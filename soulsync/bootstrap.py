"""Attach SoulSync's mutable paths to explicit HA persistent mounts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys


def persistent_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Storage paths must be absolute paths without '..'")
    resolved = path.resolve()
    if not any(root in resolved.parents for root in (Path("/media"), Path("/share"))):
        raise ValueError("Media, download and import paths must be BELOW /media or /share")
    return path


def seed_missing(source: Path, target: Path) -> None:
    """Seed shipped files once; never overwrite existing persistent state."""
    for item in source.iterdir():
        if item.name == "__pycache__":
            continue
        destination = target / item.name
        if destination.exists() or destination.is_symlink():
            continue
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)


def attach(source: Path, target: Path, uid: int, gid: int, *, seed: bool = False) -> None:
    target.mkdir(parents=True, exist_ok=True)
    # Only change directory nodes we use, never recursively chown a media share.
    os.chown(target, uid, gid)
    if source.is_symlink():
        source.unlink()
    elif source.exists():
        if not source.is_dir():
            raise RuntimeError(f"Expected a directory at {source}")
        if seed:
            seed_missing(source, target)
        shutil.rmtree(source)  # image-layer directory only, before application startup
    source.symlink_to(target, target_is_directory=True)


def prepare() -> dict:
    for key, value in json.loads(Path("/ha-upstream-env.json").read_text()).items():
        os.environ.setdefault(key, value)
    data = Path("/data")
    if not data.is_dir() or not os.path.ismount(data):
        raise RuntimeError("Missing persistent /data mount; refusing to start with disposable state")
    if not all(os.path.ismount(path) for path in ("/media", "/share")):
        raise RuntimeError("Missing persistent /media or /share mount")
    options_file = data / "options.json"
    options = json.loads(options_file.read_text()) if options_file.exists() else {}
    uid, gid = int(options.get("puid", 1000)), int(options.get("pgid", 1000))
    if not 1 <= uid <= 2147483647 or not 1 <= gid <= 2147483647:
        raise ValueError("puid and pgid must be positive non-root IDs")
    mask = str(options.get("umask", "002"))
    if not re.fullmatch(r"0[0-7]{2}", mask):
        raise ValueError("umask must have three octal digits, e.g. 002")
    media = persistent_path(options.get("media_root", "/media/soulsync"))
    downloads = persistent_path(options.get("downloads_path", "/share/soulsync/downloads"))
    staging = persistent_path(options.get("import_path", "/share/soulsync/inbox"))
    if any(a == b or a in b.parents or b in a.parents
           for a, b in ((media.resolve(), downloads.resolve()),
                        (media.resolve(), staging.resolve()),
                        (downloads.resolve(), staging.resolve()))):
        raise ValueError("Media, download and inbox folders must not overlap")

    # usermod -u cannot migrate a home directory that is itself a symlink.
    # Set its real persistent location before upstream adjusts IDs (also
    # important when restoring a backup with a different runtime UID/GID).
    (data / "home").mkdir(exist_ok=True)
    account = pwd.getpwnam("soulsync")
    if account.pw_dir != "/data/home":
        subprocess.run(["usermod", "-d", "/data/home", "soulsync"], check=True)
    if account.pw_gid != gid:
        subprocess.run(["groupmod", "-o", "-g", str(gid), "soulsync"], check=True)
    if account.pw_uid != uid:
        subprocess.run(["usermod", "-o", "-u", str(uid), "soulsync"], check=True)

    state_names = ("config", "data", "logs", "storage", "scripts", "home", "cache")
    owner_marker = data / ".soulsync-owner"
    owner = f"{uid}:{gid}"
    repair_owner = not owner_marker.exists() or owner_marker.read_text() != owner
    repair_owner = repair_owner or any(
        (data / name).exists() and ((data / name).stat().st_uid, (data / name).stat().st_gid) != (uid, gid)
        for name in state_names)
    for name in ("config", "data", "logs", "storage", "scripts"):
        attach(Path("/app") / name, data / name, uid, gid, seed=True)
    attach(Path("/home/soulsync"), data / "home", uid, gid, seed=True)
    for name in ("cache",):
        folder = data / name
        folder.mkdir(exist_ok=True)
        os.chown(folder, uid, gid)
    # Parent directories are created only within the selected app-owned roots.
    media.mkdir(parents=True, exist_ok=True)
    os.chown(media, uid, gid)
    for name, child in (("Transfer", "music"), ("libraries", "libraries"),
                        ("MusicVideos", "music-videos"), ("podcasts", "podcasts"),
                        ("audiobooks", "audiobooks"), ("samples", "samples")):
        attach(Path("/app") / name, media / child, uid, gid)
    attach(Path("/app/downloads"), downloads, uid, gid)
    attach(Path("/app/Staging"), staging, uid, gid)

    config = Path("/app/config/config.json")
    if not config.exists():
        initial = json.loads(Path("/defaults/config.json").read_text())
        initial.setdefault("database", {})["path"] = os.environ["DATABASE_PATH"]
        initial.setdefault("soulseek", {}).update(
            download_path="/app/downloads", transfer_path="/app/Transfer")
        initial.setdefault("import", {})["staging_path"] = "/app/Staging"
        initial.setdefault("download_source", {})["album_bundle_staging_path"] = "/app/storage/album_bundle_staging"
        # These optional features must also write to persistent media, never
        # the image filesystem or someone else's existing movie/TV folders.
        initial.setdefault("library", {}).update(
            podcasts_path="/app/podcasts", audiobooks_path="/app/audiobooks",
            sample_paths=["/app/samples"])
        initial.setdefault("podcasts", {})["download_path"] = "/app/podcasts"
        initial.setdefault("audiobooks", {})["download_path"] = "/app/audiobooks"
        config.write_text(json.dumps(initial, indent=2) + "\n")
        os.chown(config, uid, gid)

    # Seeded templates/avatars/scripts may have come from root-owned image files.
    # This is private state only; existing media and download trees are not walked.
    if repair_owner:
        for root in (data / name for name in state_names):
            for current, dirs, files in os.walk(root, followlinks=False):
                os.chown(current, uid, gid)
                for name in dirs + files:
                    path = Path(current) / name
                    if not path.is_symlink():
                        os.chown(path, uid, gid)
        owner_marker.write_text(owner)
    os.environ.update(PUID=str(uid), PGID=str(gid), UMASK=mask)
    print(f"SoulSync persistent state: /data; music: {media / 'music'}; inbox: {staging}", flush=True)
    return options


if __name__ == "__main__":
    try:
        prepare()
        os.execv("/entrypoint.sh", ["/entrypoint.sh", *sys.argv[1:]])
    except Exception as error:
        print(f"SoulSync startup failed: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
