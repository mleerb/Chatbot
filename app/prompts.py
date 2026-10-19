from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.core.config import PROMPT_DIR

TEMPLATES = Environment(
    loader=FileSystemLoader(PROMPT_DIR, encoding="utf-8"),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


def render_prompt(filename: str, **values: str) -> str:
    return TEMPLATES.get_template(filename).render(**values).strip()
