import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "reading_sessions.db"


def get_db_path() -> str:
    return str(DB_PATH)


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def get_llm_model(kind: str, explicit_model: str | None = None) -> str:
    if explicit_model:
        return explicit_model
    if kind == "grade":
        return os.environ.get("LLM_GRADE_MODEL") or os.environ.get("LLM_MODEL") or "gpt-4.1-mini"
    return os.environ.get("LLM_MODEL") or "gpt-4.1-mini"
