#!/usr/bin/env python3
"""Synchronize the App wrapper with the latest stable Agregarr Docker tag."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "agregarr" / "config.yaml"
CHANGELOG = ROOT / "agregarr" / "CHANGELOG.md"
TOKEN_URL = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:bitr8/agregarr:pull"
TAGS_URL = "https://registry-1.docker.io/v2/bitr8/agregarr/tags/list"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def semver(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise RuntimeError(f"Unsupported semantic version: {value!r}")
    return tuple(map(int, match.groups()))


def latest_stable_tag() -> str:
    with urlopen(Request(TOKEN_URL, headers={"User-Agent": "peskinator-ha-updater"}), timeout=30) as response:
        token = json.load(response)["token"]
    request = Request(TAGS_URL, headers={"Authorization": f"Bearer {token}", "User-Agent": "peskinator-ha-updater"})
    with urlopen(request, timeout=30) as response:
        tags = json.load(response)["tags"]
    stable = [tag for tag in tags if VERSION_RE.fullmatch(tag)]
    if not stable:
        raise RuntimeError("No stable semantic-version Agregarr Docker tag found")
    return max(stable, key=semver)


def main() -> int:
    source = CONFIG.read_text(encoding="utf-8")
    match = re.search(r'^version: "([^"]+)"$', source, re.MULTILINE)
    if not match:
        raise RuntimeError("Unable to read App version from config.yaml")
    current = match.group(1)
    upstream = latest_stable_tag()
    if semver(upstream) <= semver(current):
        print(f"Agregarr already current: {current}")
        return 0

    updated, count = re.subn(r'^version: "[^"]+"$', f'version: "{upstream}"', source, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError("Unable to update App version")
    CONFIG.write_text(updated, encoding="utf-8", newline="\n")
    entry = f"## {upstream}\n\n- Automated update to stable `bitr8/agregarr:{upstream}`.\n\n"
    changelog = CHANGELOG.read_text(encoding="utf-8")
    CHANGELOG.write_text("# Changelog\n\n" + entry + changelog.removeprefix("# Changelog\n\n"), encoding="utf-8", newline="\n")
    print(f"Updated Agregarr from {current} to {upstream}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
