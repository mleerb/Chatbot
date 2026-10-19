from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = APP_DIR.parent
PROMPT_DIR = APP_DIR / "prompts"

load_dotenv(ROOT_DIR / ".env")
