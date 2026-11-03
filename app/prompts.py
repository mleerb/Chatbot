from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.core.config import PROMPT_DIR
from app.core.file_types import TEXT_EXTENSIONS

TEMPLATES = Environment(
    loader=FileSystemLoader(PROMPT_DIR, encoding="utf-8"),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)
TEMPLATES.globals["supported_text_extensions"] = tuple(sorted(TEXT_EXTENSIONS))


def render_prompt(filename: str, **values: object) -> str:
    return TEMPLATES.get_template(filename).render(**values).strip()
