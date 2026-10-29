"""Protect the versioning that makes Home Assistant discover real updates."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location("soulsync_updater", Path(__file__).resolve().parents[1] / "scripts/sync_soulsync_upstream.py")
updater=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Path(self.temp.name)
        self.patch=patch.object(updater,"APP",self.app)
        self.patch.start()
        self.original=(f'ARG BUILD_SOULSYNC_VERSION="3.6.0"\n'
                       f'ARG BUILD_SOULSYNC_IMAGE="ghcr.io/nezreka/soulsync@sha256:{"a"*64}"\n'
                       f'FROM scratch\nARG BUILD_SOULSYNC_VERSION="3.6.0"\n')
        (self.app / "Dockerfile").write_text(self.original)
        (self.app / "config.yaml").write_text('version: "3.6.0-2"\n')
        (self.app / "CHANGELOG.md").write_text('# Changelog\n\n## 3.6.0-2\n')

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_unchanged_image_does_not_create_phantom_updates(self):
        self.assertFalse(updater.update("3.6.0","sha256:"+"a"*64))
        self.assertEqual((self.app / "Dockerfile").read_text(),self.original)

    def test_republished_stable_image_increases_wrapper_revision(self):
        self.assertTrue(updater.update("3.6.0","sha256:"+"b"*64))
        self.assertIn('version: "3.6.0-3"',(self.app / "config.yaml").read_text())

    def test_new_stable_release_starts_at_revision_one(self):
        self.assertTrue(updater.update("3.7.0","sha256:"+"b"*64))
        self.assertIn('version: "3.7.0-1"',(self.app / "config.yaml").read_text())
        self.assertEqual((self.app / "Dockerfile").read_text().count('BUILD_SOULSYNC_VERSION="3.7.0"'),2)

    def test_prerelease_downgrade_and_invalid_digest_leave_files_unchanged(self):
        for version,digest in (("3.7.0-beta","sha256:"+"b"*64),
                               ("3.5.0","sha256:"+"b"*64), ("3.7.0","not-a-digest")):
            with self.assertRaises((ValueError,RuntimeError)):
                updater.update(version,digest)
            self.assertEqual((self.app / "Dockerfile").read_text(),self.original)


if __name__=="__main__":
    unittest.main()
