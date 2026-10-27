import hashlib
import json
import logging
import os
import struct

import numpy as np
import tiktoken
from openai import OpenAI

logger = logging.getLogger(__name__)
DIMENSIONS = 512
VERSION = 1
BATCH_SIZE = 32
MAX_TOKENS = 8000
QUERY_CACHE_SIZE = 32


def settings() -> tuple[str, str]:
    return os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(), os.getenv("OPENAI_BASE_URL", "").strip()


def available() -> bool:
    return bool(settings()[0] and os.getenv("OPENAI_API_KEY", "").strip())


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize(vectors):
    matrix = np.asarray(vectors, dtype="<f4")
    if matrix.ndim != 2 or matrix.shape[1] != DIMENSIONS or not np.isfinite(matrix).all():
        raise ValueError("Invalid embedding dimensions or values")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if (norms <= 0).any():
        raise ValueError("Empty embedding vector")
    return matrix / norms


def request(texts: list[str], config: tuple[str, str]):
    model, base_url = config
    if base_url and not base_url.startswith("https://"):
        raise ValueError("OPENAI_BASE_URL must be an HTTPS URL")
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks, owners, weights = [], [], []
    for number, text in enumerate(texts):
        tokens = encoding.encode(text, disallowed_special=())
        if not tokens:
            raise ValueError("Cannot embed empty text")
        for start in range(0, len(tokens), MAX_TOKENS):
            chunk = tokens[start:start + MAX_TOKENS]
            chunks.append(chunk)
            owners.append(number)
            weights.append(len(chunk))
    totals = np.zeros((len(texts), DIMENSIONS), dtype="<f4")
    with OpenAI(base_url=base_url or None, timeout=20, max_retries=1) as client:
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start:start + BATCH_SIZE]
            response = client.embeddings.create(model=model, input=batch, dimensions=DIMENSIONS, encoding_format="float")
            ordered = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in ordered] != list(range(len(batch))):
                raise ValueError("Incomplete embedding response")
            vectors = normalize([item.embedding for item in ordered])
            for offset, vector in enumerate(vectors):
                index = start + offset
                totals[owners[index]] += vector * weights[index]
    return normalize(totals)


def pack(config: tuple[str, str], hashes: list[str], vectors) -> bytes:
    matrix = normalize(vectors)
    if len(hashes) != len(matrix):
        raise ValueError("Embedding page count mismatch")
    metadata = json.dumps({"version": VERSION, "model": config[0], "provider": config[1],
                           "dimensions": DIMENSIONS, "hashes": hashes}, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(metadata)) + metadata + matrix.astype("<f4").tobytes()


def unpack(blob: bytes | None, config: tuple[str, str]):
    if not blob:
        return None
    try:
        size = struct.unpack("<I", blob[:4])[0]
        metadata = json.loads(blob[4:4 + size])
        if (metadata["version"], metadata["model"], metadata["provider"], metadata["dimensions"]) != (
            VERSION, config[0], config[1], DIMENSIONS
        ):
            return None
        hashes = metadata["hashes"]
        if not isinstance(hashes, list) or not all(isinstance(value, str) for value in hashes):
            return None
        matrix = np.frombuffer(blob, dtype="<f4", offset=4 + size).reshape(len(hashes), DIMENSIONS)
        norms = np.linalg.norm(matrix, axis=1)
        if not np.isfinite(matrix).all() or not np.allclose(norms, 1, atol=0.001):
            return None
        return hashes, matrix
    except (ValueError, KeyError, TypeError, struct.error):
        return None


def build(page_list, previous: bytes | None = None, config: tuple[str, str] | None = None) -> bytes | None:
    if not available() or not page_list:
        return None
    config = config or settings()
    hashes = [text_hash(page.text) for page in page_list]
    old = unpack(previous, config)
    reusable = dict(zip(*old)) if old is not None else {}
    missing = list(dict.fromkeys(value for value in hashes if value not in reusable))
    if missing:
        by_hash = {text_hash(page.text): page.text for page in page_list}
        reusable.update(zip(missing, request([by_hash[value] for value in missing], config)))
    return pack(config, hashes, [reusable[value] for value in hashes])


def prepare(item) -> bool:
    from app.services.pages import is_large

    if not available() or not is_large(item) or not item.pages:
        return False
    with item.embedding_lock:
        config = settings()
        page_list = item.pages
        old = unpack(item.embeddings, config)
        hashes = [text_hash(page.text) for page in page_list]
        if old is not None and old[0] == hashes:
            return False
        try:
            blob = build(page_list, item.embeddings, config)
        except Exception:
            logger.warning("File embeddings unavailable; retaining keyword search")
            return False
        if item.pages is page_list and settings() == config:
            item.embeddings = blob
            item.embeddings_dirty = True
            return True
        return False


def query_vector(session, query: str, config: tuple[str, str]):
    key = (*config, query)
    with session.embedding_query_lock:
        if key in session.embedding_queries:
            session.embedding_queries.move_to_end(key)
            return session.embedding_queries[key]
        vector = request([query], config)[0]
        session.embedding_queries[key] = vector
        while len(session.embedding_queries) > QUERY_CACHE_SIZE:
            session.embedding_queries.popitem(last=False)
        return vector


def cosine(matrix, vector):
    return matrix @ vector
