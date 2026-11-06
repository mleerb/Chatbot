import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"[0-9a-f]{32}")
TABLES = ("chat_users", "chat_accounts", "chat_conversations", "chat_messages", "chat_files", "chat_usage")
REPORT_SQL = """
SELECT json_build_object(
  'database_bytes', pg_database_size(current_database()),
  'tables', (SELECT json_object_agg(name, rows) FROM (
    SELECT 'chat_users' AS name, count(*) AS rows FROM chat_users
    UNION ALL SELECT 'chat_accounts', count(*) FROM chat_accounts
    UNION ALL SELECT 'chat_conversations', count(*) FROM chat_conversations
    UNION ALL SELECT 'chat_messages', count(*) FROM chat_messages
    UNION ALL SELECT 'chat_files', count(*) FROM chat_files
    UNION ALL SELECT 'chat_usage', count(*) FROM chat_usage
  ) AS counts),
  'files', (SELECT coalesce(json_agg(t), '[]'::json) FROM (
    SELECT kind, count(*) AS count, coalesce(sum(octet_length(data)), 0) AS binary_bytes,
      coalesce(sum(octet_length(document)), 0) AS document_bytes,
      coalesce(sum(octet_length(embeddings)), 0) AS embedding_bytes,
      coalesce(sum(octet_length(pages::text)), 0) AS pages_json_bytes
    FROM chat_files GROUP BY kind ORDER BY kind
  ) AS t),
  'messages', (SELECT json_build_object(
    'content_bytes', coalesce(sum(octet_length(content)), 0),
    'sources_json_bytes', coalesce(sum(octet_length(sources::text)), 0),
    'attachments_json_bytes', coalesce(sum(octet_length(attachments::text)), 0)
  ) FROM chat_messages)
);
"""


def run(arguments, *, timeout=600, stdin=None, stdout=subprocess.PIPE):
    try:
        return subprocess.run(arguments, cwd=ROOT, stdin=stdin, stdout=stdout,
                              stderr=subprocess.PIPE, check=True, timeout=timeout).stdout
    except (subprocess.SubprocessError, OSError):
        raise RuntimeError("Operator command failed or timed out; private command output was withheld") from None


def compose(*arguments, **kwargs):
    return run(["docker", "compose", *arguments], **kwargs)


FINGERPRINT_SQL = "SELECT json_build_object(" + ",".join(
    f"'{table}', (SELECT json_build_object('rows', count(*), 'digest', md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY {('user_id' if table == 'chat_usage' else 'id')}), ''))) FROM {table} AS t)"
    for table in TABLES
) + ");"


def database_report(container=None, timeout=600, fingerprint=False):
    sql = FINGERPRINT_SQL if fingerprint else REPORT_SQL
    if container:
        result = run(["docker", "exec", container, "psql", "-X", "-U", "aster_verify", "-d", "aster_verify",
                      "-v", "ON_ERROR_STOP=1", "-At", "-c", sql], timeout=timeout)
    else:
        result = compose("exec", "-T", "db", "sh", "-c",
                         'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At -c "$1"',
                         "storage", sql, timeout=timeout)
    return json.loads(result)


@contextmanager
def directory(path):
    path = Path(os.path.abspath(path))
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


@contextmanager
def child_directory(parent, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def inventory(descriptor, prefix=""):
    entries = []
    for name in sorted(os.listdir(descriptor)):
        info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        key = f"{prefix}{name}"
        if stat.S_ISDIR(info.st_mode):
            with child_directory(descriptor, name) as child:
                entries.extend(inventory(child, key + "/"))
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError("Refusing symlinks and non-regular workspace entries")
        entries.append((key, info.st_dev, info.st_ino, info.st_size if stat.S_ISREG(info.st_mode) else 0,
                        info.st_mtime_ns, stat.S_ISDIR(info.st_mode)))
    return entries


def snapshot_rows(root, identifiers=None):
    with directory(root) as workspace:
        try:
            with child_directory(workspace, "uploads") as uploads:
                selected = sorted(set(identifiers)) if identifiers is not None else sorted(os.listdir(uploads))
                rows = []
                for identifier in selected:
                    if not IDENTIFIER.fullmatch(identifier):
                        if identifiers is not None:
                            raise ValueError("Select exact 32-character lowercase hexadecimal snapshot IDs")
                        raise ValueError("Unexpected entry in uploads; inspect manually")
                    with child_directory(uploads, identifier) as target:
                        entries = inventory(target)
                        info = os.fstat(target)
                    rows.append({"id": identifier, "bytes": sum(item[3] for item in entries),
                                 "files": sum(not item[5] for item in entries),
                                 "fingerprint": hashlib.sha256(json.dumps(
                                     [info.st_dev, info.st_ino, entries]).encode()).hexdigest()})
                return rows
        except FileNotFoundError:
            if identifiers:
                raise ValueError("Selected snapshot or uploads directory does not exist") from None
            return []


def workspace_report(root):
    if not Path(root).exists() and not Path(root).is_symlink():
        return {"exists": False, "snapshot_count": 0, "snapshot_bytes": 0, "workspace_bytes": 0}
    rows = snapshot_rows(root)
    with directory(root) as descriptor:
        entries = inventory(descriptor)
    return {"exists": True, "snapshot_count": len(rows), "snapshot_bytes": sum(row["bytes"] for row in rows),
            "workspace_bytes": sum(item[3] for item in entries), "snapshots": rows}


def cleanup(root, identifiers, delete=False, confirm=input):
    if not identifiers:
        raise ValueError("Select at least one explicit snapshot ID; bulk age/all selection is not supported")
    rows = snapshot_rows(root, identifiers)
    print(json.dumps({"mode": "delete" if delete else "dry-run", "snapshots": rows,
                      "bytes": sum(row["bytes"] for row in rows)}, indent=2))
    print("Back up the database and workspace first. Snapshot deletion is permanent and does not remove database files.")
    if not delete:
        return rows
    token = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:16]
    phrase = f"DELETE {token}"
    if confirm(f"Type {phrase} to delete only the snapshots listed above: ") != phrase:
        raise ValueError("Confirmation did not match; nothing deleted")
    if snapshot_rows(root, identifiers) != rows:
        raise ValueError("Selected snapshots changed; nothing deleted. Run dry-run again")
    if not shutil.rmtree.avoids_symlink_attacks:
        raise RuntimeError("Safe directory deletion is not supported on this platform")
    with directory(root) as workspace, child_directory(workspace, "uploads") as uploads:
        for row in rows:
            with child_directory(uploads, row["id"]) as target:
                info = os.fstat(target)
                entries = inventory(target)
                fingerprint = hashlib.sha256(json.dumps([info.st_dev, info.st_ino, entries]).encode()).hexdigest()
                if fingerprint != row["fingerprint"]:
                    raise ValueError("Snapshot changed during deletion; stopped. Some earlier selections may be removed")
            shutil.rmtree(row["id"], dir_fd=uploads)
    print(f"Deleted {len(rows)} explicitly selected snapshot(s). Database and other workspace entries were not changed.")
    return rows


def private_file(parent, name):
    descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    return os.fdopen(descriptor, "wb")


def archive_tree(archive, descriptor, prefix):
    for name in sorted(os.listdir(descriptor)):
        info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        member = tarfile.TarInfo(f"{prefix}/{name}")
        member.mtime = int(info.st_mtime)
        if stat.S_ISDIR(info.st_mode):
            member.type, member.mode = tarfile.DIRTYPE, 0o700
            archive.addfile(member)
            with child_directory(descriptor, name) as child:
                archive_tree(archive, child, member.name)
        elif stat.S_ISREG(info.st_mode):
            member.mode, member.size = 0o600, info.st_size
            source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
            with os.fdopen(source, "rb") as stream:
                before = os.fstat(stream.fileno())
                if (before.st_dev, before.st_ino, before.st_size) != (info.st_dev, info.st_ino, info.st_size):
                    raise ValueError("Workspace changed during backup; retry while uploads are idle")
                archive.addfile(member, stream)
                after = os.fstat(stream.fileno())
                if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                    raise ValueError("Workspace changed during backup; retry while uploads are idle")
        else:
            raise ValueError("Refusing symlinks and non-regular backup entries")


def digest_file(parent, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Backup must contain regular files only")
        return {"sha256": hashlib.file_digest(stream, "sha256").hexdigest(),
                "bytes": os.fstat(stream.fileno()).st_size}


def make_directory(path):
    path = Path(os.path.abspath(path))
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)


def backup(destination, workspace, include_config=False, timeout=600):
    destination = Path(os.path.abspath(destination))
    workspace = Path(os.path.abspath(workspace))
    if destination == workspace or workspace in destination.parents:
        raise ValueError("Backup destination must be outside the workspace")
    make_directory(destination)
    with directory(destination) as parent:
        if os.fstat(parent).st_mode & 0o077:
            raise ValueError("Backup parent directory must be private (0700)")
        name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
        os.mkdir(name, mode=0o700, dir_fd=parent)
        with child_directory(parent, name) as output:
            with private_file(output, "INCOMPLETE") as marker:
                marker.write(b"Do not restore until manifest.json exists and verification succeeds.\n")
            before = database_report(timeout=timeout, fingerprint=True)
            with private_file(output, "database.dump") as stream:
                compose("exec", "-T", "db", "sh", "-c",
                        'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc', stdout=stream, timeout=timeout)
            names = ["database.dump"]
            if workspace.exists() or workspace.is_symlink():
                with directory(workspace) as source, private_file(output, "workspace.tar.gz") as stream:
                    initial = inventory(source)
                    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                        archive_tree(archive, source, "workspace")
                    if inventory(source) != initial:
                        raise ValueError("Workspace changed during backup; retry while uploads are idle")
                names.append("workspace.tar.gz")
            if include_config:
                with directory(ROOT) as source, private_file(output, "config.tar.gz") as stream:
                    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                        for filename in (".env", ".docker.env", "compose.yaml", "compose.override.yaml", "compose.workspace.yaml"):
                            try:
                                descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=source)
                            except FileNotFoundError:
                                continue
                            with os.fdopen(descriptor, "rb") as config:
                                info = os.fstat(config.fileno())
                                if not stat.S_ISREG(info.st_mode):
                                    raise ValueError("Private configuration must be a regular file")
                                member = tarfile.TarInfo("config/" + filename)
                                member.mode, member.size = 0o600, info.st_size
                                archive.addfile(member, config)
                names.append("config.tar.gz")
            manifest = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                        "files": {name: digest_file(output, name) for name in names},
                        "source_before": before, "source_after": database_report(timeout=timeout, fingerprint=True),
                        "warning": "Private data and password hashes; configuration archive may include provider secrets. Database and workspace are not one atomic snapshot."}
            with private_file(output, "manifest.json") as stream:
                stream.write(json.dumps(manifest, indent=2).encode())
            os.unlink("INCOMPLETE", dir_fd=output)
    print(f"Private backup completed: {destination / name}")
    print("Contains private content and password hashes. Keep encrypted/off-host copies; never publish or commit.")
    return destination / name


def check_archive(parent, name):
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    seen = set()
    total = 0
    with os.fdopen(descriptor, "rb") as stream, tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            parts = member.name.split("/")
            if member.name in seen or any(part in ("", ".", "..") for part in parts) or member.name.startswith("/"):
                raise ValueError("Unsafe or duplicate archive entry")
            seen.add(member.name)
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Archive contains a link or unsupported entry")
            with archive.extractfile(member) as content:
                consumed = 0
                while chunk := content.read(1024 * 1024):
                    consumed += len(chunk)
                if consumed != member.size:
                    raise ValueError("Truncated archive")
            total += member.size
    return {"entries": len(seen), "bytes": total}


def verify_backup(path, timeout=600, memory_mb=1024):
    with directory(path) as parent:
        descriptor = os.open("manifest.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(descriptor, "rb") as stream:
            manifest = json.load(stream)
        names = set(manifest.get("files", {}))
        if manifest.get("version") != 1 or "database.dump" not in names or not names <= {
            "database.dump", "workspace.tar.gz", "config.tar.gz"
        }:
            raise ValueError("Unsupported backup manifest")
        if "INCOMPLETE" in os.listdir(parent):
            raise ValueError("Backup is incomplete")
        for name in sorted(names):
            if digest_file(parent, name) != manifest["files"][name]:
                raise ValueError("Backup checksum mismatch")
        archives = {name: check_archive(parent, name) for name in sorted(names) if name.endswith(".tar.gz")}
        container = "aster-restore-" + uuid.uuid4().hex
        started = False
        try:
            run(["docker", "run", "--detach", "--pull", "never", "--name", container, "--network", "none",
                 "--memory", f"{memory_mb}m", "--cpus", "1", "--read-only",
                 "--tmpfs", f"/var/lib/postgresql/data:rw,nosuid,nodev,size={memory_mb}m",
                 "--tmpfs", "/var/run/postgresql:rw,nosuid,nodev,size=16m",
                 "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
                 "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_USER=aster_verify",
                 "-e", "POSTGRES_DB=aster_verify", "postgres:17"], timeout=timeout)
            started = True
            deadline = time.monotonic() + min(timeout, 90)
            while True:
                try:
                    run(["docker", "exec", container, "pg_isready", "-q", "-U", "aster_verify", "-d", "aster_verify"], timeout=10)
                    break
                except RuntimeError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Disposable restore database did not become ready") from None
                    time.sleep(0.5)
            descriptor = os.open("database.dump", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            with os.fdopen(descriptor, "rb") as stream:
                run(["docker", "exec", "-i", container, "pg_restore", "-U", "aster_verify", "-d", "aster_verify",
                     "--no-owner", "--no-privileges", "--exit-on-error"], stdin=stream, timeout=timeout)
            restored = database_report(container, timeout)
            fingerprints = database_report(container, timeout, fingerprint=True)
            stable = manifest["source_before"] == manifest["source_after"]
            if stable and fingerprints != manifest["source_before"]:
                raise ValueError("Restored data fingerprint differs from the stable source")
            report = {"restored": restored, "source_stable": stable,
                      "fingerprints_match": fingerprints == manifest["source_before"] if stable else None,
                      "warning": None if stable else "Source changed during backup; restore succeeded but source equality is not asserted. Repeat while idle.",
                      "archives": archives,
                      "production_modified": False, "workspace_extracted": False}
            print(json.dumps(report, indent=2))
            return report
        finally:
            try:
                run(["docker", "rm", "--force", container], timeout=60)
            except RuntimeError:
                if started:
                    raise RuntimeError(f"Could not remove disposable container {container}; remove this exact container manually") from None


def positive_integer(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description="Local operator-only storage and recovery; no automatic cleanup")
    parser.add_argument("--workspace", type=Path, default=ROOT / ".workspace")
    parser.add_argument("--timeout", type=positive_integer, default=600)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("report")
    clean = commands.add_parser("cleanup")
    clean.add_argument("--snapshot", action="append", required=True)
    mode = clean.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--delete", action="store_true")
    save = commands.add_parser("backup")
    save.add_argument("--destination", type=Path, default=ROOT / "backups")
    save.add_argument("--include-config", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("backup", type=Path)
    verify.add_argument("--memory-mb", type=positive_integer, default=1024)
    args = parser.parse_args()
    try:
        if args.command == "report":
            print(json.dumps({"database": database_report(timeout=args.timeout),
                              "workspace": workspace_report(args.workspace),
                              "note": "Logical byte totals overlap extracted text/pages; physical DB size includes indexes, TOAST and overhead. Guest RAM, Docker images/cache and backups are excluded."}, indent=2))
        elif args.command == "cleanup":
            cleanup(args.workspace, args.snapshot, args.delete)
        elif args.command == "backup":
            backup(args.destination, args.workspace, args.include_config, args.timeout)
        elif args.command == "verify":
            verify_backup(args.backup, args.timeout, args.memory_mb)
    except (OSError, ValueError, RuntimeError, EOFError, tarfile.TarError):
        print("Operation failed or was refused; no private command output shown. Check selected paths, permissions, confirmation, Docker health and available space. Failed backups retain INCOMPLETE; deletion may have stopped after earlier selections. Inspect any aster-restore-* containers after an interrupted verification and remove only the exact disposable container, never application volumes.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
