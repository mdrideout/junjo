"""User Pydantic schemas for validation and serialization."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Schema for creating a user.

    Attributes:
        email: User email address
        password: Plain text password (min 8 characters)
    """

    email: EmailStr
    password: str = Field(..., min_length=8)


class UserRead(BaseModel):
    """Schema for reading a user (no password hash).

    Attributes:
        id: Unique user identifier
        email: User email address
        is_active: Whether the user account is active
        created_at: Timestamp when user was created
        updated_at: Timestamp when user was last updated
    """

    id: str = Field(
        examples=["usr_2k4h6j8m9n0p1q2r"],
        description="Unique user identifier",
    )
    email: EmailStr = Field(
        examples=["alice@example.com"],
        description="User email address",
    )
    is_active: bool = Field(
        examples=[True],
        description="Whether the user account is active",
    )
    created_at: datetime = Field(
        examples=["2025-01-15T10:30:00Z"],
        description="Timestamp when user was created",
    )
    updated_at: datetime = Field(
        examples=["2025-01-15T10:30:00Z"],
        description="Timestamp when user was last updated",
    )

    model_config = ConfigDict(from_attributes=True)


class UserInDB(UserRead):
    """Schema for user with password hash (internal use only).

    Attributes:
        password_hash: Hashed password (bcrypt)
    """

    password_hash: str


# Auth-specific schemas


class SignInRequest(BaseModel):
    """Schema for sign-in request."""

    email: EmailStr
    password: str


class CreateUserRequest(BaseModel):
    """Schema for user creation request (API endpoint)."""

    email: EmailStr
    password: str = Field(..., min_length=8)


class UserResponse(BaseModel):
    """Response after successful user operation."""

    message: str


class DbHasUsersResponse(BaseModel):
    """Response for db-has-users check."""

    users_exist: bool


class AuthTestResponse(BaseModel):
    """Response for auth-test endpoint."""

    user_email: EmailStr
