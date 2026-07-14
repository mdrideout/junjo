"""ASGI entrypoint; no provider or telemetry work occurs during import."""

from ai_chat.api.app import create_app
from ai_chat.bootstrap import build_application
from ai_chat.config import Settings

settings = Settings.from_environment()
application = build_application(settings)
app = create_app(
    application=application,
    cors_origins=settings.cors_origins,
    telemetry=settings.telemetry,
)
