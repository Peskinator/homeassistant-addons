#!/usr/bin/env python3
"""Real container replacement/rebuild/restore test; no production credentials."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, text=True, check=True, **kwargs)


def output(*args):
    result = run(*args, capture_output=True)
    return result.stdout + result.stderr


def inside(container, source):
    # Feed code over stdin: no shell interpolation and no credentials in args.
    result = subprocess.run(["docker", "exec", "-i", container, "gosu", "soulsync", "python", "-"],
                            text=True, input=source, capture_output=True)
    if result.returncode:
        raise RuntimeError("Persistence probe failed: " + result.stdout + result.stderr)
    return result.stdout


PROBE = '''
import hashlib,json,os,sqlite3
from pathlib import Path
from core.settings import ConfigManager
c=ConfigManager()
marker="ha-container-replacement-probe"
if os.environ.get("NOT_USED"): raise AssertionError()
'''
SEED = PROBE + '''
c.set("ha_persistence_probe", marker)
c.set("spotify.client_secret", "synthetic-persistence-probe-not-a-real-secret")
paths=["/app/config/.provider-probe", "/app/data/.identity-probe", "/app/storage/avatars/.avatar-probe",
       "/app/scripts/.script-probe", "/app/Transfer/.music-probe", "/app/Staging/.upload-probe",
       "/app/downloads/.download-probe", "/app/libraries/.profile-probe", "/app/podcasts/.podcast-probe",
       "/app/audiobooks/.book-probe", "/app/MusicVideos/.video-probe", "/app/samples/.sample-probe",
       "/data/home/.tool-probe"]
for p in paths:
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(marker)
with sqlite3.connect(os.environ["DATABASE_PATH"]) as db:
    db.execute("CREATE TABLE IF NOT EXISTS ha_persistence_probe(value TEXT)")
    db.execute("INSERT INTO ha_persistence_probe VALUES (?)", (marker,))
snapshot={"key":hashlib.sha256(Path("/app/data/.encryption_key").read_bytes()).hexdigest(),
          "paths":paths}
Path("/app/data/persistence-probe.json").write_text(json.dumps(snapshot))
print("Seeded synthetic settings, encrypted token, SQLite row, identity and media files")
'''
VERIFY = PROBE + '''
s=json.loads(Path("/app/data/persistence-probe.json").read_text())
assert c.get("ha_persistence_probe")==marker, "settings reset"
assert c.get("spotify.client_secret")=="synthetic-persistence-probe-not-a-real-secret", "encrypted token lost"
assert hashlib.sha256(Path("/app/data/.encryption_key").read_bytes()).hexdigest()==s["key"], "encryption key replaced"
for p in s["paths"]:
    assert Path(p).read_text()==marker, "file lost: "+p
    target=Path(p).resolve()
    assert any(root in target.parents for root in [Path("/data"),Path("/media"),Path("/share")]), str(target)
with sqlite3.connect(os.environ["DATABASE_PATH"]) as db:
    assert db.execute("SELECT value FROM ha_persistence_probe").fetchone()[0]==marker
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
assert os.getuid()!=0, "server must not run as root"
print("PASS: settings, token decryption/key, database integrity, uploads, media and all persistent paths")
'''


def build(tag, version):
    run("docker", "build", "--build-arg", "BUILD_ARCH=amd64", "--build-arg", f"BUILD_VERSION={version}",
        "--tag", tag, str(ROOT / "soulsync"))
    config=json.loads(output("docker", "image", "inspect", tag))[0]["Config"]
    assert not config.get("Volumes"), "Anonymous upstream volumes would lose state on replacement"


def start(name, image, base):
    run("docker", "run", "-d", "--name", name, "--network", "none",
        "--mount", f"type=bind,source={base / 'data'},target=/data",
        "--mount", f"type=bind,source={base / 'media'},target=/media",
        "--mount", f"type=bind,source={base / 'share'},target=/share", image)
    for _ in range(120):
        state=json.loads(output("docker", "inspect", name))[0]
        if not state["State"]["Running"]:
            raise RuntimeError("SoulSync stopped: " + output("docker", "logs", name)[-9000:])
        health=subprocess.run(["docker", "exec", name, "curl", "-fsS", "-o", "/dev/null", "http://127.0.0.1:8008/"],
                              capture_output=True)
        if health.returncode==0:
            mounts={m["Destination"]:m["Type"] for m in state["Mounts"]}
            assert mounts=={"/data":"bind", "/media":"bind", "/share":"bind"}, mounts
            return
        time.sleep(2)
    raise RuntimeError("SoulSync did not become ready: " + output("docker", "logs", name)[-9000:])


def remove(name):
    run("docker", "stop", "--time", "20", name, stdout=subprocess.DEVNULL)
    run("docker", "rm", "-v", name, stdout=subprocess.DEVNULL)


def main():
    stamp=uuid.uuid4().hex[:10]
    name=f"soulsync-persistence-{stamp}"
    first=f"soulsync-ha-test:{stamp}"
    rebuilt=f"soulsync-ha-test:{stamp}-rebuilt"
    with tempfile.TemporaryDirectory(prefix="soulsync-ha-test-") as scratch:
        base=Path(scratch)
        for folder in ("data", "media", "share"):
            (base / folder).mkdir()
        (base / "data/options.json").write_text(json.dumps({"puid":1234,"pgid":1234,"umask":"002"}))
        try:
            build(first, "3.6.0-test")
            start(name, first, base)
            print(inside(name, SEED), flush=True)
            remove(name)
            # A fresh build and fresh container, not merely docker restart.
            build(rebuilt, "3.6.0-test-rebuild")
            start(name, rebuilt, base)
            print(inside(name, VERIFY), flush=True)
            remove(name)
            # Simulate HA's cold backup and restoring private /data elsewhere.
            archive=base / "state-backup.tar"
            with tarfile.open(archive, "w") as tar:
                tar.add(base / "data", arcname="data")
            restored=base / "restore"
            restored.mkdir()
            with tarfile.open(archive) as tar:
                tar.extractall(restored, filter="data")
            (restored / "media").symlink_to(base / "media", target_is_directory=True)
            (restored / "share").symlink_to(base / "share", target_is_directory=True)
            start(name, rebuilt, restored)
            print(inside(name, VERIFY), flush=True)
            remove(name)
            print("PASS: fresh boot, rebuilt-container replacement and cold-backup restore", flush=True)
        finally:
            subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)


if __name__=="__main__":
    main()
