# Storage and recovery

`scripts/storage.py` is a host-side, operator-only tool using Python 3.11+ standard-library modules and the Docker CLI. Run it from this repository on Linux as the owner of the private workspace. It is not a chat tool, HTTP endpoint, scheduled job or database migration. It adds no environment settings and makes no model/parser/embedding requests. Normal Compose configuration, including the private workspace override, remains unchanged. Production database commands target the running Compose `db` service, not a shell-supplied URL. A stopped database causes failure rather than silently switching databases.

## Read-only report

```bash
python3 scripts/storage.py report
python3 scripts/storage.py --workspace /absolute/private/workspace report
```

The report shows total physical PostgreSQL database size; aggregate user/account/conversation/message/file/usage row counts; binary, document, embedding and page-JSON byte totals grouped by original upload, revision or generated file; message content/source/attachment JSON sizes; and workspace bytes plus snapshot IDs/counts/bytes. It does not print messages, filenames, account identities, passwords, provider settings or extracted text. Snapshot IDs and aggregate counts may still be sensitive operational metadata. Do not publish reports.

Logical sizes overlap: extracted text can appear in both `document` and `pages`, with further copies in immutable citation sources. Database size includes indexes, TOAST, free space and other overhead; logical totals are not reclaimable-disk estimates. Workspace totals include audits/README as well as snapshots; only `uploads/<id>` snapshots are cleanup candidates. Guest live RAM, Docker images/cache, volumes for other projects and backups are outside this report. There is no comprehensive storage quota or automatic reclamation policy.

## Private backup

First ensure adequate free disk space and ask users to pause uploads, edits and chat writes. The database dump is transactionally consistent, but database and workspace/config archives are not one cross-system atomic snapshot. Workspace modifications detected while copying abort the backup; a file created just after the archive finishes may still fall outside that archive. For a strict maintenance backup, stop new traffic and wait for in-flight requests to finish before running it. Do not stop/delete PostgreSQL or its volume.

```bash
python3 scripts/storage.py backup
python3 scripts/storage.py --timeout 1800 backup --include-config
```

Default output is a uniquely named directory under Git-ignored `backups/`, mode 0700, with files mode 0600:

- `database.dump`: PostgreSQL 17 custom-format dump, including stored uploads, revisions, generated files, message citation snapshots, accounts and password hashes.
- `workspace.tar.gz`: the entire chosen workspace when present, including retained guest inspection copies and audit artifacts; no symlinks or special entries are accepted.
- `config.tar.gz`: only with explicit `--include-config`; copies existing `.env`, `.docker.env`, `compose.yaml`, `compose.override.yaml` and `compose.workspace.yaml`. This can contain provider/database secrets. It does not include external secret stores, TLS keys, arbitrary source documents or Langfuse-hosted data.
- `manifest.json`: version, creation time, checksums/sizes and before/after aggregate per-table fingerprints. No table contents or secrets are printed or included in the manifest. Fingerprints use ordered row hashes to detect accidental changes, not cryptographic authentication.
- `INCOMPLETE`: retained on failure; do not restore a backup with this marker. Failed directories are never automatically deleted. Investigate private logs locally and manually remove only a known failed backup if desired.

No backups are encrypted automatically. They contain private messages, documents and password hashes; the configuration archive also contains credentials. Never commit, upload publicly or share them. Make an encrypted off-host copy and retain the source code/lockfiles or a matching release separately for disaster recovery. File permissions protect against other unprivileged host users, not root/Docker administrators. `backups/` and common SQL/dump extensions are Git-ignored; arbitrary archive names elsewhere are not guaranteed ignored. Check before committing. Use a mode-0700 destination outside the repository for off-repository copies:

```bash
python3 scripts/storage.py backup --destination "$HOME/leminh/chatbot-backups"
```

The destination cannot be inside the workspace. Existing public destination directories, symlinks in directory paths and special archive entries are refused. Do not run cleanup or rename workspace directories concurrently with backup. Backup may read all database rows to compute fingerprints; reserve time/resources for larger installations. `--timeout` controls each Docker subprocess, not the whole backup or local archive-copy duration.

## Validate recovery without overwriting production

```bash
python3 scripts/storage.py --timeout 1800 verify backups/REPLACE_WITH_BACKUP_DIRECTORY
```

Verification first rejects incomplete backups, unsupported manifests and checksum mismatches. It reads all archive entries without extracting anything, refusing traversal, duplicate names, links and special entries. It then restores `database.dump` with `pg_restore --exit-on-error --no-owner --no-privileges` into a new randomly named `aster-restore-*` PostgreSQL 17 container. It has no network, published port or production volume/bind mount; its database is on disposable tmpfs with a read-only root filesystem. Local trust authentication is used only inside that network-isolated disposable container, never production. The cached `postgres:17` image is required; verification never pulls images automatically.

The tool reports restored row counts/logical sizes. When source fingerprints were unchanged across backup, it requires the restored table fingerprints to match. If source data changed during backup, it explicitly does not assert source equality; repeat while idle. Empty production tables alone do not prove file recovery, so a separate gated synthetic integration test covers binary uploads, revisions, generated files, Unicode text, embeddings, citation JSON, password-hash fields and usage.

Default container memory and database tmpfs capacity are each 1024 MiB. This is not a promise that a 1 GiB database fits: PostgreSQL consumes memory in addition to tmpfs. Increase capacity deliberately for larger backups; for example `verify PATH --memory-mb 4096`. The tool limits CPU to one. Host swap behavior follows Docker/host configuration; tmpfs is not a guarantee against host-level swapping or administrator access. The container is removed in a `finally` block; Ctrl-C normally reaches that block, but host/process termination or Docker failure can leave `aster-restore-*` behind. Inspect and remove only that exact disposable container. Never remove application volumes or run broad Docker prune commands as part of this procedure.

Verification trusts that the operator selected a locally produced backup; checksums detect accidental corruption, not malicious replacement of both data and manifest. Restoring SQL can execute database-side code, so do not verify untrusted dumps. The tool does not perform a production restore, restore configuration, extract workspace archives or test browser login against restored data. Recovery after an actual incident must be a separately approved maintenance operation: preserve current storage first, restore into a new private PostgreSQL 17 instance, restore workspace/config into separate private staging directories, inspect ownership/settings and application compatibility, then explicitly switch the stack after validation. Never extract configuration over live credentials or restore on top of the running production database without a recovery plan.

To inspect a trusted archive, use `tar -tzf BACKUP/workspace.tar.gz` locally; listings may reveal private filenames. A manual workspace restore into a new empty mode-0700 staging directory can use `tar --no-same-owner --no-same-permissions -xzf BACKUP/workspace.tar.gz -C STAGING` after successful verification. The archive contains a `workspace/` prefix. Restrict the restored directory tree to 0700 and regular files to 0600 before use. Do not serve staged files over HTTP. Archive contents were read/validated in Phase 3; automatic extraction/production cutover are intentionally not implemented.

## Manual snapshot cleanup

Back up first. Cleanup only removes explicitly selected inspection snapshots under `uploads/`; it never removes database files, accounts, conversations, generated downloads, audit directories, reports, secrets, backups or Docker volumes. Snapshot deletion does not erase copies retained in earlier backups, citations or external providers. It is permanent and does not have an undo command.

Use exact lowercase 32-character hexadecimal IDs from the storage report. There is no `--all`, age cutoff, cron task, retention timer or noninteractive bypass. Repeating `--snapshot` selects several IDs; duplicates are collapsed.

```bash
python3 scripts/storage.py cleanup --snapshot REPLACE_WITH_EXACT_SNAPSHOT_ID --dry-run
python3 scripts/storage.py cleanup --snapshot REPLACE_WITH_EXACT_SNAPSHOT_ID --delete
```

Without `--delete`, cleanup is always a dry-run and does not prompt. Deletion prints the selected IDs/bytes, recommends backup, then requires typing the exact `DELETE <selection-token>` phrase. EOF, mismatch, invalid/missing IDs, symlink paths or unsupported entries fail closed. The selection fingerprint binds the confirmation to inspected file identity/size/mtime; changes after preview are rechecked before deletion. Linux descriptor-relative, symlink-resistant directory operations prevent following symlinks into other directories. This is an operator tool, not a defense against a malicious process with the same UID or root changing directories during deletion. Run during an idle maintenance window and do not run competing cleanup jobs. Multiple deletions are not transactional: filesystem/permission failure can stop after earlier selected snapshots have already been deleted. Rerun the read-only report to inspect remaining entries.

No existing inspection snapshots were deleted during Phase 3; destructive tests used only temporary synthetic fixtures. Account and guest exports remain persistently enabled on this machine.

## Tests

```bash
python3 -m unittest discover -s tests -p test_storage_ops.py
TEST_STORAGE_RECOVERY=1 python3 -m unittest discover -s tests -p test_recovery.py -v
```

The second command is an explicit opt-in: it creates two disposable network-isolated PostgreSQL 17 containers with tmpfs only, runs synthetic backup/restore and removes those containers. It never uses production Compose credentials or data. The normal backend suite skips this integration test. For Docker backend discovery, additionally mount `"$PWD/scripts:/app/scripts:ro"` so host-side operator unit tests are importable. The operator script is intentionally not included in the backend image or exposed to agent tools.
