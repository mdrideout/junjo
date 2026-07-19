"""Security tests for authentication bypass attempts.

Tests various authentication bypass scenarios to ensure the system
properly rejects unauthorized access attempts.
"""

import asyncio
import base64
import os

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.db_sqlite.users.repository import UserRepository
from app.main import app


@pytest.mark.security
@pytest.mark.asyncio
async def test_session_cookie_tampering():
    """Test that tampering with session cookie results in rejection.

    Security: Prevents session hijacking by validating cookie signatures.

    Fixed: https_only is now environment-aware (False in test/dev, True in production)
    """

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )

        # Ensure session cookie was set
        assert "session" in sign_in_response.cookies, "Session cookie not set on sign in"

        # Get valid session cookie
        session_cookie = sign_in_response.cookies["session"]

        # Change a non-padding character so the decoded authenticated value must
        # differ; changing the final base64 character can alter only ignored
        # padding bits and leave the decoded bytes unchanged.
        tamper_index = len(session_cookie) // 2
        replacement = "a" if session_cookie[tamper_index] != "a" else "b"
        tampered_cookie = (
            session_cookie[:tamper_index] + replacement + session_cookie[tamper_index + 1 :]
        )

        # Replace the client's valid cookie instead of sending two cookies with
        # the same name and relying on ambiguous duplicate-cookie selection.
        client.cookies.clear()
        client.cookies.set("session", tampered_cookie)
        response = await client.get("/auth-test")

        # Should reject tampered cookie
        assert response.status_code == 401
        assert "session" in response.json()["detail"].lower()


@pytest.mark.security
@pytest.mark.asyncio
async def test_missing_session_cookie():
    """Test that missing session cookie is properly rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try to access protected endpoint without any cookie
        response = await client.get("/auth-test")

        assert response.status_code == 401
        assert "session" in response.json()["detail"].lower()


@pytest.mark.security
@pytest.mark.asyncio
async def test_empty_session_cookie():
    """Test that empty session cookie is rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Try with empty session cookie
        response = await client.get(
            "/auth-test",
            cookies={"session": ""},
        )

        assert response.status_code == 401


@pytest.mark.security
@pytest.mark.asyncio
async def test_malformed_session_cookie():
    """Test that malformed session cookies are rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        malformed_cookies = [
            "invalid",
            "a" * 1000,  # Very long
            ";;;;",
            "<script>alert(1)</script>",
            "../../../etc/passwd",
        ]

        for malformed in malformed_cookies:
            response = await client.get(
                "/auth-test",
                cookies={"session": malformed},
            )

            assert response.status_code == 401, f"Failed to reject malformed cookie: {malformed}"


@pytest.mark.security
@pytest.mark.asyncio
async def test_sign_out_clears_session():
    """Test that signing out clears the session data.

    Security: Ensures users can properly sign out.

    A captured pre-sign-out cookie must also be rejected after sign-out.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )

        # Ensure session cookie was set
        assert "session" in sign_in_response.cookies, "Session cookie not set on sign in"
        session_cookie = sign_in_response.cookies["session"]

        # Verify session works
        auth_response = await client.get(
            "/auth-test",
            cookies={"session": session_cookie},
        )
        assert auth_response.status_code == 200

        # Sign out (clears session data)
        signout_response = await client.post("/sign-out", cookies={"session": session_cookie})
        assert signout_response.status_code == 200

        client.cookies.clear()
        replay_response = await client.get(
            "/auth-test",
            cookies={"session": session_cookie},
        )
        assert replay_response.status_code == 401
        assert "revoked" in replay_response.json()["detail"].lower()


@pytest.mark.security
@pytest.mark.concurrency
@pytest.mark.asyncio
async def test_create_first_user_race_condition():
    """Test that only one 'first user' can be created even with concurrent requests.

    Security: Prevents race condition in initial setup that could allow
    unauthorized users to gain access.
    """
    transport = ASGITransport(app=app)

    async def create_user(user_num: int) -> tuple[int, dict[str, str]]:
        """Attempt to create first user."""
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/users/create-first-user",
                json={
                    "email": f"user{user_num}@example.com",
                    "password": f"password{user_num}",
                },
            )
            return response.status_code, response.json()

    # Launch 10 concurrent requests to create first user
    results = await asyncio.gather(*[create_user(i) for i in range(10)])

    successes = [(index, result) for index, result in enumerate(results) if result[0] == 200]
    failures = [result for result in results if result[0] == 400]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 9, f"Expected 9 failures, got {len(failures)}"

    for status, response in failures:
        assert status == 400
        assert "already exist" in response["detail"].lower()

    assert await UserRepository.count_users() == 1
    successful_index = successes[0][0]
    for user_num in range(10):
        user = await UserRepository.get_by_email(f"user{user_num}@example.com")
        if user_num == successful_index:
            assert user is not None
        else:
            assert user is None


@pytest.mark.security
@pytest.mark.asyncio
async def test_invalid_credentials_multiple_attempts():
    """Test that multiple invalid login attempts are rejected consistently.

    Note: This doesn't test rate limiting (not yet implemented), but ensures
    consistent rejection behavior.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "correct_password"},
        )

        # Try 10 failed login attempts
        for i in range(10):
            response = await client.post(
                "/sign-in",
                json={"email": "test@example.com", "password": f"wrong_password_{i}"},
            )

            # Each should be rejected
            assert response.status_code == 401
            assert "Invalid credentials" in response.json()["detail"]

        # Verify valid credentials still work (account not locked)
        valid_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "correct_password"},
        )
        assert valid_response.status_code == 200


@pytest.mark.security
@pytest.mark.asyncio
async def test_sql_injection_in_email():
    """Test that SQL injection attempts in email field are prevented.

    Security: Tests multiple layers of defense:
    1. Pydantic email validation rejects malformed emails (422)
    2. ORM parameterization prevents SQL injection if validation bypassed
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a legitimate user
        await client.post(
            "/users/create-first-user",
            json={"email": "legit@example.com", "password": "password123"},
        )

        # Try SQL injection payloads in email field
        sql_injection_payloads = [
            "' OR '1'='1",
            "admin'--",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users--",
            "admin' OR '1'='1'--",
        ]

        for payload in sql_injection_payloads:
            response = await client.post(
                "/sign-in",
                json={"email": payload, "password": "password123"},
            )

            # Should be rejected by validation (422) or auth (401)
            # Both are acceptable - indicates defense in depth
            assert response.status_code in [401, 422], (
                f"SQL injection not rejected: {payload} got {response.status_code}"
            )

            # If 401, should have invalid credentials message
            if response.status_code == 401:
                assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.security
@pytest.mark.asyncio
async def test_protected_endpoints_require_auth():
    """Test that all protected endpoints properly require authentication.

    Security: Ensures no protected endpoints are accidentally exposed.

    NOTE: API key endpoints now require authentication after recent updates.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # List of protected endpoints that should require auth
        protected_endpoints = [
            ("GET", "/auth-test", True),  # Should require auth
            ("GET", "/users", True),  # Should require auth
            ("POST", "/users", True),  # Should require auth
            ("GET", "/api_keys", True),  # Now protected
            ("POST", "/api_keys", True),  # Now protected
            ("POST", "/llm/generate", True),  # Should require auth
            ("GET", "/llm/providers/openai/models", True),  # Should require auth
            ("GET", "/api/v1/observability/services", True),
            ("GET", "/api/v1/observability/traces/trace-id/spans", True),
        ]

        for method, endpoint, currently_protected in protected_endpoints:
            if method == "GET":
                response = await client.get(endpoint)
            elif method == "POST":
                response = await client.post(endpoint, json={})

            if currently_protected:
                # All should reject unauthorized access
                assert response.status_code == 401, (
                    f"Endpoint {method} {endpoint} did not require auth (status: {response.status_code})"
                )
            else:
                # Document endpoints that need to be protected
                assert response.status_code != 401, (
                    f"Endpoint {method} {endpoint} unexpectedly requires auth (test needs update)"
                )


@pytest.mark.security
@pytest.mark.asyncio
async def test_session_cookie_httponly_and_secure_flags():
    """Test that session cookies have proper security flags (conceptual test).

    Note: This tests the concept - actual cookie flags depend on middleware configuration.
    The test verifies that cookies are being set, and we document the required flags.

    Required flags (configured in middleware):
    - HttpOnly: Prevents JavaScript access
    - Secure: Only sent over HTTPS (production)
    - SameSite=Lax or Strict: CSRF protection
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )

        # Verify session cookie is set
        assert "session" in sign_in_response.cookies

        # Document: In production, ensure these flags are set in middleware:
        # - SessionMiddleware with httponly=True
        # - SecureCookiesMiddleware with secure=True (HTTPS only)
        # - SameSite=Lax or Strict for CSRF protection


@pytest.mark.security
@pytest.mark.asyncio
async def test_session_cookie_is_encrypted_at_rest_in_the_browser():
    """The browser-facing cookie is Fernet ciphertext, not signed plaintext."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/users/create-first-user",
            json={"email": "encrypted@example.com", "password": "password123"},
        )
        response = await client.post(
            "/sign-in",
            json={"email": "encrypted@example.com", "password": "password123"},
        )

        cookie = response.cookies["session"]
        assert "encrypted@example.com" not in cookie
        decrypted = Fernet(os.environ["JUNJO_SECURE_COOKIE_KEY"]).decrypt(cookie.encode())
        signed_payload = decrypted.split(b".", maxsplit=1)[0]
        payload = base64.urlsafe_b64decode(signed_payload)
        assert b"encrypted@example.com" in payload


@pytest.mark.asyncio
async def test_observability_route_decodes_an_encoded_service_path(monkeypatch):
    received: list[tuple[str, int]] = []

    async def get_workflows(service_name: str, limit: int):
        received.append((service_name, limit))
        return []

    monkeypatch.setattr(
        "app.features.otel_spans.repository.get_fused_workflow_spans",
        get_workflows,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/users/create-first-user",
            json={"email": "route@example.com", "password": "password123"},
        )
        response = await client.get(
            "/api/v1/observability/services/slash%2Fpercent%25%20%E6%97%A5%E6%9C%AC%E8%AA%9E/workflows"
        )

    assert response.status_code == 200
    assert received == [("slash/percent% 日本語", 100)]


@pytest.mark.security
@pytest.mark.asyncio
async def test_sign_out_revokes_all_concurrent_sessions_for_the_user():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as first:
        await first.post(
            "/users/create-first-user",
            json={"email": "tabs@example.com", "password": "password123"},
        )
        first_cookie = (
            await first.post(
                "/sign-in",
                json={"email": "tabs@example.com", "password": "password123"},
            )
        ).cookies["session"]

        async with AsyncClient(transport=transport, base_url="http://test") as second:
            second_cookie = (
                await second.post(
                    "/sign-in",
                    json={"email": "tabs@example.com", "password": "password123"},
                )
            ).cookies["session"]

        await first.post("/sign-out", cookies={"session": first_cookie})
        first.cookies.clear()
        response = await first.get("/auth-test", cookies={"session": second_cookie})

    assert response.status_code == 401
    assert "revoked" in response.json()["detail"].lower()


@pytest.mark.security
@pytest.mark.asyncio
async def test_session_is_rejected_after_its_user_is_deleted():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/users/create-first-user",
            json={"email": "deleted@example.com", "password": "password123"},
        )
        cookie = (
            await client.post(
                "/sign-in",
                json={"email": "deleted@example.com", "password": "password123"},
            )
        ).cookies["session"]
        user_id = (await client.get("/users", cookies={"session": cookie})).json()[0]["id"]
        assert (
            await client.delete(f"/users/{user_id}", cookies={"session": cookie})
        ).status_code == 200

        client.cookies.clear()
        response = await client.get("/auth-test", cookies={"session": cookie})

    assert response.status_code == 401
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.security
@pytest.mark.asyncio
async def test_password_not_returned_in_responses():
    """Test that password hashes are never returned in API responses.

    Security: Prevents accidental password hash exposure.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create user
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )

        # Sign in and get session
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # List users
        list_response = await client.get(
            "/users",
            cookies={"session": session_cookie},
        )

        assert list_response.status_code == 200
        users = list_response.json()

        # Verify no password fields in response
        for user in users:
            assert "password" not in user
            assert "password_hash" not in user
            assert "hashed_password" not in user
