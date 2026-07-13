"""Configuration endpoint for runtime settings."""

from fastapi import APIRouter

from app.config.settings import settings
from app.features.config.schemas import ConfigResponse

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.get("", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Get runtime configuration.

    Returns configuration values that the frontend needs to display,
    particularly the OTLP endpoint for SDK setup instructions.

    This endpoint is public (no authentication required) as it only
    exposes non-sensitive deployment configuration.
    """
    return ConfigResponse(
        environment=settings.junjo_env,
        otlp_endpoint=settings.otlp_endpoint,
        frontend_url=settings.prod_frontend_url,
        backend_url=settings.prod_backend_url,
    )
