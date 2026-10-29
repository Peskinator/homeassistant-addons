"""Protect the versioning that makes Home Assistant discover real updates."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location("slskd_updater", Path(__file__).resolve().parents[1] / "scripts/sync_slskd_upstream.py")
updater=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Path(self.temp.name)
        self.patch=patch.object(updater,"APP",self.app)
        self.patch.start()
        self.original=(f'ARG BUILD_SLSKD_VERSION="0.26.2"\n'
                       f'ARG BUILD_SLSKD_IMAGE="ghcr.io/slskd/slskd@sha256:{"a"*64}"\n'
                       f'FROM scratch\nARG BUILD_SLSKD_VERSION="0.26.2"\n')
        (self.app / "Dockerfile").write_text(self.original)
        (self.app / "config.yaml").write_text('version: "0.26.2-2"\n')
        (self.app / "CHANGELOG.md").write_text('# Changelog\n\n## 0.26.2-2\n')

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_unchanged_image_does_not_create_phantom_updates(self):
        self.assertFalse(updater.update("0.26.2","sha256:"+"a"*64))
        self.assertEqual((self.app / "Dockerfile").read_text(),self.original)

    def test_republished_stable_image_increases_wrapper_revision(self):
        self.assertTrue(updater.update("0.26.2","sha256:"+"b"*64))
        self.assertIn('version: "0.26.2-3"',(self.app / "config.yaml").read_text())

    def test_new_stable_release_starts_at_revision_one(self):
        self.assertTrue(updater.update("0.27.0","sha256:"+"b"*64))
        self.assertIn('version: "0.27.0-1"',(self.app / "config.yaml").read_text())
        self.assertEqual((self.app / "Dockerfile").read_text().count('BUILD_SLSKD_VERSION="0.27.0"'),2)

    def test_prerelease_downgrade_and_invalid_digest_leave_files_unchanged(self):
        for version,digest in (("0.27.0-beta","sha256:"+"b"*64),
                               ("0.25.0","sha256:"+"b"*64), ("0.27.0","not-a-digest")):
            with self.assertRaises((ValueError,RuntimeError)):
                updater.update(version,digest)
            self.assertEqual((self.app / "Dockerfile").read_text(),self.original)


if __name__=="__main__":
    unittest.main()
