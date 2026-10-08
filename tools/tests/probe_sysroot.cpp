// Checks the arm64 sysroot the core is cross-compiled against: the C and C++ libraries, the X11
// headers SDL3's video driver needs, and the libraries the emulator's own code links.
// tools/tests/probe-sysroot.sh compiles and links it with the cross clang.
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <dbus/dbus.h>
#include <libudev.h>
#include <uuid/uuid.h>
#include <zlib.h>

int main() {
    std::vector<std::string> names{"AstroQuest"};
    uuid_t id{};
    uuid_generate(id);
    char text[37]{};
    uuid_unparse(id, text);
    std::printf("%s %s %s %d\n", names[0].c_str(), text, zlibVersion(),
                static_cast<int>(sizeof(void*)));
    return 0;
}
