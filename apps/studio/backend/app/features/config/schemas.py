"""Configuration endpoint schemas."""

from pydantic import BaseModel, Field


class ConfigResponse(BaseModel):
    """Runtime configuration response.

    Exposes configuration that frontend needs to display to users,
    particularly for SDK setup (OTLP endpoint).
    """

    environment: str = Field(description="Current environment (development/production)")
    otlp_endpoint: str = Field(description="OTLP ingestion endpoint for OpenTelemetry SDKs")
    frontend_url: str | None = Field(default=None, description="Frontend URL (production only)")
    backend_url: str | None = Field(default=None, description="Backend URL (production only)")
