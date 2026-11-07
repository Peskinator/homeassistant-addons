"""The server must never see a release whose image is unavailable."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("publish_app_image", Path(__file__).resolve().parents[1] / "scripts/publish_app_image.py")
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = self.root / "songmirror"
        self.app.mkdir()
        self.config = self.app / "config.yaml"
        self.original = 'name: SongMirror\nversion: "0.1.25"\noptions: {}\n'
        self.config.write_text(self.original)
        (self.app / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.25\n")
        self.root_patch = patch.object(publisher, "ROOT", self.root)
        self.root_patch.start()

    def tearDown(self):
        self.root_patch.stop()
        self.temp.cleanup()

    def test_versions_preserve_updater_formats(self):
        self.assertEqual(publisher.next_version("0.1.25"), "0.1.26")
        self.assertEqual(publisher.next_version("3.6.3-1"), "3.6.3-2")
        self.assertEqual(publisher.next_version("2.7.6-1"), "2.7.6-2")
        with self.assertRaises(ValueError):
            publisher.next_version("latest")

    def test_failed_build_or_push_leaves_manifest_unchanged(self):
        for failed_command in ("build", "push"):
            def run(command, **kwargs):
                if command[1] == failed_command:
                    raise subprocess.CalledProcessError(1, command)
            with patch.dict(os.environ, {"GITHUB_TOKEN":"test-only", "GITHUB_ACTOR":"test"}), patch.object(publisher.subprocess,"check_output",return_value="abc"), patch.object(publisher.subprocess,"run",side_effect=run), patch.object(publisher,"verify_public") as verify:
                with self.assertRaises(subprocess.CalledProcessError):
                    publisher.publish("songmirror", migrate=True)
                verify.assert_not_called()
            self.assertEqual(self.config.read_text(), self.original)

    def test_private_or_missing_image_is_never_advertised(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN":"test-only", "GITHUB_ACTOR":"test"}), patch.object(publisher.subprocess,"check_output",return_value="abc"), patch.object(publisher.subprocess,"run"), patch.object(publisher,"verify_public",side_effect=RuntimeError("private")):
            with self.assertRaisesRegex(RuntimeError,"no HA manifest was changed"):
                publisher.publish("songmirror", migrate=True)
        self.assertEqual(self.config.read_text(), self.original)

    def test_manifest_only_changes_after_pull_verification(self):
        commands=[]
        def run(command, **kwargs):
            commands.append(command[1])
            self.assertEqual(self.config.read_text(), self.original)
        def verify(image, version):
            self.assertEqual(commands, ["login", "build", "push"])
            self.assertEqual(version, "0.1.26")
            self.assertEqual(self.config.read_text(), self.original)
        with patch.dict(os.environ, {"GITHUB_TOKEN":"test-only", "GITHUB_ACTOR":"test"}), patch.object(publisher.subprocess,"check_output",return_value="abc"), patch.object(publisher.subprocess,"run",side_effect=run), patch.object(publisher,"verify_public",side_effect=verify):
            publisher.publish("songmirror", migrate=True)
        self.assertIn('version: "0.1.26"',self.config.read_text())
        self.assertIn('image: "ghcr.io/peskinator/ha-songmirror"',self.config.read_text())

    def test_migration_retry_does_not_bump_or_rebuild(self):
        self.config.write_text('version: "0.1.26"\nimage: "ghcr.io/peskinator/ha-songmirror"\n')
        with patch.object(publisher,"verify_public") as verify, patch.object(publisher.subprocess,"run") as run:
            self.assertFalse(publisher.publish("songmirror",migrate=True))
            verify.assert_called_once_with("ghcr.io/peskinator/ha-songmirror","0.1.26")
            run.assert_not_called()

    def test_upstream_update_keeps_the_version_selected_by_its_updater(self):
        self.config.write_text('version: "0.1.27"\nimage: "ghcr.io/peskinator/ha-songmirror"\n')
        with patch.dict(os.environ, {"GITHUB_TOKEN":"test-only", "GITHUB_ACTOR":"test"}), patch.object(publisher.subprocess,"check_output",return_value="abc"), patch.object(publisher.subprocess,"run") as run, patch.object(publisher,"verify_public") as verify:
            publisher.publish("songmirror")
            verify.assert_called_once_with("ghcr.io/peskinator/ha-songmirror", "0.1.27")
            self.assertIn("ghcr.io/peskinator/ha-songmirror:0.1.27",run.call_args_list[1].args[0])
        self.assertEqual(self.config.read_text(),'version: "0.1.27"\nimage: "ghcr.io/peskinator/ha-songmirror"\n')

    def test_arbitrary_app_or_existing_image_is_rejected(self):
        with self.assertRaises(ValueError): publisher.publish("../private")
        self.config.write_text(self.original+'image: "ghcr.io/someone/other"\n')
        with self.assertRaises(ValueError): publisher.publish("songmirror",migrate=True)


if __name__ == "__main__": unittest.main()
