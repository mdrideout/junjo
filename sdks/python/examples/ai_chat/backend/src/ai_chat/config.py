"""Explicit environment configuration for the runnable backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
STUDIO_SERVICE_NAMESPACE = "junjo.examples"
STUDIO_SERVICE_NAME = "ai-chat"


class ModelProvider(StrEnum):
    """Explicit runtime adapter selected at the composition root."""

    GEMINI = "gemini"
    GROK = "grok"


@dataclass(frozen=True, slots=True)
class TelemetrySettings:
    api_key: str
    host: str
    port: int
    insecure: bool


@dataclass(frozen=True, slots=True)
class DebugSettings:
    enabled: bool
    studio_ui_url: str | None
    service_namespace: str = STUDIO_SERVICE_NAMESPACE
    service_name: str = STUDIO_SERVICE_NAME


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    image_directory: Path
    cors_origins: tuple[str, ...]
    telemetry: TelemetrySettings | None
    debug: DebugSettings = DebugSettings(enabled=False, studio_ui_url=None)
    model_provider: ModelProvider = ModelProvider.GEMINI
    gemini_api_key: str | None = None
    xai_api_key: str | None = None
    gemini_text_model: str = "gemini-3.5-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"
    grok_text_model: str = "grok-4.3"
    grok_image_model: str = "grok-imagine-image-quality"

    @classmethod
    def from_environment(cls) -> Settings:
        data_directory = Path(os.getenv("AI_CHAT_DATA_DIRECTORY", _BACKEND_ROOT / "runtime-data")).resolve()
        api_key = os.getenv("JUNJO_AI_STUDIO_API_KEY")
        telemetry = None
        if api_key is not None:
            if not api_key.strip():
                raise ValueError("JUNJO_AI_STUDIO_API_KEY cannot be empty when configured.")
            telemetry = TelemetrySettings(
                api_key=api_key,
                host=os.getenv("JUNJO_AI_STUDIO_HOST", "localhost"),
                port=_port(os.getenv("JUNJO_AI_STUDIO_PORT", "26155")),
                insecure=_boolean(
                    os.getenv("JUNJO_AI_STUDIO_INSECURE", "true"),
                    "JUNJO_AI_STUDIO_INSECURE",
                ),
            )
        origins = tuple(
            item.strip()
            for item in os.getenv("AI_CHAT_CORS_ORIGINS", "http://localhost:26251").split(",")
            if item.strip()
        )
        debug_enabled = _boolean(os.getenv("AI_CHAT_DEBUG", "false"), "AI_CHAT_DEBUG")
        studio_ui_url = None
        if debug_enabled:
            studio_ui_url = _http_origin(
                os.getenv("AI_CHAT_STUDIO_UI_URL", "http://localhost:26153"),
                "AI_CHAT_STUDIO_UI_URL",
            )
        provider = ModelProvider(os.getenv("AI_CHAT_MODEL_PROVIDER", ModelProvider.GEMINI.value).casefold())
        gemini_api_key = _optional_secret("GEMINI_API_KEY")
        xai_api_key = _optional_secret("XAI_API_KEY")
        if provider is ModelProvider.GEMINI and gemini_api_key is None:
            raise ValueError("GEMINI_API_KEY is required for the gemini provider.")
        if provider is ModelProvider.GROK and xai_api_key is None:
            raise ValueError("XAI_API_KEY is required for the grok provider.")
        return cls(
            database_path=data_directory / "chat-v3.sqlite3",
            image_directory=data_directory / "images",
            cors_origins=origins,
            telemetry=telemetry,
            debug=DebugSettings(
                enabled=debug_enabled,
                studio_ui_url=studio_ui_url,
            ),
            model_provider=provider,
            gemini_api_key=gemini_api_key,
            xai_api_key=xai_api_key,
            gemini_text_model=os.getenv("AI_CHAT_GEMINI_TEXT_MODEL", "gemini-3.5-flash"),
            gemini_image_model=os.getenv("AI_CHAT_GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            grok_text_model=os.getenv("AI_CHAT_GROK_TEXT_MODEL", "grok-4.3"),
            grok_image_model=os.getenv("AI_CHAT_GROK_IMAGE_MODEL", "grok-imagine-image-quality"),
        )


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError("JUNJO_AI_STUDIO_PORT must be an integer.") from exc
    if not 1 <= port <= 65_535:
        raise ValueError("JUNJO_AI_STUDIO_PORT must be between 1 and 65535.")
    return port


def _boolean(value: str, name: str) -> bool:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{name} must be exactly true or false.")


def _http_origin(value: str, name: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} must be an absolute HTTP origin.")
    return f"{parsed.scheme}://{parsed.netloc}"


def _optional_secret(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    if not value.strip():
        raise ValueError(f"{name} cannot be empty when configured.")
    return value
