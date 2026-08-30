#!/usr/bin/env python3
"""Synchronize the App wrapper with the latest stable SFTPGo release."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "sftpgo" / "Dockerfile"
CONFIG = ROOT / "sftpgo" / "config.yaml"
CHANGELOG = ROOT / "sftpgo" / "CHANGELOG.md"
RELEASE_URL = "https://api.github.com/repos/drakkan/sftpgo/releases/latest"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def release_version() -> str:
    request = Request(
        RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "peskinator-homeassistant-sftpgo-updater",
        },
    )
    with urlopen(request, timeout=30) as response:
        release = json.load(response)

    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("Latest GitHub release is not a stable release")

    version = str(release["tag_name"]).lstrip("v")
    if not VERSION_RE.fullmatch(version):
        raise RuntimeError(f"Unsupported upstream release tag: {release['tag_name']!r}")
    return version


def semver_tuple(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(version)
    if not match:
        raise RuntimeError(f"Unsupported semantic version: {version!r}")
    return tuple(map(int, match.groups()))


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    source = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, source, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one matching version in {path}")
    path.write_text(updated, encoding="utf-8", newline="\n")


def update_changelog(version: str) -> None:
    entry = f"## {version}-1\n\n- Automated update to upstream SFTPGo v{version}.\n\n"
    source = CHANGELOG.read_text(encoding="utf-8") if CHANGELOG.exists() else "# Changelog\n\n"
    if entry in source:
        return
    header = "# Changelog\n\n"
    if not source.startswith(header):
        raise RuntimeError("Unexpected changelog header")
    CHANGELOG.write_text(header + entry + source[len(header):], encoding="utf-8", newline="\n")


def main() -> int:
    upstream = release_version()
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    match = re.search(r'^ARG BUILD_SFTPGO_VERSION="v([^"]+)"$', dockerfile, re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to read current SFTPGo version from Dockerfile")
    current = match.group(1)

    if semver_tuple(upstream) <= semver_tuple(current):
        print(f"SFTPGo already current: v{current}")
        return 0

    replace_once(DOCKERFILE, r'^ARG BUILD_SFTPGO_VERSION="v[^"]+"$', f'ARG BUILD_SFTPGO_VERSION="v{upstream}"')
    replace_once(CONFIG, r'^version: "[^"]+"$', f'version: "{upstream}-1"')
    update_changelog(upstream)
    print(f"Updated SFTPGo from v{current} to v{upstream}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
