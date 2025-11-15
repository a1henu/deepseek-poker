from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


API_KEY_FILE = Path(__file__).resolve().parent.parent / "APIKEY"


def _read_api_key_from_file() -> str | None:
    try:
        text = API_KEY_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return text or None


DEFAULT_MODEL = "deepseek-chat"
DEFAULT_URL = "https://api.deepseek.com/v1/chat/completions"
DEFAULT_STACK = 2000
DEFAULT_SMALL_BLIND = 10
DEFAULT_BIG_BLIND = 20
DEFAULT_MAX_ROOMS = 128


@dataclass(slots=True)
class Settings:
    deepseek_api_key: str | None
    deepseek_model: str = DEFAULT_MODEL
    deepseek_url: str = DEFAULT_URL
    starting_stack: int = DEFAULT_STACK
    small_blind: int = DEFAULT_SMALL_BLIND
    big_blind: int = DEFAULT_BIG_BLIND
    max_rooms: int = DEFAULT_MAX_ROOMS


def load_settings() -> Settings:
    api_key = os.getenv("DEEPSEEK_API_KEY") or _read_api_key_from_file()
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
    url = os.getenv("DEEPSEEK_API_URL", DEFAULT_URL)
    starting_stack = int(os.getenv("DEFAULT_STACK", DEFAULT_STACK))
    small_blind = int(os.getenv("DEFAULT_SMALL_BLIND", DEFAULT_SMALL_BLIND))
    big_blind = int(os.getenv("DEFAULT_BIG_BLIND", DEFAULT_BIG_BLIND))
    max_rooms = int(os.getenv("MAX_ROOMS", DEFAULT_MAX_ROOMS))
    return Settings(
        deepseek_api_key=api_key,
        deepseek_model=model,
        deepseek_url=url,
        starting_stack=starting_stack,
        small_blind=small_blind,
        big_blind=big_blind,
        max_rooms=max_rooms,
    )
