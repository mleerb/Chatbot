from app.prompts import render_prompt

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


def conversation_messages(question: str, history: list[dict], document_text: str = "",
                          image_url: str = "", filename: str = "") -> list[dict]:
    messages = []
    if document_text:
        messages.append({
            "role": "user",
            "content": render_prompt("document.j2", document_text=document_text),
        })
    if filename and not document_text and not image_url:
        messages.append({"role": "user", "content": render_prompt("unreadable.j2", upload_name=filename)})
    if image_url:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": render_prompt("image.j2", upload_name=filename)},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        })
    messages.extend({"role": item["role"], "content": item["content"]}
                    for item in history[-MAX_HISTORY_MESSAGES:])
    messages.append({"role": "user", "content": question})
    return messages
