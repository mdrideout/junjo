"""API Key Pydantic schemas for validation and serialization."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.common.datetime_utils import format_iso8601_utc, validate_aware_datetime


class APIKeyCreate(BaseModel):
    """Schema for creating an API key.

    Attributes:
        name: Human-readable name for the key
    """

    name: str = Field(..., min_length=1)


class APIKeyRead(BaseModel):
    """Schema for reading an API key.

    Attributes:
        id: Unique identifier
        key: API key value (64-char alphanumeric)
        name: Human-readable name
        created_at: Timestamp when key was created
    """

    id: str = Field(
        examples=["key_9x7v6u5t4s3r2q1p"],
        description="Unique identifier",
    )
    key: str = Field(
        examples=["sk_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2"],
        description="API key value (64-char alphanumeric)",
    )
    name: str = Field(
        examples=["Production API Key"],
        description="Human-readable name",
    )
    created_at: datetime = Field(
        examples=["2025-01-15T10:30:00Z"],
        description="Timestamp when key was created (UTC)",
    )

    model_config = ConfigDict(from_attributes=True)

    # Validator: Reject naive datetimes
    @field_validator("created_at", mode="before")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware."""
        if isinstance(v, datetime):
            return validate_aware_datetime(v)
        return v

    # Serializer: Always output ISO 8601 with 'Z' suffix
    @field_serializer("created_at")
    def serialize_datetime(self, dt: datetime) -> str:
        """Serialize datetime as ISO 8601 with 'Z' suffix."""
        return format_iso8601_utc(dt)
