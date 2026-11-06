import io
import json
import os
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import storage


class StorageOperationsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir(mode=0o700)
        self.identifier = "a" * 32
        self.target = self.workspace / "uploads" / self.identifier
        (self.target / "chunks").mkdir(parents=True, mode=0o700)
        (self.target / "extracted.txt").write_text("private synthetic text")
        (self.target / "chunks" / "001.txt").write_text("chunk")
        (self.workspace / "README.md").write_text("keep me")

    def quiet(self, function, *args, **kwargs):
        with redirect_stdout(io.StringIO()):
            return function(*args, **kwargs)

    def test_report_counts_bytes_without_exposing_contents(self):
        report = storage.workspace_report(self.workspace)
        self.assertEqual(report["snapshot_count"], 1)
        self.assertEqual(report["snapshot_bytes"], len(b"private synthetic textchunk"))
        self.assertEqual(report["snapshots"][0]["files"], 2)
        self.assertNotIn("private synthetic text", json.dumps(report))
        self.assertEqual(storage.workspace_report(self.root / "absent")["snapshot_count"], 0)

    def test_default_and_explicit_dry_run_never_prompt_or_delete(self):
        confirm = lambda _: self.fail("Dry-run must not prompt")
        self.quiet(storage.cleanup, self.workspace, [self.identifier], confirm=confirm)
        self.assertTrue(self.target.exists())
        with self.assertRaises(ValueError):
            self.quiet(storage.cleanup, self.workspace, [self.identifier], True, lambda _: "yes")
        self.assertTrue(self.target.exists())

    def test_confirmed_selection_only_deletes_selected_snapshots(self):
        other = self.workspace / "uploads" / ("b" * 32)
        other.mkdir()
        (other / "extracted.txt").write_text("retain")
        confirm = lambda prompt: prompt.split("Type ", 1)[1].split(" to delete", 1)[0]
        self.quiet(storage.cleanup, self.workspace, [self.identifier, self.identifier], True, confirm)
        self.assertFalse(self.target.exists())
        self.assertTrue(other.exists())
        self.assertTrue((self.workspace / "README.md").exists())

    def test_changed_snapshot_aborts_before_deletion(self):
        def confirm(prompt):
            (self.target / "new.txt").write_text("new")
            return prompt.split("Type ", 1)[1].split(" to delete", 1)[0]
        with self.assertRaisesRegex(ValueError, "changed"):
            self.quiet(storage.cleanup, self.workspace, [self.identifier], True, confirm)
        self.assertTrue(self.target.exists())

    def test_ids_traversal_and_absent_selection_are_refused(self):
        for identifier in ["../uploads", "a" * 31, "A" * 32, "c" * 32, "/tmp"]:
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                storage.snapshot_rows(self.workspace, [identifier])
        with self.assertRaises(ValueError):
            self.quiet(storage.cleanup, self.workspace, [])

    def test_symlinks_in_any_workspace_path_or_tree_are_refused(self):
        link = self.root / "link"
        link.symlink_to(self.workspace, target_is_directory=True)
        for root in [link, link / "uploads"]:
            with self.assertRaises(OSError):
                storage.workspace_report(root)
        (self.target / "outside").symlink_to(self.root)
        with self.assertRaises(ValueError):
            storage.snapshot_rows(self.workspace)
        (self.target / "outside").unlink()
        target = self.workspace / "uploads" / ("b" * 32)
        target.symlink_to(self.target, target_is_directory=True)
        with self.assertRaises(OSError):
            storage.snapshot_rows(self.workspace)

    def test_nonregular_workspace_entry_is_refused(self):
        os.mkfifo(self.target / "pipe")
        with self.assertRaises(ValueError):
            storage.snapshot_rows(self.workspace)

    def test_private_backup_archives_and_checksums_without_config_by_default(self):
        report = {"tables": {"chat_files": 3}}
        def compose(*args, **kwargs):
            kwargs["stdout"].write(b"synthetic-dump")
        with patch.object(storage, "database_report", return_value=report), patch.object(storage, "compose", side_effect=compose):
            path = self.quiet(storage.backup, self.root / "backups", self.workspace)
        self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        self.assertFalse((path / "INCOMPLETE").exists())
        self.assertFalse((path / "config.tar.gz").exists())
        for item in path.iterdir():
            self.assertEqual(item.stat().st_mode & 0o777, 0o600)
        manifest = json.loads((path / "manifest.json").read_text())
        with storage.directory(path) as descriptor:
            self.assertEqual(storage.digest_file(descriptor, "database.dump"), manifest["files"]["database.dump"])
            result = storage.check_archive(descriptor, "workspace.tar.gz")
        self.assertEqual(result["bytes"], len(b"private synthetic textchunkkeep me"))
        with tarfile.open(path / "workspace.tar.gz") as archive:
            self.assertEqual(archive.extractfile(f"workspace/uploads/{self.identifier}/extracted.txt").read(), b"private synthetic text")
            self.assertTrue(all(member.mode in (0o600, 0o700) for member in archive))

    def test_config_backup_is_explicit_and_secret_content_not_printed(self):
        config = self.root / "config"
        config.mkdir()
        (config / ".env").write_text("synthetic-secret")
        report = {"tables": {}}
        def compose(*args, **kwargs):
            kwargs["stdout"].write(b"dump")
        with patch.object(storage, "ROOT", config), patch.object(storage, "database_report", return_value=report), patch.object(storage, "compose", side_effect=compose):
            path = self.quiet(storage.backup, self.root / "backups", self.workspace, True)
        self.assertTrue((path / "config.tar.gz").exists())
        self.assertNotIn("synthetic-secret", (path / "manifest.json").read_text())

    def test_failed_dump_remains_marked_incomplete(self):
        with patch.object(storage, "database_report", return_value={}), patch.object(storage, "compose", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                self.quiet(storage.backup, self.root / "backups", self.workspace)
        child = next((self.root / "backups").iterdir())
        self.assertTrue((child / "INCOMPLETE").exists())
        self.assertFalse((child / "manifest.json").exists())

    def test_backup_refuses_nested_workspace_public_parent_and_symlink(self):
        with self.assertRaises(ValueError):
            self.quiet(storage.backup, self.workspace / "backups", self.workspace)
        public = self.root / "public"
        public.mkdir(mode=0o755)
        with self.assertRaises(ValueError):
            self.quiet(storage.backup, public, self.workspace)
        link = self.root / "link"
        link.symlink_to(public, target_is_directory=True)
        with self.assertRaises(OSError):
            self.quiet(storage.backup, link, self.workspace)

    def make_backup(self):
        report = {"tables": {"chat_files": 2}, "database_bytes": 1}
        def compose(*args, **kwargs):
            kwargs["stdout"].write(b"dump")
        with patch.object(storage, "database_report", return_value=report), patch.object(storage, "compose", side_effect=compose):
            return self.quiet(storage.backup, self.root / "backups", self.workspace)

    def test_verify_checks_archive_and_uses_no_production_mounts_or_ports(self):
        path = self.make_backup()
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            return b"container"
        with patch.object(storage, "run", side_effect=run), patch.object(storage, "database_report", return_value={"tables": {"chat_files": 2}, "database_bytes": 1}):
            result = self.quiet(storage.verify_backup, path)
        self.assertFalse(result["production_modified"])
        self.assertTrue(result["source_stable"])
        self.assertTrue(result["fingerprints_match"])
        self.assertGreater(result["archives"]["workspace.tar.gz"]["bytes"], 0)
        start = commands[0]
        self.assertIn("none", start)
        self.assertIn("--read-only", start)
        self.assertNotIn("-v", start)
        self.assertNotIn("--volume", start)
        self.assertNotIn("-p", start)
        self.assertIn("pg_restore", commands[2])
        self.assertEqual(commands[-1][:3], ["docker", "rm", "--force"])

    def test_verify_rejects_restored_fingerprint_mismatch_and_removes_container(self):
        path = self.make_backup()
        with patch.object(storage, "run", return_value=b"ready") as runner, patch.object(storage, "database_report", return_value={"different": True}):
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                self.quiet(storage.verify_backup, path)
        self.assertEqual(runner.call_args.args[0][:3], ["docker", "rm", "--force"])

    def test_verify_always_removes_disposable_container_on_restore_failure(self):
        path = self.make_backup()
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            if "pg_restore" in command:
                raise RuntimeError("restore failed")
            return b"container"
        with patch.object(storage, "run", side_effect=run), self.assertRaises(RuntimeError):
            self.quiet(storage.verify_backup, path)
        self.assertEqual(commands[-1][:3], ["docker", "rm", "--force"])

    def test_verify_rejects_tampering_and_incomplete_before_docker(self):
        path = self.make_backup()
        (path / "database.dump").write_bytes(b"tampered")
        with patch.object(storage, "run") as runner, self.assertRaises(ValueError):
            self.quiet(storage.verify_backup, path)
        runner.assert_not_called()
        (path / "INCOMPLETE").touch()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.quiet(storage.verify_backup, path)

    def test_archive_verification_refuses_links_and_traversal_without_extraction(self):
        for name, link in [("workspace/../outside", False), ("workspace/link", True)]:
            path = self.root / "unsafe.tar.gz"
            with tarfile.open(path, "w:gz") as archive:
                member = tarfile.TarInfo(name)
                if link:
                    member.type = tarfile.SYMTYPE
                    member.linkname = "/etc/passwd"
                archive.addfile(member)
            with storage.directory(self.root) as descriptor, self.assertRaises(ValueError):
                storage.check_archive(descriptor, path.name)

    def test_command_errors_never_expose_stderr(self):
        import subprocess
        with patch.object(storage.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "docker", stderr=b"private-secret")):
            with self.assertRaises(RuntimeError) as caught:
                storage.run(["docker"])
        self.assertNotIn("private-secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
