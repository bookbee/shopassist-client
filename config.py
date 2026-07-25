"""Central configuration.

Load order (later wins):
  1. config.yaml            — project defaults, checked into the repo
  2. environment / .env     — deployment overrides (API_BASE_URL, TIMEOUT, ...)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def _load_yaml() -> dict:
    cfg_path = PROJECT_ROOT / "config.yaml"
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        return {}


_raw = _load_yaml()
_app = _raw.get("app", {})
_api = _raw.get("api", {})
_colors = _raw.get("colors", {})


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable, app-wide settings resolved from YAML + environment."""

    app_title: str = os.getenv("APP_TITLE", _app.get("title", "IISc Alumni Store"))
    enable_chatbot: bool = _env_bool("ENABLE_CHATBOT", bool(_app.get("enable_chatbot", True)))
    log_level: str = os.getenv("LOG_LEVEL", _app.get("log_level", "INFO")).upper()

    api_base_url: str = os.getenv("API_BASE_URL", _api.get("base_url", "http://localhost:8000"))
    chat_endpoint: str = os.getenv("CHAT_ENDPOINT", _api.get("chat_endpoint", "/api/v1/chat"))
    timeout_seconds: float = float(os.getenv("TIMEOUT", _api.get("timeout_seconds", 10)))
    api_key: str = os.getenv("API_KEY", _api.get("api_key", ""))

    colors: dict = field(
        default_factory=lambda: {
            "primary": _colors.get("primary", "#5E1029"),
            "secondary": _colors.get("secondary", "#FFFFFF"),
            "accent": _colors.get("accent", "#C9A227"),
            "neutral": _colors.get("neutral", "#F5F2EC"),
        }
    )

    @property
    def chat_url(self) -> str:
        return self.api_base_url.rstrip("/") + self.chat_endpoint


settings = Settings()
