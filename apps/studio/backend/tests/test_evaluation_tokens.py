"""Security and REST contract tests for scoped evaluation-control tokens."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select

from app.common.datetime_utils import utcnow
from app.db_sqlite import db_config
from app.db_sqlite.evaluation_tokens.models import EvaluationTokenTable
from app.db_sqlite.users.models import UserTable
from app.features.auth.dependencies import get_authenticated_user
from app.main import app

pytestmark = pytest.mark.security


@pytest_asyncio.fixture
async def token_management_app(test_db, mock_authenticated_user) -> AsyncIterator:
    async with test_db() as session:
        session.add(
            UserTable(
                id=mock_authenticated_user.user_id,
                email=mock_authenticated_user.email,
                password_hash="test-only",
            )
        )
        await session.commit()
    app.dependency_overrides[get_authenticated_user] = lambda: mock_authenticated_user
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_authenticated_user, None)


async def _create_token(
    client: AsyncClient,
    *,
    name: str,
    scopes: list[str],
    expires_at: str | None = None,
) -> dict:
    body: dict[str, object] = {"name": name, "scopes": scopes}
    if expires_at is not None:
        body["expires_at"] = expires_at
    response = await client.post("/api/v1/evaluation-tokens", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_token_is_recoverable_from_authenticated_management_routes(
    token_management_app,
    test_db,
) -> None:
    transport = ASGITransport(app=token_management_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _create_token(
            client,
            name="Coding agent",
            scopes=["evaluation:write", "evaluation:read", "evidence:read"],
        )
        listed = await client.get("/api/v1/evaluation-tokens")

    assert created["token"].startswith("jcli_")
    assert len(created["token"]) == 69
    assert "prefix" not in created
    assert created["scopes"] == [
        "evaluation:read",
        "evaluation:write",
        "evidence:read",
    ]
    assert listed.status_code == 200
    assert listed.json()["items"] == [created]

    async with test_db() as session:
        stored = (
            await session.execute(
                select(EvaluationTokenTable).where(EvaluationTokenTable.id == created["id"])
            )
        ).scalar_one()
    assert stored.token == created["token"]


async def test_token_listing_is_keyset_paginated_and_deletion_is_explicit(
    token_management_app,
) -> None:
    transport = ASGITransport(app=token_management_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await _create_token(client, name="First", scopes=["evaluation:read"])
        second = await _create_token(client, name="Second", scopes=["evidence:read"])

        first_page = await client.get("/api/v1/evaluation-tokens", params={"limit": 1})
        cursor = first_page.json()["next_cursor"]
        second_page = await client.get(
            "/api/v1/evaluation-tokens",
            params={"limit": 1, "cursor": cursor},
        )
        malformed = await client.get(
            "/api/v1/evaluation-tokens",
            params={"cursor": "____"},
        )

        deleted = await client.delete(f"/api/v1/evaluation-tokens/{first['id']}")
        deleted_again = await client.delete(f"/api/v1/evaluation-tokens/{first['id']}")
        missing = await client.delete("/api/v1/evaluation-tokens/missing")

    page_ids = {
        first_page.json()["items"][0]["id"],
        second_page.json()["items"][0]["id"],
    }
    assert page_ids == {first["id"], second["id"]}
    assert second_page.json()["next_cursor"] is None
    assert malformed.status_code == 422
    assert deleted.status_code == 204
    assert deleted_again.status_code == 404
    assert missing.status_code == 404


async def test_token_management_requires_browser_session_not_bearer_token(
    token_management_app,
) -> None:
    transport = ASGITransport(app=token_management_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _create_token(
            client,
            name="Cannot manage credentials",
            scopes=["evaluation:read", "evaluation:write", "evidence:read"],
        )

    session_override = app.dependency_overrides.pop(get_authenticated_user)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/evaluation-tokens",
                headers={"Authorization": f"Bearer {created['token']}"},
            )
    finally:
        app.dependency_overrides[get_authenticated_user] = session_override
    assert response.status_code == 401


async def test_evaluation_read_write_and_evidence_scopes_are_distinct(
    token_management_app,
    monkeypatch,
) -> None:
    transport = ASGITransport(app=token_management_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        read = await _create_token(client, name="Read", scopes=["evaluation:read"])
        write = await _create_token(client, name="Write", scopes=["evaluation:write"])
        evidence = await _create_token(client, name="Evidence", scopes=["evidence:read"])

    session_override = app.dependency_overrides.pop(get_authenticated_user)
    monkeypatch.setattr(
        "app.features.execution_resolution.service.resolve_execution",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.features.trace_evidence.service.get_trace_evidence",
        AsyncMock(return_value=None),
    )
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            read_ok = await client.get(
                "/api/v1/evaluation/runs",
                headers={"Authorization": f"Bearer {read['token']}"},
            )
            read_cannot_write = await client.post(
                "/api/v1/evaluation/datasets",
                headers={"Authorization": f"Bearer {read['token']}"},
                json={
                    "application_key": "ai_chat",
                    "key": "scope-test",
                    "name": "Scope test",
                },
            )
            write_ok = await client.post(
                "/api/v1/evaluation/datasets",
                headers={"Authorization": f"Bearer {write['token']}"},
                json={
                    "application_key": "ai_chat",
                    "key": "write-scope-test",
                    "name": "Write scope test",
                },
            )
            write_cannot_read = await client.get(
                "/api/v1/evaluation/runs",
                headers={"Authorization": f"Bearer {write['token']}"},
            )
            evidence_ok = await client.get(
                "/api/v1/execution-resolution",
                headers={"Authorization": f"Bearer {evidence['token']}"},
                params={
                    "service_namespace": "junjo.examples",
                    "service_name": "ai-chat",
                    "executable_type": "workflow",
                    "runtime_id": "workflow-run",
                },
            )
            evidence_cannot_read_control = await client.get(
                "/api/v1/evaluation/runs",
                headers={"Authorization": f"Bearer {evidence['token']}"},
            )
            evidence_trace_ok = await client.get(
                f"/api/v1/trace-evidence/{'a' * 32}",
                headers={"Authorization": f"Bearer {evidence['token']}"},
            )
            read_cannot_read_evidence = await client.get(
                "/api/v1/execution-resolution",
                headers={"Authorization": f"Bearer {read['token']}"},
                params={
                    "service_namespace": "junjo.examples",
                    "service_name": "ai-chat",
                    "executable_type": "workflow",
                    "runtime_id": "workflow-run",
                },
            )
    finally:
        app.dependency_overrides[get_authenticated_user] = session_override

    assert read_ok.status_code == 200
    assert read_cannot_write.status_code == 403
    assert write_ok.status_code == 200
    assert write_cannot_read.status_code == 403
    assert evidence_ok.status_code == 404
    assert evidence_trace_ok.status_code == 404
    assert evidence_cannot_read_control.status_code == 403
    assert read_cannot_read_evidence.status_code == 403
    for forbidden in (
        read_cannot_write,
        write_cannot_read,
        evidence_cannot_read_control,
        read_cannot_read_evidence,
    ):
        assert forbidden.json()["detail"]["code"] == "insufficient_evaluation_token_scope"


async def test_deletion_applies_to_the_next_request_without_auth_cache_or_write(
    token_management_app,
) -> None:
    transport = ASGITransport(app=token_management_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _create_token(client, name="Revocable", scopes=["evaluation:read"])

    session_override = app.dependency_overrides.pop(get_authenticated_user)
    write_statements: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _many):
        normalized = statement.lstrip().upper()
        if normalized.startswith(("INSERT", "UPDATE", "DELETE")):
            write_statements.append(statement)

    event.listen(db_config.engine.sync_engine, "before_cursor_execute", capture_statement)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            authorized = await client.get(
                "/api/v1/evaluation/runs",
                headers={"Authorization": f"Bearer {created['token']}"},
            )
    finally:
        event.remove(db_config.engine.sync_engine, "before_cursor_execute", capture_statement)
        app.dependency_overrides[get_authenticated_user] = session_override

    assert authorized.status_code == 200
    assert write_statements == []

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        deleted = await client.delete(f"/api/v1/evaluation-tokens/{created['id']}")
    assert deleted.status_code == 204

    session_override = app.dependency_overrides.pop(get_authenticated_user)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rejected = await client.get(
                "/api/v1/evaluation/runs",
                headers={"Authorization": f"Bearer {created['token']}"},
            )
    finally:
        app.dependency_overrides[get_authenticated_user] = session_override
    assert rejected.status_code == 401


async def test_expired_unknown_and_wrong_scheme_credentials_are_rejected(
    token_management_app,
    test_db,
) -> None:
    transport = ASGITransport(app=token_management_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        expiring = await _create_token(
            client,
            name="Expiring",
            scopes=["evaluation:read"],
            expires_at=(utcnow() + timedelta(hours=1)).isoformat(),
        )
        expired_create = await client.post(
            "/api/v1/evaluation-tokens",
            json={
                "name": "Expired",
                "scopes": ["evaluation:read"],
                "expires_at": (utcnow() - timedelta(seconds=1)).isoformat(),
            },
        )

    assert expired_create.status_code == 422
    async with test_db() as session:
        row = await session.get(EvaluationTokenTable, expiring["id"])
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        await session.commit()

    session_override = app.dependency_overrides.pop(get_authenticated_user)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            expired = await client.get(
                "/api/v1/evaluation/runs",
                headers={"Authorization": f"Bearer {expiring['token']}"},
            )
            unknown = await client.get(
                "/api/v1/evaluation/runs",
                headers={"Authorization": "Bearer token-not-present-in-the-table"},
            )
            wrong_scheme = await client.get(
                "/api/v1/evaluation/runs",
                headers={"Authorization": "Basic abc"},
            )
    finally:
        app.dependency_overrides[get_authenticated_user] = session_override

    assert expired.status_code == 401
    assert unknown.status_code == 401
    assert wrong_scheme.status_code == 401


async def test_browser_session_remains_accepted_for_evaluation_routes() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/users/create-first-user",
            json={"email": "session@example.com", "password": "password123"},
        )
        signed_in = await client.post(
            "/sign-in",
            json={"email": "session@example.com", "password": "password123"},
        )
        response = await client.get("/api/v1/evaluation/runs")

    assert created.status_code == 200
    assert signed_in.status_code == 200
    assert response.status_code == 200


def test_evaluation_token_openapi_contract_is_explicit() -> None:
    schema = app.openapi()
    assert schema["paths"]["/api/v1/evaluation-tokens"]["post"]["operationId"] == (
        "create_evaluation_token"
    )
    assert schema["paths"]["/api/v1/evaluation-tokens"]["get"]["operationId"] == (
        "list_evaluation_tokens"
    )
    assert (
        schema["paths"]["/api/v1/evaluation-tokens/{token_id}"]["delete"]["operationId"]
        == "delete_evaluation_token"
    )

    read_properties = schema["components"]["schemas"]["EvaluationTokenRead"]["properties"]
    assert "token" in read_properties
    assert "prefix" not in read_properties
    assert "secret_hash" not in read_properties

    for path, method in (
        ("/api/v1/evaluation/runs", "get"),
        ("/api/v1/evaluation/runs", "post"),
        ("/api/v1/execution-resolution", "get"),
        ("/api/v1/trace-evidence/{trace_id}", "get"),
    ):
        assert schema["paths"][path][method]["security"] == [{"EvaluationControlToken": []}]
