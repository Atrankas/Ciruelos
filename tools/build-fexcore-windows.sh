#!/usr/bin/env bash
# Builds FEXCore for the headset on Windows: the same build as
# shadps4-arm64-main/runtime/scripts/build-fexcore-smoke-aarch64.sh, with the paths that script
# hands to CMake converted to the form a native Windows CMake understands.
#
#   tools/build-fexcore-windows.sh
#
# Why the copy: that script computes its directories with `pwd -P`, which Git Bash answers with
# `/c/Users/...`, and passes them to CMake through -D. MSYS converts such an argument only when it
# recognises it as a path, which it does not inside `-DNAME=/c/...` or inside the `;`-separated
# source list, so CMake is told to look for `/c/Users/...` and finds nothing:
#
#     Cannot find source file: /c/.../src/core/fex/fex_guest_engine.cpp
#
# Everything else - the pinned checkout, the FEXCore-only patch, the FEX submodules, the build
# itself and the two verifiers - is what that script does, in the same order. Keep the two in step
# when the one upstream changes.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly root
# The repository's own scripts ask for their toolchain beside them; do the same when this is run
# on its own rather than after `source tools/env-local.sh`.
if ! command -v cmake >/dev/null || ! command -v ninja >/dev/null; then
  # shellcheck disable=SC1091
  source "$root/tools/env-local.sh"
fi

project_root="$root/shadps4-arm64-main"
readonly project_root
# The form CMake gets: `C:/Users/...` rather than `/c/Users/...`.
project_win=$(cygpath -m "$project_root")
readonly project_win
lock="$project_root/runtime/locks/components.lock.json"
readonly lock
fex_source="$project_root/runtime/sources/fex"
readonly fex_source
build_dir="$project_root/runtime/build/fexcore-smoke-build"
readonly build_dir
stage_dir="$project_root/runtime/build/fexcore-smoke-stage"
readonly stage_dir
patch_path="$project_root/runtime/patches/fex-fexcore-only.patch"
readonly patch_path

mapfile -t fex_lock < <(node -e '
const { readFileSync } = require("node:fs");
const lock = JSON.parse(readFileSync(process.argv[1], "utf8"));
const component = lock.components?.find(({ name }) => name === "fex");
if (!component || !/^https:\/\//.test(component.url) || !/^[0-9a-f]{40}$/.test(component.revision)) process.exit(1);
console.log(component.url);
console.log(component.revision);
' "$lock")
[[ ${#fex_lock[@]} -eq 2 ]] || { echo "invalid fex component lock" >&2; exit 1; }

mkdir -p "$build_dir"
bash "$project_root/runtime/scripts/checkout-component.sh" fex "${fex_lock[0]}" "${fex_lock[1]}"
git -C "$fex_source" submodule update --init --depth 1 --jobs 8 -- \
  External/unordered_dense External/rpmalloc External/xxhash External/fmt External/range-v3 \
  Source/Common/cpp-optparse
[[ $(git -C "$fex_source" rev-parse HEAD) == "${fex_lock[1]}" ]] || {
  echo "fex checkout does not match components lock" >&2
  exit 1
}

patched=0
cleanup() {
  local status=$?
  if [[ $patched -eq 1 ]] && ! git -C "$fex_source" apply -R "$patch_path"; then
    echo "failed to reverse temporary FEXCore build patch" >&2
    [[ $status -eq 0 ]] && status=1
  fi
  exit "$status"
}
trap cleanup EXIT

git -C "$fex_source" apply --check "$patch_path"
git -C "$fex_source" apply "$patch_path"
patched=1

cmake -S "$fex_source" -B "$build_dir" -G Ninja \
  -DCMAKE_SYSTEM_NAME=Linux \
  -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
  -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++ \
  -DCMAKE_C_COMPILER_TARGET=aarch64-linux-gnu \
  -DCMAKE_CXX_COMPILER_TARGET=aarch64-linux-gnu \
  -DCMAKE_BUILD_TYPE=Release \
  -DTUNE_CPU=none \
  -DCMAKE_INSTALL_PREFIX=/usr \
  -DCMAKE_EXE_LINKER_FLAGS="-Wl,--build-id=sha1" \
  -DBUILD_FEXCORE_ONLY=ON \
  -DFEXCORE_PROJECT_SOURCE_DIR="$project_win/src" \
  -DFEXCORE_SMOKE_SOURCE="$project_win/runtime/probes/fexcore-smoke.cpp" \
  -DFEXCORE_GUEST_HARNESS_SOURCES="$project_win/src/core/fex/fex_guest_engine.cpp;$project_win/src/core/guest_cpu/fex_guest_cpu.cpp;$project_win/src/core/guest_cpu/hle_call_adapter.cpp;$project_win/src/core/guest_cpu/fex_hle_bridge.cpp;$project_win/runtime/probes/fexcore-guest-harness.cpp" \
  -DBUILD_TESTING=OFF \
  -DBUILD_FEX_LINUX_TESTS=OFF \
  -DBUILD_THUNKS=OFF \
  -DBUILD_FEXCONFIG=OFF \
  -DENABLE_GDB_SYMBOLS=OFF \
  -DENABLE_LTO=OFF \
  -DENABLE_JEMALLOC_GLIBC_ALLOC=OFF \
  -DENABLE_OFFLINE_TELEMETRY=OFF \
  -DENABLE_VIXL_DISASSEMBLER=OFF \
  -DENABLE_VIXL_SIMULATOR=OFF \
  -DENABLE_ZYDIS=OFF \
  -DENABLE_FEXCORE_PROFILER=OFF

ninja -C "$build_dir" -t clean fexcore-guest-harness
cmake --build "$build_dir" --target fexcore-smoke fexcore-guest-harness --parallel

rm -rf "$stage_dir"
mkdir -p "$stage_dir"
cmake --install "$build_dir" --prefix "$stage_dir"
aarch64-linux-gnu-strip "$stage_dir/bin/fexcore-smoke" "$stage_dir/bin/fexcore-guest-harness"
node "$project_root/runtime/tests/verify-fexcore-smoke-build.mjs" "$stage_dir/bin/fexcore-smoke"
node "$project_root/runtime/tests/verify-fexcore-guest-harness-build.mjs" \
  "$stage_dir/bin/fexcore-guest-harness"
echo "FEXCore built: $stage_dir"
