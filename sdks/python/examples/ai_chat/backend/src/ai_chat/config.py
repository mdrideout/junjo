"""Explicit environment configuration for the runnable backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class TelemetrySettings:
    api_key: str
    host: str
    port: int
    insecure: bool


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    image_directory: Path
    cors_origins: tuple[str, ...]
    telemetry: TelemetrySettings | None

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
            for item in os.getenv("AI_CHAT_CORS_ORIGINS", "http://localhost:5173").split(",")
            if item.strip()
        )
        return cls(
            database_path=data_directory / "chat.sqlite3",
            image_directory=data_directory / "images",
            cors_origins=origins,
            telemetry=telemetry,
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
