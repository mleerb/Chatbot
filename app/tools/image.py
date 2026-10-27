import logging
import re
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.services import guest, images, quota, storage
from app.services.sessions import Download, sessions, sessions_lock

logger = logging.getLogger(__name__)


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000,
                        description="A detailed visual description of the one image to create, based on the user's request")
    filename: str = Field(description="A short descriptive filename ending in .png, such as watercolor-cat.png")
    size: Literal["1024x1024", "1536x1024", "1024x1536"] | None = Field(
        default=None, description="1024x1024 square, 1536x1024 landscape or 1024x1536 portrait; omit for the default")


def image_filename(filename: str) -> str:
    stem = re.sub(r"\.png$", "", filename.strip(), flags=re.IGNORECASE)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-_")[:60]
    return f"{stem or 'image'}.png"


def create_image_tool(token: str):
    @tool(
        args_schema=ImageRequest,
        description="Create one PNG image from a text description and show it to the user under your answer. Use it when the user asks for a picture, drawing, illustration, logo, icon or photo-like image. Each call creates one image and counts against the user's daily image limit, so call it once per image the user asked for.",
    )
    def generate_image(prompt: str, filename: str, size: str | None = None) -> str:
        with sessions_lock:
            session = sessions.get(token)
        if session is None:
            return "Session expired; no image was created."
        if not (guest.take_image(session) if session.guest else quota.take_image(session.user_id)):
            return quota.IMAGE_LIMIT_MESSAGE

        def release():
            try:
                if session.guest:
                    guest.release_image(session)
                else:
                    quota.release_image(session.user_id)
            except Exception:
                logger.exception("Could not release the image count")

        try:
            data = images.generate(prompt, size)
        except Exception:
            logger.exception("Image generation failed")
            release()
            return "Image generation failed; no image was created. Tell the user it did not work and suggest trying again."
        item = Download(image_filename(filename), data)
        try:
            storage.save_generated(session, item)
        except Exception:
            logger.exception("Could not save the generated image")
            release()
            return "Could not save the image; no image was created."
        session.generated[item.id] = item
        return (f"Created image {item.filename} (file_id={item.id}). The app shows it under your answer; "
                "describe it briefly and do not add image links or Markdown images.")

    return generate_image
