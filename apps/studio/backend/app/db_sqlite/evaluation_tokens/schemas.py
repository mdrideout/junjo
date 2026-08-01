"""Closed request and response contracts for evaluation-control tokens."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.common.datetime_utils import validate_aware_datetime
from app.db_sqlite.evaluation_tokens.models import MAX_TOKEN_NAME_BYTES

MAX_EVALUATION_TOKEN_PAGE_SIZE = 100
DEFAULT_EVALUATION_TOKEN_PAGE_SIZE = 50
MAX_EVALUATION_TOKEN_CURSOR_BYTES = 1_024


class EvaluationTokenScope(StrEnum):
    """Authorities supported by the evaluation control/query credential."""

    EVALUATION_READ = "evaluation:read"
    EVALUATION_WRITE = "evaluation:write"
    EVIDENCE_READ = "evidence:read"


SCOPE_ORDER = (
    EvaluationTokenScope.EVALUATION_READ,
    EvaluationTokenScope.EVALUATION_WRITE,
    EvaluationTokenScope.EVIDENCE_READ,
)


def _validate_name(value: str) -> str:
    if not value.strip():
        raise ValueError("name must not be blank")
    if value != value.strip():
        raise ValueError("name must not contain surrounding whitespace")
    if len(value.encode("utf-8", errors="strict")) > MAX_TOKEN_NAME_BYTES:
        raise ValueError(f"name must be at most {MAX_TOKEN_NAME_BYTES} UTF-8 bytes")
    return value


def _validate_cursor(value: str) -> str:
    if not value:
        raise ValueError("cursor must not be empty")
    if len(value.encode("utf-8", errors="strict")) > MAX_EVALUATION_TOKEN_CURSOR_BYTES:
        raise ValueError(f"cursor must be at most {MAX_EVALUATION_TOKEN_CURSOR_BYTES} UTF-8 bytes")
    return value


TokenName = Annotated[
    str,
    Field(min_length=1, max_length=MAX_TOKEN_NAME_BYTES),
    AfterValidator(_validate_name),
]
TokenCursor = Annotated[
    str,
    Field(min_length=1, max_length=MAX_EVALUATION_TOKEN_CURSOR_BYTES),
    AfterValidator(_validate_cursor),
]
TokenId = Annotated[str, Field(min_length=1, max_length=64)]


class EvaluationTokenContract(BaseModel):
    """Closed base contract for evaluation-token operations."""

    model_config = ConfigDict(extra="forbid")


class EvaluationTokenCreate(EvaluationTokenContract):
    name: TokenName
    scopes: list[EvaluationTokenScope] = Field(min_length=1, max_length=len(SCOPE_ORDER))
    expires_at: datetime | None = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(
        cls,
        scopes: list[EvaluationTokenScope],
    ) -> list[EvaluationTokenScope]:
        if len(set(scopes)) != len(scopes):
            raise ValueError("scopes must not contain duplicates")
        requested = set(scopes)
        return [scope for scope in SCOPE_ORDER if scope in requested]

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, expires_at: datetime | None) -> datetime | None:
        if expires_at is not None:
            return validate_aware_datetime(expires_at)
        return None


class EvaluationTokenRead(EvaluationTokenContract):
    id: TokenId
    name: TokenName
    token: str = Field(
        description="Recoverable bearer token managed by authenticated Studio users.",
        examples=["jcli_0123456789_abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOPQRSTUVWXYZ"],
    )
    scopes: list[EvaluationTokenScope]
    expires_at: datetime | None
    created_by_user_id: TokenId | None
    created_at: datetime


class EvaluationTokenList(EvaluationTokenContract):
    items: list[EvaluationTokenRead] = Field(max_length=MAX_EVALUATION_TOKEN_PAGE_SIZE)
    next_cursor: str | None
