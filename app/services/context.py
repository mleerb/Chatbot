from app.prompts import render_prompt
from app.services.sessions import Upload

MAX_HISTORY_MESSAGES = 12


def response_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return str(content)


def conversation_messages(question: str, history: list[dict],
                          uploads: list[Upload] | None = None) -> list[dict]:
    messages = []
    for item in uploads or []:
        messages.append({
            "role": "user",
            "content": render_prompt("upload.j2", upload_name=item.filename, file_id=item.id),
        })
        if item.document:
            messages.append({
                "role": "user",
                "content": render_prompt("document.j2", document_text=item.document),
            })
        if not item.document and not item.image_url:
            messages.append({
                "role": "user",
                "content": render_prompt("unreadable.j2", upload_name=item.filename),
            })
        if item.image_url:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": render_prompt("image.j2", upload_name=item.filename)},
                    {"type": "image_url", "image_url": {"url": item.image_url}},
                ],
            })
    messages.extend({"role": item["role"], "content": item["content"]}
                    for item in history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": question})
    return messages
