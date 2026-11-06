import io
import json
import os
import tempfile
import time
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import storage


@unittest.skipUnless(os.getenv("TEST_STORAGE_RECOVERY") == "1", "Requires explicit disposable Docker recovery opt-in")
class RecoveryTests(unittest.TestCase):
    def test_synthetic_files_sources_and_password_hash_restore(self):
        container = "aster-recovery-source-" + uuid.uuid4().hex
        try:
            storage.run(["docker", "run", "-d", "--pull", "never", "--name", container, "--network", "none",
                         "--read-only", "--memory", "512m", "--cpus", "1",
                         "--tmpfs", "/var/lib/postgresql/data:rw,size=256m",
                         "--tmpfs", "/var/run/postgresql:rw,size=16m", "--tmpfs", "/tmp:rw,size=16m",
                         "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_USER=aster_verify",
                         "-e", "POSTGRES_DB=aster_verify", "postgres:17"])
            for attempt in range(90):
                try:
                    storage.run(["docker", "exec", container, "pg_isready", "-q", "-U", "aster_verify", "-d", "aster_verify"], timeout=5)
                    break
                except RuntimeError:
                    if attempt == 89:
                        raise
                    time.sleep(0.5)
            sql = """
CREATE TABLE chat_users (id bigint PRIMARY KEY, name text);
CREATE TABLE chat_accounts (id bigint PRIMARY KEY, user_id bigint REFERENCES chat_users(id), password_hash text);
CREATE TABLE chat_conversations (id bigint PRIMARY KEY, user_id bigint REFERENCES chat_users(id), title text);
CREATE TABLE chat_messages (id bigint PRIMARY KEY, content text, sources jsonb, attachments jsonb);
CREATE TABLE chat_files (id bigint PRIMARY KEY, kind text, data bytea, document text, embeddings bytea, pages jsonb);
CREATE TABLE chat_usage (user_id bigint PRIMARY KEY REFERENCES chat_users(id), tokens bigint);
INSERT INTO chat_users VALUES (1, 'synthetic');
INSERT INTO chat_accounts VALUES (1, 1, 'synthetic-password-hash');
INSERT INTO chat_conversations VALUES (1, 1, 'Synthetic recovery');
INSERT INTO chat_messages VALUES (1, 'Synthetic message', '[{"text":"synthetic immutable citation"}]', '[{"id":"synthetic"}]');
INSERT INTO chat_files VALUES
 (1, 'upload', decode('00ff1234', 'hex'), 'Vietnamese: kiểm thử', NULL, '[["page 1","source text"]]'),
 (2, 'revision', decode('010203', 'hex'), 'edited source', decode('aabbcc', 'hex'), '[]'),
 (3, 'generated', decode('89504e47', 'hex'), '', NULL, '[]');
INSERT INTO chat_usage VALUES (1, 42);
"""
            storage.run(["docker", "exec", container, "psql", "-X", "-U", "aster_verify", "-d", "aster_verify",
                         "-v", "ON_ERROR_STOP=1", "-c", sql])
            report_function = storage.database_report
            def report(container_override=None, timeout=600, fingerprint=False):
                return report_function(container_override or container, timeout, fingerprint)
            def dump(*args, **kwargs):
                return storage.run(["docker", "exec", container, "pg_dump", "-U", "aster_verify", "-d", "aster_verify", "-Fc"],
                                   stdout=kwargs["stdout"], timeout=kwargs["timeout"])
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                workspace = root / "workspace"
                target = workspace / "uploads" / ("a" * 32)
                target.mkdir(parents=True)
                (target / "extracted.txt").write_text("synthetic snapshot")
                with patch.object(storage, "database_report", side_effect=report), patch.object(storage, "compose", side_effect=dump), redirect_stdout(io.StringIO()):
                    path = storage.backup(root / "backups", workspace)
                with redirect_stdout(io.StringIO()):
                    restored = storage.verify_backup(path, memory_mb=512)
                self.assertTrue(restored["source_stable"])
                self.assertTrue(restored["fingerprints_match"])
                self.assertEqual(restored["restored"]["tables"]["chat_files"], 3)
                self.assertEqual([row["kind"] for row in restored["restored"]["files"]], ["generated", "revision", "upload"])
                self.assertGreater(restored["restored"]["messages"]["sources_json_bytes"], 10)
                self.assertEqual(restored["archives"]["workspace.tar.gz"]["bytes"], len(b"synthetic snapshot"))
                self.assertTrue((target / "extracted.txt").exists())
                self.assertEqual(json.loads((path / "manifest.json").read_text())["source_before"]["chat_files"]["rows"], 3)
        finally:
            storage.run(["docker", "rm", "--force", container], timeout=60)


if __name__ == "__main__":
    unittest.main()
