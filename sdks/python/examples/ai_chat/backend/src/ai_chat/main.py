"""ASGI entrypoint; no provider or telemetry work occurs during import."""

from ai_chat.api.app import create_app
from ai_chat.bootstrap import build_application
from ai_chat.config import Settings

settings = Settings.from_environment()
app = create_app(
    application_factory=lambda: build_application(settings),
    image_directory=settings.image_directory,
    cors_origins=settings.cors_origins,
    telemetry=settings.telemetry,
)
