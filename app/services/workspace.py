import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import ROOT_DIR
from app.services import embed
from app.services.pages import INLINE_TOKENS, MAX_PAGE_CHARS, PAGE_CHARS, estimate_tokens, is_large

logger = logging.getLogger(__name__)


def enabled(session) -> bool:
    return (os.getenv("WORKSPACE_EXPORT_ENABLED", "false").lower() == "true"
            and (session.user_id is not None or (
                session.guest and os.getenv("WORKSPACE_EXPORT_GUESTS", "false").lower() == "true"
            )))


def private_write(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)


def export_upload(session, item, inspection: dict) -> None:
    if not enabled(session):
        return
    try:
        if re.fullmatch(r"[0-9a-f]{32}", item.id) is None:
            raise ValueError("Invalid upload identifier")
        root = Path(os.getenv("WORKSPACE_EXPORT_DIR", str(ROOT_DIR / ".workspace"))).absolute()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or root.stat().st_mode & 0o077:
            raise ValueError("Workspace directory must be private and not a symlink")
        uploads = root / "uploads"
        uploads.mkdir(mode=0o700, exist_ok=True)
        if uploads.is_symlink() or uploads.stat().st_mode & 0o077:
            raise ValueError("Upload workspace must be private and not a symlink")
        target = uploads / item.id
        target.mkdir(mode=0o700)
        chunks = target / "chunks"
        chunks.mkdir(mode=0o700)
        entries = []
        for number, page in enumerate(item.pages, 1):
            filename = f"chunks/{number:03d}.txt"
            private_write(target / filename, page.text)
            entries.append({"number": number, "label": page.label, "file": filename,
                            "characters": len(page.text), "estimated_tokens": estimate_tokens(page.text),
                            "sha256": embed.text_hash(page.text)})
        parser = inspection.get("parser", "unknown")
        embedding_status = "ready" if item.embeddings else (
            "not_needed" if not is_large(item) or not item.pages else (
                "unavailable" if not embed.available() else "failed_or_unavailable"
            )
        )
        manifest = {
            "version": 1, "upload_id": item.id, "filename": item.filename,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "user_id": session.user_id, "conversation_id": session.conversation_id,
            "session_kind": "guest" if session.guest else "account",
            "original_bytes": len(item.data), "parser": parser, "status": item.status,
            "extracted_characters": len(inspection.get("extracted", item.document)),
            "context_characters": len(item.document), "chunk_count": len(entries),
            "context_mode": "on_demand" if is_large(item) else "inline",
            "inline_token_threshold": INLINE_TOKENS,
            "split_max_characters": MAX_PAGE_CHARS if parser == "llamaparse" else PAGE_CHARS,
            "source_pages": inspection.get("source_pages", []), "chunks": entries,
        }
        steps = [
            {"step": "extract", "parser": parser, "result": inspection.get("parse_result", "unknown")},
            {"step": "split", "result": "complete", "chunk_count": len(entries),
             "strategy": "source_pages_with_parts" if parser == "llamaparse" else "paragraph_line_space"},
            {"step": "embed", "result": embedding_status, "model": embed.settings()[0],
             "dimensions": embed.DIMENSIONS if item.embeddings else None},
            {"step": "persist", "result": "guest_upload_in_memory" if session.guest else "account_upload_saved"},
            {"step": "context", "result": manifest["context_mode"]},
        ]
        private_write(target / "extracted.txt", inspection.get("extracted", item.document))
        private_write(target / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        private_write(target / "steps.json", json.dumps(steps, ensure_ascii=False, indent=2))
    except Exception:
        logger.warning("Could not export upload inspection workspace")
