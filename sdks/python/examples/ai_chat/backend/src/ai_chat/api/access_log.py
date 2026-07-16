"""Access-log policy for operational endpoints."""

from __future__ import annotations

import logging

HEALTH_PATH = "/api/healthz"


class HealthCheckAccessLogFilter(logging.Filter):
    """Suppress successful Docker health probes from Uvicorn's access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        arguments = record.args
        if not isinstance(arguments, tuple) or len(arguments) < 5:
            return True
        path = arguments[2]
        status_code = arguments[4]
        return path != HEALTH_PATH or not isinstance(status_code, int) or status_code >= 400


def configure_access_logging() -> None:
    """Install the health-probe filter once on Uvicorn's access logger."""

    logger = logging.getLogger("uvicorn.access")
    if any(isinstance(item, HealthCheckAccessLogFilter) for item in logger.filters):
        return
    logger.addFilter(HealthCheckAccessLogFilter())
