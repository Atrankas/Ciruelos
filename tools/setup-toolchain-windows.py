#!/usr/bin/env python3
"""Sets up the portable Windows toolchain AstroQuest builds with, without admin rights.

Everything lands under `tools/` inside the repository (plus the Bachata S4 APK the APK build
takes its Linux runtime from, at the repository root). Nothing is installed system-wide and no
PATH is changed: `tools/env-cross.sh` and the build scripts add what they need themselves.

    python tools/setup-toolchain-windows.py [--only NAME[,NAME...]] [--list]

Downloads are skipped when the file is already there with the expected size, so the script can be
run again after a failure. Needs Python 3.9+ and a working HTTPS connection (it uses urllib, which
does not go through the Windows certificate store the way curl does).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
CACHE = TOOLS / "downloads"

UA = {"User-Agent": "AstroQuest-toolchain-setup/1"}

LLVM_VERSION = "21.1.8"
NODE_VERSION = "22.20.0"
CMAKE_VERSION = "4.4.4"
NINJA_VERSION = "1.13.1"
XZ_VERSION = "5.8.4"
ZSTD_VERSION = "1.5.7"

DOWNLOADS = {
    "llvm": (
        f"https://github.com/llvm/llvm-project/releases/download/llvmorg-{LLVM_VERSION}/"
        f"clang+llvm-{LLVM_VERSION}-x86_64-pc-windows-msvc.tar.xz",
        TOOLS / "llvm",
    ),
    "cmake": (
        f"https://github.com/Kitware/CMake/releases/download/v{CMAKE_VERSION}/"
        f"cmake-{CMAKE_VERSION}-windows-x86_64.zip",
        TOOLS / "cmake",
    ),
    "ninja": (
        f"https://github.com/ninja-build/ninja/releases/download/v{NINJA_VERSION}/ninja-win.zip",
        TOOLS / "ninja",
    ),
    "node": (
        f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip",
        TOOLS / "node",
    ),
    "xz": (
        f"https://github.com/tukaani-project/xz/releases/download/v{XZ_VERSION}/"
        f"xz-{XZ_VERSION}-windows.zip",
        TOOLS / "xz",
    ),
    "zstd": (
        f"https://github.com/facebook/zstd/releases/download/v{ZSTD_VERSION}/"
        f"zstd-v{ZSTD_VERSION}-win64.zip",
        TOOLS / "zstd",
    ),
    "xwin": (
        "https://github.com/Jake-Shadle/xwin/releases/download/0.10.0/"
        "xwin-0.10.0-x86_64-pc-windows-msvc.tar.gz",
        TOOLS / "xwin",
    ),
    "jdk": (
        "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse",
        TOOLS / "jdk",
    ),
    "ndk": (
        "https://dl.google.com/android/repository/android-ndk-r27c-windows.zip",
        TOOLS / "android-ndk",
    ),
    "cmdline-tools": (
        "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip",
        TOOLS / "android-sdk" / "cmdline-tools" / "latest",
    ),
    "openxr": (
        "https://repo1.maven.org/maven2/org/khronos/openxr/openxr_loader_for_android/1.1.63/"
        "openxr_loader_for_android-1.1.63.aar",
        TOOLS / "openxr",
    ),
    "bachata": (
        "https://github.com/JICA98/Bachata-S4/releases/download/v0.2.4/"
        "bachatas4-0.2.4-release.apk",
        ROOT,
    ),
}

# What "already there" means per entry, checked before downloading anything.
READY = {
    "llvm": lambda: (TOOLS / "llvm" / "bin" / "clang.exe").exists(),
    "cmake": lambda: (TOOLS / "cmake" / "bin" / "cmake.exe").exists(),
    "ninja": lambda: (TOOLS / "ninja" / "ninja.exe").exists(),
    "node": lambda: (TOOLS / "node" / "node.exe").exists(),
    "xz": lambda: any((TOOLS / "xz").rglob("xz.exe")),
    "zstd": lambda: any((TOOLS / "zstd").rglob("zstd.exe")),
    "xwin": lambda: any((TOOLS / "xwin").rglob("xwin.exe")),
    "jdk": lambda: (TOOLS / "jdk" / "bin" / "javac.exe").exists(),
    "ndk": lambda: (TOOLS / "android-ndk" / "toolchains" / "llvm" / "prebuilt" /
                    "windows-x86_64" / "bin" / "clang++.exe").exists(),
    "cmdline-tools": lambda: (TOOLS / "android-sdk" / "cmdline-tools" / "latest" / "bin" /
                              "sdkmanager.bat").exists(),
    "openxr": lambda: (TOOLS / "openxr" / "jni" / "arm64-v8a" / "libopenxr_loader.so").exists(),
    "bachata": lambda: (ROOT / "bachatas4-0.2.4-release.apk").exists(),
}

# Where the executables the build scripts call by name ended up (idempotent: the script is run
# again after a failure).
ON_PATH = {
    "xz": "xz/bin_x86-64",
    "zstd": "zstd",
    "node": "node",
    "llvm": "llvm/bin",
    "cmake": "cmake/bin",
    "ninja": "ninja",
}


def say(message: str) -> None:
    print(message, flush=True)


def download(name: str, url: str) -> Path:
    """Fetches `url` into tools/downloads. A file that is already the whole thing is left alone;
    a partial one is continued from where it stopped."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / os.path.basename(urllib.parse.urlparse(url).path)

    # Ask the server how big it should be: that is what says whether what is on disk is a whole
    # file, a beginning of one, or nothing at all.
    expected = 0
    try:
        head = urllib.request.Request(url, headers=UA, method="HEAD")
        with urllib.request.urlopen(head, timeout=60) as response:
            length = response.headers.get("Content-Length")
            expected = int(length) if length and length.isdigit() else 0
    except Exception:  # noqa: BLE001 - without a length the file is fetched whole
        expected = 0
    if target.exists():
        have = target.stat().st_size
        if expected and have == expected:
            say(f"    {name}: {expected / 1048576:.1f} MB already downloaded")
            return target
        if not expected and have:
            say(f"    {name}: {have / 1048576:.1f} MB already there, fetching the rest")
        if expected and have > expected:
            target.unlink()
            have = 0
    else:
        have = 0

    request = urllib.request.Request(url, headers=UA)
    if have:
        request.add_header("Range", f"bytes={have}-")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = response.headers.get("Content-Length")
            total = have + int(total) if total and total.isdigit() else expected
            mode = "ab" if have and response.status == 206 else "wb"
            if mode == "wb":
                have = 0
            done = have
            next_report = 0.0
            with open(target, mode) as out:
                while True:
                    chunk = response.read(4 << 20)
                    if not chunk:
                        break
                    out.write(chunk)
                    done += len(chunk)
                    if total and done / total >= next_report:
                        say(f"    {name}: {done / 1048576:7.1f} / {total / 1048576:.1f} MB")
                        next_report += 0.1
    except urllib.error.HTTPError as error:
        # A range the server will not serve on a file that is already whole.
        if error.code == 416 and target.exists() and target.stat().st_size > 0:
            say(f"    {name}: already downloaded in full")
            return target
        say(f"    {name}: download failed ({error})")
        raise
    except Exception as error:  # noqa: BLE001 - reported and re-raised
        say(f"    {name}: download failed ({error})")
        raise
    return target


def extract(archive: Path, destination: Path) -> None:
    """Unpacks an archive into `destination`, dropping the single top-level folder if there is
    one (LLVM's tarball and the JDK's zip both have one).

    The unpacking happens beside the repository rather than inside `tools/`: some of what is
    unpacked (LLVM's own headers, the NDK) goes deep, and Windows gives up on paths over 260
    characters, which a staging folder inside `tools/` pushes it over.
    """
    destination.mkdir(parents=True, exist_ok=True)
    staging_root = TOOLS.parent.parent if os.access(TOOLS.parent.parent, os.W_OK) else TOOLS
    # A plain directory rather than tempfile.mkdtemp: the latter is made owner-only, and in a
    # sandboxed shell (the DeepSeek Harness file sandbox, for one) nothing can then be written
    # inside it at all, which fails the unpacking on its first folder.
    staging = staging_root / f"_unpack-{destination.name}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        say(f"    unpacking {archive.name} in {staging}")
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(staging)
        else:
            with tarfile.open(archive, "r:*") as bundle:
                # "data" keeps the archive from writing outside the staging folder and drops the
                # permissions and owners a Windows machine has no use for.
                bundle.extractall(staging, filter="data")
        entries = [entry for entry in staging.iterdir()]
        source = staging
        if len(entries) == 1 and entries[0].is_dir():
            source = entries[0]
        for entry in source.iterdir():
            target = destination / entry.name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(entry), str(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def write_text_lf(path: Path, text: str) -> None:
    """Writes a file with Unix line endings: these are read by shell scripts and by clang, and a
    stray carriage return at the end of a path is a path that does not exist."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def hard_link_clang() -> None:
    """The cross compiler is clang under a name that selects the target: the name is what makes
    `tools/llvm/bin/aarch64-linux-gnu-clang.exe` build for aarch64 without any flag (see
    tools/toolchain-aarch64-linux.cmake)."""
    bindir = TOOLS / "llvm" / "bin"
    for source, target in [("clang.exe", "aarch64-linux-gnu-clang.exe"),
                           ("clang++.exe", "aarch64-linux-gnu-clang++.exe"),
                           # The FEXCore build strips its artifacts with the GNU name, and the
                           # verifiers that follow read them with `readelf` and `strings`.
                           ("llvm-strip.exe", "aarch64-linux-gnu-strip.exe"),
                           ("llvm-readelf.exe", "readelf.exe"),
                           ("llvm-strings.exe", "strings.exe")]:
        source_path = bindir / source
        target_path = bindir / target
        if target_path.exists() or not source_path.exists():
            continue
        try:
            os.link(source_path, target_path)
            say(f"    linked {target}")
        except OSError:
            shutil.copy2(source_path, target_path)
            say(f"    copied {target}")
    # Beside the two names, a config file gives them the sysroot, so that build steps which call
    # the compiler without CMake's flags (libpng's configuration generator does) still cross
    # compile. The name is the target triple clang normalises the program name to.
    config = bindir / "aarch64-unknown-linux-gnu.cfg"
    sysroot = (TOOLS / "sysroot-arm64").as_posix()
    wanted = (f"--sysroot={sysroot}\n"
              f"--target=aarch64-linux-gnu\n"
              f"-L{sysroot}/usr/lib/aarch64-linux-gnu\n"
              # There is no aarch64-linux-gnu-ld on a Windows machine: the linker LLVM ships
              # writes the same ELF objects, whatever it runs on.
              f"-fuse-ld=lld\n")
    # Always written: a comparison through text mode hides the carriage returns this is here to
    # avoid, and the file is two lines.
    if not config.exists() or config.read_bytes() != wanted.replace("\n", "\n").encode():
        write_text_lf(config, wanted)
        say(f"    wrote {config.name}")


def write_python_local() -> None:
    """tools/python.local holds the full path of the Python the build scripts should use."""
    path = TOOLS / "python.local"
    wanted = Path(sys.executable).as_posix()
    write_text_lf(path, wanted)
    say(f"    wrote tools/python.local -> {wanted}")


def msys(path: Path) -> str:
    """A path Git Bash understands inside PATH: the colon of `C:/...` would otherwise be taken for
    the separator between two entries, and everything after it read as a relative path."""
    text = path.as_posix()
    if len(text) > 1 and text[1] == ":":
        return "/" + text[0].lower() + text[2:]
    return text


def write_env_local() -> None:
    """Writes tools/env-local.sh: what the build scripts need on PATH and in the environment,
    with the paths of this machine resolved. Source it from Git Bash beside tools/env-cross.sh:
    the scripts find the Android SDK and the JDK nowhere else."""
    on_path = ":".join(f'"{msys(TOOLS / folder)}"' for folder in ON_PATH.values())
    body = f"""# Written by tools/setup-toolchain-windows.py: the toolchain this repository builds with,
# with the paths of this machine. Source it from Git Bash before building:
#   source tools/env-local.sh
# (tools/env-win.sh and tools/env-cross.sh still do their own part of the job.)
export ANDROID_NDK="{msys(TOOLS / 'android-ndk')}"
export ANDROID_SDK="{msys(TOOLS / 'android-sdk')}"
export JAVA_HOME="{msys(TOOLS / 'jdk')}"
export PATH={on_path}:"$PATH"
# The runtime the APK build takes its Linux runtime out of.
export BACHATA_APK="{msys(ROOT / 'bachatas4-0.2.4-release.apk')}"
"""
    path = TOOLS / "env-local.sh"
    write_text_lf(path, body)
    say("    wrote tools/env-local.sh")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="", help="comma-separated subset of the entries")
    parser.add_argument("--list", action="store_true", help="show what would be set up and stop")
    arguments = parser.parse_args()

    if arguments.list:
        for name in DOWNLOADS:
            say(f"{name:<14} {'present' if READY[name]() else 'missing'}")
        return 0

    wanted = [name.strip() for name in arguments.only.split(",") if name.strip()] or list(DOWNLOADS)
    unknown = [name for name in wanted if name not in DOWNLOADS]
    if unknown:
        say(f"unknown: {', '.join(unknown)} (see --list)")
        return 2

    for name in wanted:
        url, destination = DOWNLOADS[name]
        if READY[name]():
            say(f"{name}: already there")
            continue
        say(f"{name}:")
        archive = download(name, url)
        if name == "bachata":
            # The APK itself is what the build wants, at the repository root: it takes the Linux
            # runtime the emulator core runs in out of it.
            shutil.copy2(archive, ROOT / archive.name)
        else:
            extract(archive, destination)
        if name == "llvm":
            hard_link_clang()
        if not READY[name]():
            say(f"    !! {name} does not look complete after unpacking: check {destination}")
            return 1

    write_python_local()
    write_env_local()
    say("")
    say("Toolchain in place. Next, from Git Bash:")
    say("  source tools/env-local.sh          # SDK, NDK, JDK and the tools above")
    say("  python tools/setup-toolchain-windows.py --list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
