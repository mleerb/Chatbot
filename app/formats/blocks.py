import json


def structured_content(content: str, key: str) -> list:
    try:
        payload = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Supply JSON with a '{key}' array for this format.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise ValueError(f"Supply JSON with a '{key}' array for this format.")
    return payload[key]


def table_rows(block: dict) -> list[list]:
    rows = block.get("rows")
    if (not isinstance(rows, list) or not rows or not isinstance(rows[0], list)
            or not rows[0] or not all(
                isinstance(row, list) and len(row) == len(rows[0])
                and all(isinstance(cell, (str, int, float)) for cell in row)
                for row in rows
            )):
        raise ValueError("Table rows must be equally sized lists of text or numbers.")
    return rows


def document_blocks(content: str) -> list[dict]:
    try:
        payload = json.loads(content)
    except ValueError:
        return [{"type": "paragraph", "text": line} for line in content.split("\n")]
    if isinstance(payload, dict) and isinstance(payload.get("blocks"), list):
        return payload["blocks"]
    return [{"type": "paragraph", "text": line} for line in content.split("\n")]
