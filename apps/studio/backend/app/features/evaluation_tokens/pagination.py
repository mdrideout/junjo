"""Opaque, route-bound keyset cursor for evaluation-token listings."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime

from app.common.datetime_utils import format_iso8601_utc, validate_aware_datetime
from app.db_sqlite.evaluation_tokens.schemas import MAX_EVALUATION_TOKEN_CURSOR_BYTES
from app.features.evaluation_tokens.contract import EvaluationTokenCursorError


@dataclass(frozen=True)
class EvaluationTokenCursorValue:
    created_at: datetime
    record_id: str


def encode_evaluation_token_cursor(cursor: EvaluationTokenCursorValue) -> str:
    raw = json.dumps(
        {
            "v": 1,
            "kind": "evaluation-tokens",
            "created_at": format_iso8601_utc(cursor.created_at),
            "id": cursor.record_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_evaluation_token_cursor(
    value: str | None,
) -> EvaluationTokenCursorValue | None:
    if value is None:
        return None
    try:
        if len(value.encode("utf-8")) > MAX_EVALUATION_TOKEN_CURSOR_BYTES:
            raise ValueError
        padded = value + ("=" * (-len(value) % 4))
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError
        if payload.get("v") != 1 or payload.get("kind") != "evaluation-tokens":
            raise ValueError
        created_at_value = payload["created_at"]
        record_id = payload["id"]
        if not isinstance(created_at_value, str) or not isinstance(record_id, str):
            raise ValueError
        created_at = validate_aware_datetime(datetime.fromisoformat(created_at_value))
        if not record_id:
            raise ValueError
    except (
        KeyError,
        TypeError,
        UnicodeDecodeError,
        UnicodeEncodeError,
        ValueError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise EvaluationTokenCursorError from error
    return EvaluationTokenCursorValue(created_at=created_at, record_id=record_id)
