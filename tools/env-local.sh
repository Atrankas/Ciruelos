# Written by tools/setup-toolchain-windows.py: the toolchain this repository builds with,
# with the paths of this machine. Source it from Git Bash before building:
#   source tools/env-local.sh
# (tools/env-win.sh and tools/env-cross.sh still do their own part of the job.)
export ANDROID_NDK="/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/android-ndk"
export ANDROID_SDK="/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/android-sdk"
export JAVA_HOME="/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/jdk"
export PATH="/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/xz/bin_x86-64":"/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/zstd":"/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/node":"/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/llvm/bin":"/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/cmake/bin":"/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/tools/ninja":"$PATH"
# The runtime the APK build takes its Linux runtime out of.
export BACHATA_APK="/c/Users/Ochentunas/Documents/deepseek-harness/default-workspace/AstroQuest/bachatas4-0.2.4-release.apk"
