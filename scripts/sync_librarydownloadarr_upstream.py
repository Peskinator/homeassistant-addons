#!/usr/bin/env python3
"""Track the immutable digest behind LibraryDownloadarr's upstream latest tag."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "librarydownloadarr" / "Dockerfile"
CONFIG = ROOT / "librarydownloadarr" / "config.yaml"
CHANGELOG = ROOT / "librarydownloadarr" / "CHANGELOG.md"
TOKEN_URL = "https://ghcr.io/token?service=ghcr.io&scope=repository:kikootwo/librarydownloadarr:pull"
MANIFEST_URL = "https://ghcr.io/v2/kikootwo/librarydownloadarr/manifests/latest"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def latest_digest() -> str:
    with urlopen(Request(TOKEN_URL, headers={"User-Agent": "peskinator-ha-updater"}), timeout=30) as response:
        token = json.load(response)["token"]
    request = Request(
        MANIFEST_URL,
        method="HEAD",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json",
            "User-Agent": "peskinator-ha-updater",
        },
    )
    with urlopen(request, timeout=30) as response:
        digest = response.headers.get("Docker-Content-Digest")
    if not digest or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("Unable to read a valid upstream LibraryDownloadarr digest")
    return digest


def next_patch(version: str) -> str:
    match = VERSION_RE.fullmatch(version)
    if not match:
        raise RuntimeError(f"Unsupported App version: {version!r}")
    major, minor, patch = map(int, match.groups())
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    current_match = re.search(r'^ARG BUILD_LIBRARYDOWNLOADARR_IMAGE="ghcr.io/kikootwo/librarydownloadarr@(sha256:[0-9a-f]{64})"$', dockerfile, re.MULTILINE)
    if not current_match:
        raise RuntimeError("Unable to read the pinned LibraryDownloadarr digest")
    current_digest = current_match.group(1)
    upstream_digest = latest_digest()
    if upstream_digest == current_digest:
        print(f"LibraryDownloadarr digest already current: {current_digest}")
        return 0

    config = CONFIG.read_text(encoding="utf-8")
    version_match = re.search(r'^version: "([^"]+)"$', config, re.MULTILINE)
    if not version_match:
        raise RuntimeError("Unable to read App version from config.yaml")
    version = next_patch(version_match.group(1))
    dockerfile, count = re.subn(current_match.re, f'ARG BUILD_LIBRARYDOWNLOADARR_IMAGE="ghcr.io/kikootwo/librarydownloadarr@{upstream_digest}"', dockerfile, count=1)
    if count != 1:
        raise RuntimeError("Unable to pin the new LibraryDownloadarr digest")
    config, count = re.subn(r'^version: "[^"]+"$', f'version: "{version}"', config, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError("Unable to update App version")
    DOCKERFILE.write_text(dockerfile, encoding="utf-8", newline="\n")
    CONFIG.write_text(config, encoding="utf-8", newline="\n")
    entry = f"## {version}\n\n- Automated update to upstream container digest `{upstream_digest}`.\n\n"
    changelog = CHANGELOG.read_text(encoding="utf-8")
    CHANGELOG.write_text("# Changelog\n\n" + entry + changelog.removeprefix("# Changelog\n\n"), encoding="utf-8", newline="\n")
    print(f"Updated LibraryDownloadarr to {version}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
