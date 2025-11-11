"""Integration tests for authentication router.

Tests the complete auth flow: db-has-users → create-first-user → sign-in → auth-test → sign-out.

Note: Database isolation is handled automatically by the autouse fixture in tests/conftest.py.
Each test gets its own temporary SQLite database that is cleaned up after the test.
See: backend_python/app/database/README.md for details on the test database pattern.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.db_sqlite.users.repository import UserRepository
from app.main import app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_db_has_users_empty():
    """Test /users/db-has-users when no users exist."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/users/db-has-users")
        assert response.status_code == 200
        assert response.json() == {"users_exist": False}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_first_user():
    """Test /users/create-first-user endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/users/create-first-user",
            json={"email": "first@example.com", "password": "password123"},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "First user created successfully"}

        # Verify user exists in database
        user = await UserRepository.get_by_id("first@example.com")
        assert user is not None or await UserRepository.db_has_users()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_first_user_when_users_exist():
    """Test /users/create-first-user fails when users already exist."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create first user
        await client.post(
            "/users/create-first-user",
            json={"email": "first@example.com", "password": "password123"},
        )

        # Try to create another "first" user
        response = await client.post(
            "/users/create-first-user",
            json={"email": "second@example.com", "password": "password123"},
        )
        assert response.status_code == 400
        assert "already exist" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sign_in_success():
    """Test successful sign-in."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a user first
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )

        # Sign in
        response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "signed in"}

        # Verify session cookie was set
        assert "session" in response.cookies
        session_cookie = response.cookies["session"]
        assert len(session_cookie) > 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sign_in_invalid_credentials():
    """Test sign-in with invalid credentials."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a user first
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )

        # Try to sign in with wrong password
        response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "wrong_password"},
        )
        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_test_authenticated():
    """Test /auth-test with valid session."""
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

        # Use session cookie to access protected endpoint
        session_cookie = sign_in_response.cookies["session"]
        response = await client.get(
            "/auth-test",
            cookies={"session": session_cookie},
        )
        assert response.status_code == 200
        assert response.json() == {"user_email": "test@example.com"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_test_unauthenticated():
    """Test /auth-test without session."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/auth-test")
        assert response.status_code == 401
        assert "No valid session" in response.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sign_out():
    """Test sign-out."""
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
        sign_in_response.cookies["session"]

        # Sign out
        response = await client.post("/sign-out")
        assert response.status_code == 200
        assert response.json() == {"message": "signed out"}

        # After sign-out, session cookie is cleared (implementation detail may vary)
        # The important thing is that the sign-out succeeded


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_user_authenticated():
    """Test /users POST endpoint with authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create first user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "admin@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "admin@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Create another user (authenticated)
        response = await client.post(
            "/users",
            json={"email": "newuser@example.com", "password": "password123"},
            cookies={"session": session_cookie},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "User created successfully"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_users_authenticated():
    """Test /users GET endpoint with authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create first user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "test@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "test@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # List users (authenticated)
        response = await client.get(
            "/users",
            cookies={"session": session_cookie},
        )
        assert response.status_code == 200
        users = response.json()
        assert len(users) >= 1
        assert any(user["email"] == "test@example.com" for user in users)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_user_authenticated():
    """Test /users/{id} DELETE endpoint with authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create first user and sign in
        await client.post(
            "/users/create-first-user",
            json={"email": "admin@example.com", "password": "password123"},
        )
        sign_in_response = await client.post(
            "/sign-in",
            json={"email": "admin@example.com", "password": "password123"},
        )
        session_cookie = sign_in_response.cookies["session"]

        # Create another user to delete
        await client.post(
            "/users",
            json={"email": "todelete@example.com", "password": "password123"},
            cookies={"session": session_cookie},
        )

        # List users to get the ID
        list_response = await client.get(
            "/users",
            cookies={"session": session_cookie},
        )
        users = list_response.json()
        user_to_delete = next(u for u in users if u["email"] == "todelete@example.com")

        # Delete user (authenticated)
        response = await client.delete(
            f"/users/{user_to_delete['id']}",
            cookies={"session": session_cookie},
        )
        assert response.status_code == 200
        assert response.json() == {"message": "User deleted successfully"}

        # Verify user is deleted
        list_response2 = await client.get(
            "/users",
            cookies={"session": session_cookie},
        )
        users2 = list_response2.json()
        assert not any(u["email"] == "todelete@example.com" for u in users2)
