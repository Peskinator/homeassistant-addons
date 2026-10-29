#!/usr/bin/env python3
"""Follow stable slskd releases, pinning the matching immutable image."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "slskd"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
IMAGE_RE = r'^ARG BUILD_SLSKD_IMAGE="ghcr.io/slskd/slskd@(sha256:[0-9a-f]{64})"$'
UPSTREAM_RE = r'^ARG BUILD_SLSKD_VERSION="([^"]+)"$'


def fetch(url: str, *, headers: dict | None = None):
    request = Request(url, headers={"User-Agent": "peskinator-slskd-updater", **(headers or {})})
    return urlopen(request, timeout=30)


def semver(value: str) -> tuple[int, ...]:
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ValueError(f"Not a stable semantic version: {value!r}")
    return tuple(map(int, match.groups()))


def release_version() -> str:
    headers = {"Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    with fetch("https://api.github.com/repos/slskd/slskd/releases/latest", headers=headers) as response:
        release = json.load(response)
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("Refusing a draft/prerelease")
    version = release["tag_name"].removeprefix("v")
    semver(version)
    return version


def image_digest(version: str) -> str:
    # Versioned images can arrive after the GitHub release. A missing image
    # fails the job without changing the published wrapper; next run retries.
    with fetch("https://ghcr.io/token?service=ghcr.io&scope=repository:slskd/slskd:pull") as response:
        token = json.load(response)["token"]
    with fetch(f"https://ghcr.io/v2/slskd/slskd/manifests/{version}", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json",
    }) as response:
        digest = response.headers.get("Docker-Content-Digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("Registry did not return an immutable image digest")
    return digest


def update(version: str, digest: str) -> bool:
    semver(version)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Invalid digest")
    dockerfile = (APP / "Dockerfile").read_text(encoding="utf-8")
    current = re.search(UPSTREAM_RE, dockerfile, re.M)
    pin = re.search(IMAGE_RE, dockerfile, re.M)
    config = (APP / "config.yaml").read_text(encoding="utf-8")
    wrapper = re.search(r'^version: "([^"]+)"$', config, re.M)
    if not current or not pin or not wrapper:
        raise RuntimeError("Cannot parse current upstream/wrapper version and pin")
    if semver(version) < semver(current[1]):
        raise RuntimeError("Refusing an upstream downgrade")
    if version == current[1] and digest == pin[1]:
        print(f"slskd already current: {wrapper[1]}")
        return False
    revision = 1
    if version == current[1]:
        prefix, separator, suffix = wrapper[1].rpartition("-")
        if not separator or prefix != version or not suffix.isdigit():
            raise RuntimeError("Unexpected wrapper revision")
        revision = int(suffix) + 1
    new_version = f"{version}-{revision}"
    dockerfile = re.sub(UPSTREAM_RE, f'ARG BUILD_SLSKD_VERSION="{version}"', dockerfile, flags=re.M)
    dockerfile = re.sub(IMAGE_RE, f'ARG BUILD_SLSKD_IMAGE="ghcr.io/slskd/slskd@{digest}"', dockerfile, count=1, flags=re.M)
    config = re.sub(r'^version: "[^"]+"$', f'version: "{new_version}"', config, count=1, flags=re.M)
    changelog = (APP / "CHANGELOG.md").read_text(encoding="utf-8")
    header = "# Changelog\n\n"
    if not changelog.startswith(header):
        raise RuntimeError("Unexpected changelog header")
    entry = f"## {new_version}\n\n- Update to stable slskd {version}, pinned to `{digest}`.\n\n"
    for path, content in ((APP / "Dockerfile", dockerfile), (APP / "config.yaml", config),
                          (APP / "CHANGELOG.md", header + entry + changelog[len(header):])):
        path.write_text(content, encoding="utf-8", newline="\n")
    print(f"Updated slskd to {new_version}")
    return True


def main() -> int:
    version = release_version()
    update(version, image_digest(version))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
