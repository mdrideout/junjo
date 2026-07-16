"""Access-log policy for operational endpoints."""

from __future__ import annotations

import logging

HEALTH_PATH = "/api/healthz"


class HealthCheckAccessLogFilter(logging.Filter):
    """Suppress successful Docker health probes from Uvicorn's access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        arguments = record.args
        if not isinstance(arguments, tuple) or len(arguments) < 3:
            return True
        return arguments[2] != HEALTH_PATH


def configure_access_logging() -> None:
    """Install the health-probe filter once on Uvicorn's access logger."""

    logger = logging.getLogger("uvicorn.access")
    if any(isinstance(item, HealthCheckAccessLogFilter) for item in logger.filters):
        return
    logger.addFilter(HealthCheckAccessLogFilter())
