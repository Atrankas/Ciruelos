#!/usr/bin/env python3
"""Installs the Android SDK pieces the APK build needs, without Android Studio.

`quest-host/build.sh` wants three things under the SDK folder: `build-tools/36.1.0` (aapt2, d8),
`platforms/android-36` (android.jar for javac) and, for installing on the headset,
`platform-tools`. The `sdkmanager` that comes with the command-line tools fetches its package
manifest over the network in a way that fails in some sandboxed shells, so this reads the same
manifest (dl.google.com/android/repository/repository2-3.xml) and unpacks the archives itself.

    python tools/setup-android-sdk.py [--sdk tools/android-sdk] [--build-tools 36.1.0] [--platform 36]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
REPOSITORY = "https://dl.google.com/android/repository/"
MANIFEST = REPOSITORY + "repository2-3.xml"
UA = {"User-Agent": "AstroQuest-android-sdk/1"}


def say(message: str) -> None:
    print(message, flush=True)


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as response:
        return response.read()


def entries(xml: str) -> list[tuple[str, str, str]]:
    """(path, archive file name, sha1) for every package in the manifest, Windows builds only."""
    found = []
    for remote in re.finditer(r"<remotePackage path=\"([^\"]+)\">(.*?)</remotePackage>", xml, re.S):
        path, body = remote.group(1), remote.group(2)
        for archive in re.finditer(r"<archive>(.*?)</archive>", body, re.S):
            block = archive.group(1)
            host_os = re.search(r"<host-os>([^<]+)</host-os>", block)
            if host_os and host_os.group(1) != "windows":
                continue
            url = re.search(r"<url>([^<]+)</url>", block)
            sha1 = re.search(r"<sha1>([^<]+)</sha1>", block)
            if url:
                # The manifest names most archives relative to the repository root.
                link = url.group(1)
                if "://" not in link:
                    link = REPOSITORY + link
                found.append((path, link, sha1.group(1) if sha1 else ""))
    return found


def install(sdk: Path, package: str, url: str, folder: str) -> bool:
    target = sdk / folder
    if target.exists() and any(target.iterdir()):
        say(f"{package}: already there ({target})")
        return True
    cache = TOOLS / "downloads" / os.path.basename(url)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists() or cache.stat().st_size == 0:
        say(f"{package}: downloading {url}")
        data = fetch(url)
        cache.write_bytes(data)
    staging = sdk / f"_unpack-{folder.replace('/', '-')}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(cache) as bundle:
        bundle.extractall(staging)
    # The archives hold one top-level folder ("android-14", "36.1.0", ...): what the build wants
    # is the folder named after the package.
    inside = [entry for entry in staging.iterdir()]
    source = inside[0] if len(inside) == 1 and inside[0].is_dir() else staging
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    shutil.rmtree(staging, ignore_errors=True)
    say(f"{package}: installed into {target}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", default=str(TOOLS / "android-sdk"))
    parser.add_argument("--build-tools", default="36.1.0")
    parser.add_argument("--platform", default="36")
    arguments = parser.parse_args()
    sdk = Path(arguments.sdk)

    xml = fetch(MANIFEST).decode("utf-8", "replace")
    packages = entries(xml)
    say(f"{len(packages)} windows packages in the manifest")

    wanted = {
        f"build-tools;{arguments.build_tools}": f"build-tools/{arguments.build_tools}",
        f"platforms;android-{arguments.platform}": f"platforms/android-{arguments.platform}",
        "platform-tools": "platform-tools",
    }
    missing = []
    for package, folder in wanted.items():
        for path, url, _ in packages:
            if path == package:
                install(sdk, package, url, folder)
                break
        else:
            missing.append(package)

    if missing:
        say(f"not in the manifest: {', '.join(missing)}")
    say("")
    say(f"SDK at {sdk}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
