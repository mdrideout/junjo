"""ASGI entrypoint; no provider or telemetry work occurs during import."""

import logging

from ai_chat.api.app import create_app
from ai_chat.bootstrap import build_application
from ai_chat.config import Settings

application_logger = logging.getLogger("ai_chat")
if not application_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    application_logger.addHandler(handler)
application_logger.setLevel(logging.INFO)
application_logger.propagate = False

settings = Settings.from_environment()
app = create_app(
    application_factory=lambda: build_application(settings),
    image_directory=settings.image_directory,
    cors_origins=settings.cors_origins,
    telemetry=settings.telemetry,
)
