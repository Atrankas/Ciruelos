# Written by tools/setup-toolchain-windows.py: the toolchain this repository builds with,
# with the paths of this machine. Source it from Git Bash before building:
#   source tools/env-local.sh
# (tools/env-win.sh and tools/env-cross.sh still do their own part of the job.)
export ANDROID_NDK="/c/ps4emu/tools/android-ndk"
export ANDROID_SDK="/c/ps4emu/tools/android-sdk"
export JAVA_HOME="/c/ps4emu/tools/jdk"
export PATH="/c/ps4emu/tools/xz/bin_x86-64":"/c/ps4emu/tools/zstd":"/c/ps4emu/tools/node":"/c/ps4emu/tools/llvm/bin":"/c/ps4emu/tools/cmake/bin":"/c/ps4emu/tools/ninja":"$PATH"
# The runtime the APK build takes its Linux runtime out of.
export BACHATA_APK="/c/ps4emu/bachatas4-0.2.4-release.apk"
