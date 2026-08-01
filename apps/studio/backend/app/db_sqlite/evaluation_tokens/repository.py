"""Async SQLite repository for evaluation-control tokens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, or_, select

from app.db_sqlite import db_config
from app.db_sqlite.evaluation_tokens.models import EvaluationTokenTable
from app.db_sqlite.evaluation_tokens.schemas import (
    EvaluationTokenList,
    EvaluationTokenRead,
    EvaluationTokenScope,
)
from app.db_sqlite.users.models import UserTable
from app.features.evaluation_tokens.pagination import (
    EvaluationTokenCursorValue,
    decode_evaluation_token_cursor,
    encode_evaluation_token_cursor,
)


@dataclass(frozen=True)
class EvaluationTokenAuthenticationRecord:
    """Credential material required for one read-only authentication check."""

    id: str
    token: str
    scopes: frozenset[EvaluationTokenScope]
    expires_at: datetime | None
    user_id: str
    user_email: str
    user_is_active: bool


def _scopes(row: EvaluationTokenTable) -> list[EvaluationTokenScope]:
    return [
        scope
        for scope, enabled in (
            (EvaluationTokenScope.EVALUATION_READ, row.evaluation_read),
            (EvaluationTokenScope.EVALUATION_WRITE, row.evaluation_write),
            (EvaluationTokenScope.EVIDENCE_READ, row.evidence_read),
        )
        if enabled
    ]


def _read(row: EvaluationTokenTable) -> EvaluationTokenRead:
    return EvaluationTokenRead(
        id=row.id,
        name=row.name,
        token=row.token,
        scopes=_scopes(row),
        expires_at=row.expires_at,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
    )


class EvaluationTokenRepository:
    """Single-purpose database operations for scoped evaluation tokens."""

    @staticmethod
    async def create(
        *,
        name: str,
        token: str,
        scopes: frozenset[EvaluationTokenScope],
        expires_at: datetime | None,
        created_by_user_id: str,
    ) -> EvaluationTokenRead:
        row = EvaluationTokenTable(
            name=name,
            token=token,
            evaluation_read=EvaluationTokenScope.EVALUATION_READ in scopes,
            evaluation_write=EvaluationTokenScope.EVALUATION_WRITE in scopes,
            evidence_read=EvaluationTokenScope.EVIDENCE_READ in scopes,
            expires_at=expires_at,
            created_by_user_id=created_by_user_id,
        )
        async with db_config.async_session() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _read(row)

    @staticmethod
    async def list_tokens(
        *,
        cursor: str | None,
        limit: int,
    ) -> EvaluationTokenList:
        decoded = decode_evaluation_token_cursor(cursor)
        async with db_config.async_session() as session:
            stmt = select(EvaluationTokenTable)
            if decoded is not None:
                stmt = stmt.where(
                    or_(
                        EvaluationTokenTable.created_at < decoded.created_at,
                        and_(
                            EvaluationTokenTable.created_at == decoded.created_at,
                            EvaluationTokenTable.id < decoded.record_id,
                        ),
                    )
                )
            rows = list(
                (
                    await session.execute(
                        stmt.order_by(
                            EvaluationTokenTable.created_at.desc(),
                            EvaluationTokenTable.id.desc(),
                        ).limit(limit + 1)
                    )
                )
                .scalars()
                .all()
            )
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = encode_evaluation_token_cursor(
                EvaluationTokenCursorValue(
                    created_at=last.created_at,
                    record_id=last.id,
                )
            )
        return EvaluationTokenList(
            items=[_read(row) for row in page],
            next_cursor=next_cursor,
        )

    @staticmethod
    async def delete(token_id: str) -> bool:
        async with db_config.async_session() as session:
            result = await session.execute(
                delete(EvaluationTokenTable).where(EvaluationTokenTable.id == token_id)
            )
            await session.commit()
            return result.rowcount > 0

    @staticmethod
    async def get_for_authentication(
        token: str,
    ) -> EvaluationTokenAuthenticationRecord | None:
        """Read credential state without updating last-used or other metadata."""
        async with db_config.async_session() as session:
            result = await session.execute(
                select(EvaluationTokenTable, UserTable)
                .join(
                    UserTable,
                    UserTable.id == EvaluationTokenTable.created_by_user_id,
                )
                .where(EvaluationTokenTable.token == token)
            )
            pair = result.one_or_none()
            if pair is None:
                return None
            token_row, user = pair
            return EvaluationTokenAuthenticationRecord(
                id=token_row.id,
                token=token_row.token,
                scopes=frozenset(_scopes(token_row)),
                expires_at=token_row.expires_at,
                user_id=user.id,
                user_email=user.email,
                user_is_active=user.is_active,
            )
