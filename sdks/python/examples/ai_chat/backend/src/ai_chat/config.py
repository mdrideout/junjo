"""Explicit environment configuration for the runnable backend."""

from __future__ import annotations

import math
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
class ServiceScope:
    """One authoritative OpenTelemetry and semantic-resolution service scope."""

    namespace: str
    name: str

    def __post_init__(self) -> None:
        if self.namespace != self.namespace.strip():
            raise ValueError("Service namespace cannot contain surrounding whitespace.")
        if not self.name.strip() or self.name != self.name.strip():
            raise ValueError("Service name must be non-empty without surrounding whitespace.")


APPLICATION_SERVICE_SCOPE = ServiceScope(
    namespace=STUDIO_SERVICE_NAMESPACE,
    name=STUDIO_SERVICE_NAME,
)


@dataclass(frozen=True, slots=True)
class TelemetrySettings:
    api_key: str
    endpoint: str
    insecure: bool


@dataclass(frozen=True, slots=True)
class StudioDiagnosticsSettings:
    frontend_base_url: str | None
    service_namespace: str = STUDIO_SERVICE_NAMESPACE
    service_name: str = STUDIO_SERVICE_NAME


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    image_directory: Path
    cors_origins: tuple[str, ...]
    telemetry: TelemetrySettings | None
    studio_diagnostics: StudioDiagnosticsSettings = StudioDiagnosticsSettings(frontend_base_url=None)
    model_provider: ModelProvider = ModelProvider.GEMINI
    gemini_api_key: str | None = None
    xai_api_key: str | None = None
    gemini_text_model: str = "gemini-3.7-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"
    grok_text_model: str = "grok-4.3"
    grok_image_model: str = "grok-imagine-image-quality"
    provider_timeout_seconds: float = 120.0

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
                endpoint=_non_empty(
                    os.getenv("JUNJO_AI_STUDIO_OTLP_ENDPOINT", "localhost:26155"),
                    "JUNJO_AI_STUDIO_OTLP_ENDPOINT",
                ),
                insecure=_boolean(
                    os.getenv("JUNJO_AI_STUDIO_OTLP_INSECURE", "true"),
                    "JUNJO_AI_STUDIO_OTLP_INSECURE",
                ),
            )
        origins = tuple(
            item.strip()
            for item in os.getenv("AI_CHAT_CORS_ORIGINS", "http://localhost:26251").split(",")
            if item.strip()
        )
        studio_frontend_base_url = None
        configured_frontend_base_url = os.getenv("JUNJO_AI_STUDIO_FRONTEND_BASE_URL")
        if telemetry is not None and configured_frontend_base_url is not None:
            studio_frontend_base_url = _http_origin(
                configured_frontend_base_url,
                "JUNJO_AI_STUDIO_FRONTEND_BASE_URL",
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
            studio_diagnostics=StudioDiagnosticsSettings(
                frontend_base_url=studio_frontend_base_url,
            ),
            model_provider=provider,
            gemini_api_key=gemini_api_key,
            xai_api_key=xai_api_key,
            gemini_text_model=os.getenv("AI_CHAT_GEMINI_TEXT_MODEL", "gemini-3.7-flash"),
            gemini_image_model=os.getenv("AI_CHAT_GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            grok_text_model=os.getenv("AI_CHAT_GROK_TEXT_MODEL", "grok-4.3"),
            grok_image_model=os.getenv("AI_CHAT_GROK_IMAGE_MODEL", "grok-imagine-image-quality"),
            provider_timeout_seconds=_positive_float(
                os.getenv("AI_CHAT_PROVIDER_TIMEOUT_SECONDS", "120"),
                "AI_CHAT_PROVIDER_TIMEOUT_SECONDS",
            ),
        )


def _boolean(value: str, name: str) -> bool:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{name} must be exactly true or false.")


def _non_empty(value: str, name: str) -> str:
    if not value.strip():
        raise ValueError(f"{name} cannot be empty.")
    if value != value.strip():
        raise ValueError(f"{name} cannot contain surrounding whitespace.")
    return value


def _positive_float(value: str, name: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a finite positive number.") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number.")
    return number


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
