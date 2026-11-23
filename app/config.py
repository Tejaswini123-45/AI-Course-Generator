"""Runtime configuration shared by HTTP and MCP."""

import os
from pathlib import Path

from dotenv import load_dotenv

MAX_TEXT_LENGTH = 60_000
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100


class ConfigurationError(Exception):
    """Required settings are missing."""


def gemini_settings() -> tuple[str, str]:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "").strip()
    if not api_key or not model:
        raise ConfigurationError("Set GEMINI_API_KEY and GEMINI_MODEL.")
    return api_key, model
