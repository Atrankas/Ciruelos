"""Works out the exact Debian package list tools/mk-sysroot.mjs needs.

mk-sysroot.mjs takes packages as listed and resolves nothing, while a -dev package without its
dependencies is a sysroot that fails later, at the first missing header. This reads the same
index mk-sysroot reads, follows Depends/Pre-Depends (and the first alternative that exists),
and prints the closure in the order it was resolved.

    python sysroot-packages.py [root package ...]
"""
from __future__ import annotations

import io
import lzma
import re
import sys
import urllib.request

SUITE = "trixie"
MIRROR = "https://deb.debian.org/debian"
INDEXES = [f"{MIRROR}/dists/{SUITE}/main/binary-arm64/Packages.xz",
           f"{MIRROR}/dists/{SUITE}-updates/main/binary-arm64/Packages.xz"]

ROOTS = [
    # What the emulator core is written in and links against, and the headers it compiles with.
    "libc6-dev", "libstdc++-14-dev", "libgcc-14-dev",
    # SDL3's X11 video driver, which the core builds for the headset's Linux runtime.
    "libx11-dev", "libxext-dev", "libxcb1-dev", "libxau-dev", "libxdmcp-dev",
    # The rest of what the core's libraries want at link time.
    "libudev-dev", "uuid-dev", "zlib1g-dev", "libdrm-dev", "libdbus-1-dev", "libcap-dev",
    "libvulkan-dev", "libxkbcommon-dev",
]


def index() -> dict[str, dict[str, str]]:
    packages: dict[str, dict[str, str]] = {}
    for url in INDEXES:
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                raw = response.read()
        except Exception as error:  # noqa: BLE001 - -updates may not exist
            print(f"skipping {url}: {error}", file=sys.stderr)
            continue
        text = lzma.decompress(raw).decode("utf-8", "replace")
        for stanza in text.split("\n\n"):
            if not stanza.strip():
                continue
            fields = dict(re.findall(r"^([A-Za-z-]+): (.*(?:\n .*)*)$", stanza, re.M))
            name = fields.get("Package")
            if not name:
                continue
            fields = {key: re.sub(r"\n ", "", value) for key, value in fields.items()}
            packages[name] = fields          # later indexes win: updates replace the base
    return packages


def names(field: str) -> list[str]:
    """The package names a dependency field asks for, alternatives left as a list per group."""
    groups = []
    for entry in field.split(","):
        alternatives = [re.split(r"[ (]", part.strip(), 1)[0] for part in entry.split("|")]
        groups.append([name for name in alternatives if name])
    return groups


def closure(packages: dict[str, dict[str, str]], roots: list[str]) -> list[str]:
    wanted: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name in seen:
            return
        fields = packages.get(name)
        if fields is None:
            print(f"# {name} is not in the index", file=sys.stderr)
            return
        seen.add(name)
        wanted.append(name)
        for field in ("Pre-Depends", "Depends"):
            for group in names(fields.get(field, "")):
                for alternative in group:
                    if alternative in packages:
                        add(alternative)
                        break
                else:
                    print(f"# {name} -> {' | '.join(group)}: none in the index", file=sys.stderr)

    for root in roots:
        add(root)
    return wanted


def main() -> int:
    packages = index()
    print(f"# {len(packages)} packages in the {SUITE} arm64 index", file=sys.stderr)
    wanted = closure(packages, sys.argv[1:] or ROOTS)
    print(" ".join(wanted))
    print(f"# {len(wanted)} packages", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
