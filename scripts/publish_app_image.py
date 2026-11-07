#!/usr/bin/env python3
"""Publish a HA wrapper before advertising its version to Home Assistant."""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
APPS = ("librarydownloadarr", "sftpgo", "songmirror", "soulsync")


def next_version(version: str) -> str:
    match = re.fullmatch(r"(\d+\.\d+\.)(\d+)(?:-(\d+))?", version)
    if not match:
        raise ValueError(f"Unsupported app version: {version}")
    if match[3] is not None:
        return f"{match[1]}{match[2]}-{int(match[3]) + 1}"
    return f"{match[1]}{int(match[2]) + 1}"


def verify_public(image: str, version: str) -> None:
    """Reject private/missing packages before changing the public manifest."""
    repository = image.removeprefix("ghcr.io/")
    auth = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{repository}:pull"
    with urlopen(Request(auth, headers={"User-Agent": "peskinator-ha-publisher"}), timeout=30) as response:
        token = json.load(response)["token"]
    request = Request(
        f"https://ghcr.io/v2/{repository}/manifests/{version}", method="HEAD",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json", "User-Agent": "peskinator-ha-publisher"},
    )
    with urlopen(request, timeout=30) as response:
        if not response.headers.get("Docker-Content-Digest", "").startswith("sha256:"):
            raise RuntimeError("Registry did not return an image digest")


def publish(app: str, *, migrate: bool = False) -> bool:
    if app not in APPS:
        raise ValueError("App is not in the public-image allowlist")
    path = ROOT / app / "config.yaml"
    original = path.read_text(encoding="utf-8")
    version_match = re.search(r'^version: "([^"\n]+)"$', original, re.MULTILINE)
    if not version_match:
        raise ValueError("Missing quoted app version")
    current_version = version_match[1]
    image = f"ghcr.io/peskinator/ha-{app}"
    image_match = re.search(r'^image: ["\x27]?([^"\x27\s]+)', original, re.MULTILINE)
    if image_match and image_match[1] != image:
        raise ValueError("Refusing to replace an unexpected existing image")
    # A retry of the bootstrap never invents another version once migrated.
    if migrate and image_match:
        verify_public(image, current_version)
        print(f"{app} already uses a verified prebuilt image")
        return False
    version = next_version(current_version) if migrate else current_version
    token = os.environ.get("GITHUB_TOKEN")
    actor = os.environ.get("GITHUB_ACTOR")
    if not token or not actor:
        raise RuntimeError("Run this publisher in the authenticated GitHub workflow")
    reference = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    created = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tag = f"{image}:{version}"
    with tempfile.TemporaryDirectory(prefix="ha-publish-docker-") as docker_config:
        environment = {**os.environ, "DOCKER_CONFIG": docker_config}
        subprocess.run(["docker", "login", "ghcr.io", "--username", actor, "--password-stdin"], input=token, text=True, env=environment, check=True)
        subprocess.run([
            "docker", "build", "--platform", "linux/amd64", "--tag", tag,
            "--build-arg", "BUILD_ARCH=amd64", "--build-arg", f"BUILD_VERSION={version}",
            "--build-arg", "BUILD_REPOSITORY=Peskinator/homeassistant-addons",
            "--build-arg", f"BUILD_REF={reference}", "--build-arg", f"BUILD_DATE={created}",
            "--label", "org.opencontainers.image.source=https://github.com/Peskinator/homeassistant-addons",
            str(ROOT / app),
        ], env=environment, check=True)
        subprocess.run(["docker", "push", tag], env=environment, check=True)
    try:
        verify_public(image, version)
    except Exception as error:
        raise RuntimeError(
            f"Published {tag}, but anonymous pull verification failed. Set the ha-{app} GitHub package visibility to public and retry; no HA manifest was changed."
        ) from error
    # No manifest/version changes occur until the published image is readable.
    updated = re.sub(r'^version: "[^"\n]+"$', f'version: "{version}"', original, count=1, flags=re.MULTILINE)
    if not image_match:
        updated = updated.replace(f'version: "{version}"', f'version: "{version}"\nimage: "{image}"', 1)
    path.write_text(updated, encoding="utf-8", newline="\n")
    if migrate:
        changelog = ROOT / app / "CHANGELOG.md"
        existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Changelog\n\n"
        header = "# Changelog\n\n"
        if not existing.startswith(header):
            raise ValueError("Unexpected changelog header")
        changelog.write_text(header + f"## {version}\n\n- Download the verified GitHub-built image instead of building on the Home Assistant server.\n\n" + existing[len(header):], encoding="utf-8", newline="\n")
    print(f"Verified {tag}; app manifest is ready to commit")
    return updated != original


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", choices=APPS)
    parser.add_argument("--migrate", action="store_true")
    args = parser.parse_args()
    publish(args.app, migrate=args.migrate)
