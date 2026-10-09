import os

from langchain_openai import ChatOpenAI


def chat_model():
    model = os.getenv("CHAT_MODEL", "openai:gpt-4o-mini").strip()
    if not model:
        raise ValueError("CHAT_MODEL must not be empty")

    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url:
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Set OPENAI_API_KEY in .env for the configured gateway")
        if not base_url.startswith("https://"):
            raise ValueError("OPENAI_BASE_URL must be an HTTPS URL")
        return ChatOpenAI(model=model, base_url=base_url)

    if model.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY in .env")
    return model
