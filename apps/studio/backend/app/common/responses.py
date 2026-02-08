"""
Standard API response models.

Provides consistent response formats across all endpoints.
Uses Pydantic v2+ conventions.
"""

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    """Health check response"""

    status: str = Field(default="ok", description="Health status")
    version: str = Field(default="0.80.0", description="API version")
    app_name: str = Field(description="Application name")

    model_config = ConfigDict(frozen=True)  # Immutable response


class ErrorResponse(BaseModel):
    """Error response"""

    error: str = Field(description="Error message")
    detail: str | None = Field(default=None, description="Detailed error information")


class SuccessResponse[T](BaseModel):
    """Generic success response with data"""

    success: bool = Field(default=True)
    data: T = Field(description="Response data")
