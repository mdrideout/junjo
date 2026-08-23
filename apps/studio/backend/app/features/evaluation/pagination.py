"""Opaque, route-bound keyset cursors for evaluation list endpoints."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.common.datetime_utils import format_iso8601_utc, validate_aware_datetime
from app.features.evaluation.contract import EvaluationCursorError
from app.features.evaluation.schemas import MAX_CURSOR_BYTES


@dataclass(frozen=True)
class TimeCursor:
    created_at: datetime
    record_id: str


@dataclass(frozen=True)
class MembershipCursor:
    role: Literal["case_source", "attempt_subject"]
    record_id: str


def _encode(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(value: str) -> dict[str, object]:
    try:
        if len(value.encode("utf-8")) > MAX_CURSOR_BYTES:
            raise ValueError
        padded = value + ("=" * (-len(value) % 4))
        raw = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw)
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        ValueError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise EvaluationCursorError from error
    if not isinstance(payload, dict):
        raise EvaluationCursorError
    return payload


def encode_time_cursor(kind: Literal["datasets", "runs"], cursor: TimeCursor) -> str:
    return _encode(
        {
            "v": 1,
            "kind": kind,
            "created_at": format_iso8601_utc(cursor.created_at),
            "id": cursor.record_id,
        }
    )


def decode_time_cursor(
    kind: Literal["datasets", "runs"],
    value: str | None,
) -> TimeCursor | None:
    if value is None:
        return None
    payload = _decode(value)
    try:
        if payload.get("v") != 1 or payload.get("kind") != kind:
            raise ValueError
        created_at_value = payload["created_at"]
        record_id = payload["id"]
        if not isinstance(created_at_value, str) or not isinstance(record_id, str):
            raise ValueError
        created_at = validate_aware_datetime(datetime.fromisoformat(created_at_value))
        if not record_id:
            raise ValueError
    except (KeyError, TypeError, ValueError) as error:
        raise EvaluationCursorError from error
    return TimeCursor(created_at=created_at, record_id=record_id)


def encode_membership_cursor(cursor: MembershipCursor) -> str:
    return _encode(
        {
            "v": 1,
            "kind": "evidence-membership",
            "role": cursor.role,
            "id": cursor.record_id,
        }
    )


def decode_membership_cursor(value: str | None) -> MembershipCursor | None:
    if value is None:
        return None
    payload = _decode(value)
    try:
        role = payload["role"]
        record_id = payload["id"]
        if (
            payload.get("v") != 1
            or payload.get("kind") != "evidence-membership"
            or role not in ("case_source", "attempt_subject")
            or not isinstance(record_id, str)
            or not record_id
        ):
            raise ValueError
    except (KeyError, ValueError) as error:
        raise EvaluationCursorError from error
    return MembershipCursor(role=role, record_id=record_id)
