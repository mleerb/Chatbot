import base64
import os

from openai import OpenAI

PNG = b"\x89PNG\r\n\x1a\n"
SIZES = ("1024x1024", "1536x1024", "1024x1536")


def model():
    return os.getenv("IMAGE_MODEL", "").strip()


def available():
    return bool(model() and os.getenv("OPENAI_API_KEY", "").strip())


def default_size():
    size = os.getenv("IMAGE_SIZE", "").strip()
    return size if size in SIZES else SIZES[0]


def client():
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    if base_url and not base_url.startswith("https://"):
        raise ValueError("OPENAI_BASE_URL must be an HTTPS URL")
    return OpenAI(base_url=base_url or None, timeout=180)


def is_png(filename: str, data: bytes) -> bool:
    return filename.lower().endswith(".png") and data.startswith(PNG)


def generate(prompt: str, size: str | None = None) -> bytes:
    result = client().images.generate(
        model=model(),
        prompt=prompt,
        size=size if size in SIZES else default_size(),
        quality=os.getenv("IMAGE_QUALITY", "").strip() or "medium",
        output_format="png",
        n=1,
    )
    data = base64.b64decode(result.data[0].b64_json or "")
    if not data.startswith(PNG):
        raise ValueError("The image provider did not return a PNG image")
    return data
