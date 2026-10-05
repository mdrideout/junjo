"""Terminal contracts for ``junjo auth login``, ``logout``, and ``status``."""

from __future__ import annotations

import importlib
import json
import os
import stat
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from junjo.cli import auth
from junjo.cli.credentials import (
    StoredCredential,
    credentials_path,
    read_stored_credential,
    store_credential,
)
from junjo.cli.main import (
    EXIT_AUTHENTICATION,
    EXIT_CONTRACT,
    EXIT_OK,
    EXIT_TRANSIENT,
    EXIT_USAGE,
)
from junjo.studio import StudioClient

cli = importlib.import_module("junjo.cli.main")

BASE_URL = "https://studio.test"
ORIGIN = "https://studio.test"
OTHER_ORIGIN = "http://localhost:26154"
DEVICE_CODE = "jdev_" + "d" * 64
ACCESS_TOKEN = "jcli_" + "t" * 64
OTHER_TOKEN = "jcli_" + "o" * 64
ENVIRONMENT_TOKEN = "jcli_" + "e" * 64
TOKEN_ID = "example-token-id"
ALL_SCOPES = ["evaluation:read", "evaluation:write", "evidence:read"]
APPROVAL_PAGE = "https://studio.test/cli-sign-in?code=WZRP-JWSQ"

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]

# Bound before any fixture replaces it, so its own behavior can be tested.
open_browser = auth._open_browser


@dataclass
class Terminal:
    """What a sign-in would otherwise do to the machine running the tests."""

    waits: list[int] = field(default_factory=list)
    opened: list[str] = field(default_factory=list)
    browser_opens: bool = True

    async def wait(self, seconds: int) -> None:
        self.waits.append(seconds)

    def open_browser(self, address: str) -> bool:
        self.opened.append(address)
        return self.browser_opens


def _no_studio(**_configuration: Any) -> StudioClient:
    raise AssertionError("This command must not create a Studio client.")


@pytest.fixture(autouse=True)
def terminal(monkeypatch: pytest.MonkeyPatch) -> Terminal:
    """Never sleep, open a browser, reach a network, or read ambient configuration."""

    monkeypatch.delenv("JUNJO_AI_STUDIO_CLI_TOKEN", raising=False)
    monkeypatch.delenv("JUNJO_AI_STUDIO_BACKEND_BASE_URL", raising=False)
    terminal = Terminal()
    monkeypatch.setattr(auth, "_wait", terminal.wait)
    monkeypatch.setattr(auth, "_open_browser", terminal.open_browser)
    monkeypatch.setattr(auth, "StudioClient", _no_studio)
    monkeypatch.setattr(auth.socket, "gethostname", lambda: "laptop")
    return terminal


def _studio(monkeypatch: pytest.MonkeyPatch, handler: Handler) -> list[httpx.Request]:
    """Serve Studio from a mocked transport and record every request it receives."""

    requests: list[httpx.Request] = []

    async def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return await handler(request)

    def create(**configuration: Any) -> StudioClient:
        return StudioClient(
            **configuration,
            retry_backoff_seconds=0,
            transport=httpx.MockTransport(recording),
        )

    monkeypatch.setattr(auth, "StudioClient", create)
    return requests


def _run(capsys: pytest.CaptureFixture[str], *arguments: str) -> tuple[int, dict, str]:
    exit_code = cli.main(["auth", "--studio-backend-base-url", BASE_URL, *arguments])
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1
    return exit_code, json.loads(captured.out), captured.err


def _started(*, expires_in: int = 900, interval: int = 5) -> httpx.Response:
    return httpx.Response(
        201,
        json={
            "device_code": DEVICE_CODE,
            "user_code": "WZRP-JWSQ",
            "verification_path": "/cli-sign-in",
            "expires_in": expires_in,
            "interval": interval,
        },
    )


def _pending() -> httpx.Response:
    return httpx.Response(
        400,
        json={
            "code": "authorization_pending",
            "message": "The CLI sign-in has not been approved or denied yet",
        },
    )


def _minted(scopes: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": ACCESS_TOKEN,
            "token_type": "bearer",
            "token_id": TOKEN_ID,
            "scopes": scopes,
            "expires_at": None,
        },
    )


def _current() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": TOKEN_ID,
            "name": "junjo CLI on laptop",
            "scopes": ALL_SCOPES,
            "expires_at": None,
            "created_at": "2026-10-04T05:17:09Z",
        },
    )


def _unauthorized() -> httpx.Response:
    return httpx.Response(
        401,
        headers={"WWW-Authenticate": "Bearer"},
        json={"code": "unauthorized", "message": "Invalid or expired evaluation token"},
    )


def _sign_in(*poll_answers: Callable[[], httpx.Response], started: Callable[[], httpx.Response] = _started) -> Handler:
    """Answer the start call, then each collection attempt with the next scripted answer."""

    answers = iter(poll_answers)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        if (request.method, request.url.path) == ("POST", "/api/v1/cli-sign-ins"):
            return started()
        assert (request.method, request.url.path) == ("POST", "/api/v1/cli-sign-ins/token")
        assert json.loads(request.content) == {"device_code": DEVICE_CODE}
        return next(answers)()

    return handler


def _store(origin: str = ORIGIN, token: str = ACCESS_TOKEN, token_id: str = TOKEN_ID) -> None:
    store_credential(origin, StoredCredential(token=token, token_id=token_id))


def test_login_polls_until_approved_then_stores_the_token_and_never_prints_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    terminal: Terminal,
) -> None:
    _store(OTHER_ORIGIN, OTHER_TOKEN, "other-token")
    requests = _studio(monkeypatch, _sign_in(_pending, _pending, lambda: _minted(ALL_SCOPES)))
    path = credentials_path()

    exit_code = cli.main(["auth", "--studio-backend-base-url", BASE_URL, "login"])

    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert captured.err == (
        "Sign-in code: WZRP-JWSQ\n"
        "Approval page: https://studio.test/cli-sign-in?code=WZRP-JWSQ\n"
        "The approval page was opened in your browser.\n"
        "Approve the sign-in only if the page shows the same code.\n"
        "Waiting for approval. The code expires in 900 seconds.\n"
    )
    assert captured.out == (
        '{"command":"auth.login","data":{'
        f'"credentials_path":"{path}",'
        '"environment_token_set":false,'
        f'"message":"Signed in to https://studio.test. The developer access token is stored in {path}.",'
        '"origin":"https://studio.test",'
        '"scopes":["evaluation:read","evaluation:write","evidence:read"],'
        '"token_id":"example-token-id"},'
        '"ok":true,"schema_version":1}\n'
    )
    assert ACCESS_TOKEN not in captured.out + captured.err
    assert DEVICE_CODE not in captured.out + captured.err

    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/api/v1/cli-sign-ins"),
        ("POST", "/api/v1/cli-sign-ins/token"),
        ("POST", "/api/v1/cli-sign-ins/token"),
        ("POST", "/api/v1/cli-sign-ins/token"),
    ]
    assert json.loads(requests[0].content) == {
        "client_name": "junjo CLI on laptop",
        "scopes": ALL_SCOPES,
    }
    assert terminal.waits == [5, 5, 5]
    assert terminal.opened == [APPROVAL_PAGE]

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "credentials": {
            OTHER_ORIGIN: {"token": OTHER_TOKEN, "token_id": "other-token"},
            ORIGIN: {"token": ACCESS_TOKEN, "token_id": TOKEN_ID},
        }
    }
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize(
    ("code", "message", "reported"),
    [
        ("access_denied", "The CLI sign-in was denied", "The CLI sign-in was denied."),
        (
            "expired_token",
            "The device code is unknown, already used, or expired",
            "The CLI sign-in is unknown, already used, or expired. Start a new sign-in.",
        ),
    ],
)
def test_login_reports_a_denied_or_expired_sign_in_and_stores_nothing(
    code: str,
    message: str,
    reported: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    terminal: Terminal,
) -> None:
    requests = _studio(
        monkeypatch,
        _sign_in(_pending, lambda: httpx.Response(400, json={"code": code, "message": message})),
    )

    exit_code, payload, diagnostics = _run(capsys, "login")

    assert exit_code == EXIT_AUTHENTICATION
    assert payload == {
        "command": "auth.login",
        "error": {"code": code, "message": reported},
        "ok": False,
        "schema_version": 1,
    }
    assert diagnostics.endswith(f"{code}: {reported}\n")
    assert len(requests) == 3
    assert terminal.waits == [5, 5]
    assert not credentials_path().exists()


def test_login_stops_polling_when_the_sign_in_lifetime_has_passed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    terminal: Terminal,
) -> None:
    requests = _studio(
        monkeypatch,
        _sign_in(
            _pending,
            _pending,
            _pending,
            started=lambda: _started(expires_in=12, interval=5),
        ),
    )

    exit_code, payload, diagnostics = _run(capsys, "login")

    assert exit_code == EXIT_AUTHENTICATION
    assert payload["error"] == {
        "code": "expired_token",
        "message": "The CLI sign-in is unknown, already used, or expired. Start a new sign-in.",
    }
    assert "Waiting for approval. The code expires in 12 seconds.\n" in diagnostics
    assert terminal.waits == [5, 5, 5]
    assert len(requests) == 4
    assert not credentials_path().exists()


def test_login_without_a_browser_prints_the_approval_page_address(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    terminal: Terminal,
) -> None:
    _studio(monkeypatch, _sign_in(lambda: _minted(ALL_SCOPES)))

    exit_code, payload, diagnostics = _run(capsys, "login", "--no-browser")

    assert exit_code == EXIT_OK
    assert payload["ok"] is True
    assert terminal.opened == []
    assert diagnostics == (
        "Sign-in code: WZRP-JWSQ\n"
        "Approval page: https://studio.test/cli-sign-in?code=WZRP-JWSQ\n"
        "Open the approval page in your browser.\n"
        "Approve the sign-in only if the page shows the same code.\n"
        "Waiting for approval. The code expires in 900 seconds.\n"
    )


def test_login_continues_when_a_browser_cannot_be_opened(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    terminal: Terminal,
) -> None:
    terminal.browser_opens = False
    _studio(monkeypatch, _sign_in(lambda: _minted(ALL_SCOPES)))

    exit_code, payload, diagnostics = _run(capsys, "login")

    assert exit_code == EXIT_OK
    assert payload["data"]["token_id"] == TOKEN_ID
    assert terminal.opened == [APPROVAL_PAGE]
    assert diagnostics == (
        "Sign-in code: WZRP-JWSQ\n"
        "Approval page: https://studio.test/cli-sign-in?code=WZRP-JWSQ\n"
        "A browser could not be opened. Open the approval page in your browser.\n"
        "Approve the sign-in only if the page shows the same code.\n"
        "Waiting for approval. The code expires in 900 seconds.\n"
    )
    stored = read_stored_credential(ORIGIN)
    assert stored is not None and stored.token.get_secret_value() == ACCESS_TOKEN


def test_the_browser_opener_reports_whether_a_browser_was_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcomes = iter([True, False, auth.webbrowser.Error("no browser"), OSError("the browser is gone")])
    addresses: list[str] = []

    def scripted_open(address: str) -> bool:
        addresses.append(address)
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(auth.webbrowser, "open", scripted_open)

    assert [open_browser(APPROVAL_PAGE) for _ in range(4)] == [True, False, False, False]
    assert addresses == [APPROVAL_PAGE] * 4


def test_login_asks_for_the_named_scopes_under_the_given_name(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    narrowed = ["evaluation:read", "evidence:read"]
    requests = _studio(monkeypatch, _sign_in(lambda: _minted(narrowed)))

    exit_code, payload, _ = _run(
        capsys,
        "login",
        "--scope",
        "evidence:read",
        "--scope",
        "evaluation:read",
        "--name",
        "build host",
    )

    assert exit_code == EXIT_OK
    assert json.loads(requests[0].content) == {
        "client_name": "build host",
        "scopes": ["evidence:read", "evaluation:read"],
    }
    assert payload["data"]["scopes"] == narrowed


def test_login_signs_in_to_the_normalized_origin_of_the_base_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    terminal: Terminal,
) -> None:
    requests = _studio(monkeypatch, _sign_in(lambda: _minted(ALL_SCOPES)))

    exit_code = cli.main(["auth", "--studio-backend-base-url", "HTTPS://Studio.Test/", "login"])

    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert json.loads(captured.out)["data"]["origin"] == ORIGIN
    assert f"Approval page: {APPROVAL_PAGE}\n" in captured.err
    assert terminal.opened == [APPROVAL_PAGE]
    assert str(requests[0].url) == "https://studio.test/api/v1/cli-sign-ins"
    stored = read_stored_credential(ORIGIN)
    assert stored is not None and stored.token.get_secret_value() == ACCESS_TOKEN
    assert json.loads(credentials_path().read_text(encoding="utf-8")) == {
        "credentials": {ORIGIN: {"token": ACCESS_TOKEN, "token_id": TOKEN_ID}},
    }


def test_login_says_when_the_environment_variable_still_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", ENVIRONMENT_TOKEN)
    _studio(monkeypatch, _sign_in(lambda: _minted(ALL_SCOPES)))
    path = credentials_path()

    exit_code, payload, diagnostics = _run(capsys, "login")

    assert exit_code == EXIT_OK
    assert payload["data"]["environment_token_set"] is True
    assert payload["data"]["message"] == (
        f"Signed in to https://studio.test. The developer access token is stored in {path}. "
        "JUNJO_AI_STUDIO_CLI_TOKEN is set and takes precedence, so commands keep using it."
    )
    assert ENVIRONMENT_TOKEN not in json.dumps(payload) + diagnostics
    stored = read_stored_credential(ORIGIN)
    assert stored is not None and stored.token.get_secret_value() == ACCESS_TOKEN


def test_login_refuses_an_unusable_credential_file_before_anyone_is_asked_to_approve(
    capsys: pytest.CaptureFixture[str],
    terminal: Terminal,
) -> None:
    path = credentials_path()
    path.parent.mkdir(mode=0o700)
    path.write_text("not json", encoding="utf-8")
    path.chmod(0o600)

    exit_code, payload, diagnostics = _run(capsys, "login")

    assert exit_code == EXIT_USAGE
    assert payload["error"]["code"] == "usage_or_validation"
    assert str(path) in payload["error"]["message"]
    assert "Sign-in code" not in diagnostics
    assert terminal.opened == []
    assert path.read_text(encoding="utf-8") == "not json"


def test_login_rejects_a_repeated_scope_and_an_unsafe_origin_before_any_request(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code, payload, _ = _run(capsys, "login", "--scope", "evidence:read", "--scope", "evidence:read")

    assert exit_code == EXIT_USAGE
    assert payload["error"]["code"] == "usage_or_validation"
    assert "scopes must not contain duplicates" in payload["error"]["message"]

    exit_code = cli.main(["auth", "--studio-backend-base-url", "http://studio.example.com", "login"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == EXIT_USAGE
    assert payload["error"] == {
        "code": "usage_or_validation",
        "message": "Plain HTTP Studio origins are allowed only on loopback.",
    }


def test_login_keeps_the_browser_on_the_studio_origin_it_was_started_against(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    terminal: Terminal,
) -> None:
    def elsewhere() -> httpx.Response:
        return httpx.Response(
            201,
            json={
                "device_code": DEVICE_CODE,
                "user_code": "WZRP-JWSQ",
                "verification_path": "@elsewhere.example/cli-sign-in",
                "expires_in": 900,
                "interval": 5,
            },
        )

    requests = _studio(monkeypatch, _sign_in(started=elsewhere))

    exit_code, payload, diagnostics = _run(capsys, "login")

    assert exit_code == EXIT_CONTRACT
    assert payload["error"]["code"] == "studio_contract"
    assert "elsewhere.example" not in diagnostics
    assert terminal.opened == []
    assert len(requests) == 1


def test_logout_revokes_the_stored_token_and_deletes_the_stored_copy(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store()
    _store(OTHER_ORIGIN, OTHER_TOKEN, "other-token")
    path = credentials_path()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    requests = _studio(monkeypatch, handler)

    exit_code = cli.main(["auth", "--studio-backend-base-url", BASE_URL, "logout"])

    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert captured.err == ""
    assert captured.out == (
        '{"command":"auth.logout","data":{'
        f'"credentials_path":"{path}",'
        '"environment_token_set":false,'
        '"message":"Studio revoked the token. The stored credential for https://studio.test was deleted.",'
        '"origin":"https://studio.test",'
        '"revocation":"revoked",'
        '"stored_credential":"deleted",'
        '"token_id":"example-token-id"},'
        '"ok":true,"schema_version":1}\n'
    )
    assert [(request.method, request.url.path) for request in requests] == [
        ("DELETE", "/api/v1/evaluation-tokens/current"),
    ]
    assert requests[0].headers["authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert read_stored_credential(ORIGIN) is None
    other = read_stored_credential(OTHER_ORIGIN)
    assert other is not None and other.token.get_secret_value() == OTHER_TOKEN


def test_logout_deletes_the_stored_copy_when_studio_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store()

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    _studio(monkeypatch, handler)

    exit_code, payload, diagnostics = _run(capsys, "logout")

    assert exit_code == EXIT_TRANSIENT
    assert diagnostics == ""
    assert payload["ok"] is True
    assert payload["data"] == {
        "credentials_path": str(credentials_path()),
        "environment_token_set": False,
        "message": (
            "Studio could not be reached, so the token was not revoked. "
            "The stored credential for https://studio.test was deleted. "
            "Delete token example-token-id on the Developer Access Tokens page in Studio."
        ),
        "origin": ORIGIN,
        "revocation": "unreachable",
        "stored_credential": "deleted",
        "token_id": TOKEN_ID,
    }
    assert read_stored_credential(ORIGIN) is None


def test_logout_deletes_the_stored_copy_when_studio_already_rejects_the_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store()

    async def handler(request: httpx.Request) -> httpx.Response:
        return _unauthorized()

    requests = _studio(monkeypatch, handler)

    exit_code, payload, _ = _run(capsys, "logout")

    assert exit_code == EXIT_OK
    assert payload["ok"] is True
    assert payload["data"]["revocation"] == "rejected"
    assert payload["data"]["stored_credential"] == "deleted"
    assert payload["data"]["message"] == (
        "Studio already rejects the token: it was revoked or has expired. "
        "The stored credential for https://studio.test was deleted."
    )
    assert len(requests) == 1
    assert read_stored_credential(ORIGIN) is None


def test_logout_with_nothing_stored_says_so_without_calling_studio(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store(OTHER_ORIGIN, OTHER_TOKEN, "other-token")

    exit_code, payload, diagnostics = _run(capsys, "logout")

    assert exit_code == EXIT_OK
    assert diagnostics == ""
    assert payload == {
        "command": "auth.logout",
        "data": {
            "credentials_path": str(credentials_path()),
            "environment_token_set": False,
            "message": "No credential is stored for https://studio.test.",
            "origin": ORIGIN,
            "revocation": "not_attempted",
            "stored_credential": "none",
            "token_id": None,
        },
        "ok": True,
        "schema_version": 1,
    }
    assert read_stored_credential(OTHER_ORIGIN) is not None


def test_logout_revokes_only_the_stored_token_and_says_the_environment_variable_stays_in_use(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", ENVIRONMENT_TOKEN)
    _store()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    requests = _studio(monkeypatch, handler)

    exit_code, payload, diagnostics = _run(capsys, "logout")

    assert exit_code == EXIT_OK
    assert [request.headers["authorization"] for request in requests] == [f"Bearer {ACCESS_TOKEN}"]
    assert payload["data"]["environment_token_set"] is True
    assert payload["data"]["message"] == (
        "Studio revoked the token. The stored credential for https://studio.test was deleted. "
        "JUNJO_AI_STUDIO_CLI_TOKEN is set, so commands keep using it."
    )
    assert ENVIRONMENT_TOKEN not in json.dumps(payload) + diagnostics
    assert os.environ["JUNJO_AI_STUDIO_CLI_TOKEN"] == ENVIRONMENT_TOKEN
    assert read_stored_credential(ORIGIN) is None

    exit_code, payload, _ = _run(capsys, "logout")

    assert exit_code == EXIT_OK
    assert payload["data"]["message"] == (
        "No credential is stored for https://studio.test. JUNJO_AI_STUDIO_CLI_TOKEN is set, so commands keep using it."
    )
    assert len(requests) == 1


def test_status_reports_a_stored_credential_that_studio_accepts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store()
    path = credentials_path()

    async def handler(request: httpx.Request) -> httpx.Response:
        return _current()

    requests = _studio(monkeypatch, handler)

    exit_code = cli.main(["auth", "--studio-backend-base-url", BASE_URL, "status"])

    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert captured.err == ""
    assert captured.out == (
        '{"command":"auth.status","data":{'
        '"credential_source":"stored",'
        f'"credentials_path":"{path}",'
        '"message":"Studio accepts the stored credential.",'
        '"origin":"https://studio.test",'
        '"studio_check":"accepted",'
        '"token":{"created_at":"2026-10-04T05:17:09Z","expires_at":null,'
        '"id":"example-token-id","name":"junjo CLI on laptop",'
        '"scopes":["evaluation:read","evaluation:write","evidence:read"]}},'
        '"ok":true,"schema_version":1}\n'
    )
    assert ACCESS_TOKEN not in captured.out
    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/api/v1/evaluation-tokens/current"),
    ]
    assert requests[0].headers["authorization"] == f"Bearer {ACCESS_TOKEN}"


def test_status_reports_a_stored_credential_that_studio_rejects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store()

    async def handler(request: httpx.Request) -> httpx.Response:
        return _unauthorized()

    _studio(monkeypatch, handler)

    exit_code, payload, diagnostics = _run(capsys, "status")

    assert exit_code == EXIT_AUTHENTICATION
    assert diagnostics == ""
    assert payload == {
        "command": "auth.status",
        "data": {
            "credential_source": "stored",
            "credentials_path": str(credentials_path()),
            "message": (
                "Studio rejects the stored credential: the token was revoked or has expired. "
                "Run `junjo auth login` to sign in again."
            ),
            "origin": ORIGIN,
            "studio_check": "rejected",
            "token": None,
        },
        "ok": True,
        "schema_version": 1,
    }
    assert read_stored_credential(ORIGIN) is not None


def _poison_credential_file() -> Path:
    """Leave a file that fails any attempt to read it, to prove that nothing reads it."""

    path = credentials_path()
    path.parent.mkdir(mode=0o700)
    path.write_text("not json", encoding="utf-8")
    path.chmod(0o644)
    return path


def test_status_reports_an_accepted_environment_token_without_reading_the_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", ENVIRONMENT_TOKEN)
    _poison_credential_file()

    async def handler(request: httpx.Request) -> httpx.Response:
        return _current()

    requests = _studio(monkeypatch, handler)

    exit_code, payload, diagnostics = _run(capsys, "status")

    assert exit_code == EXIT_OK
    assert payload["data"] == {
        "credential_source": "environment",
        "credentials_path": None,
        "message": "Studio accepts the token in JUNJO_AI_STUDIO_CLI_TOKEN.",
        "origin": ORIGIN,
        "studio_check": "accepted",
        "token": {
            "created_at": "2026-10-04T05:17:09Z",
            "expires_at": None,
            "id": TOKEN_ID,
            "name": "junjo CLI on laptop",
            "scopes": ALL_SCOPES,
        },
    }
    assert requests[0].headers["authorization"] == f"Bearer {ENVIRONMENT_TOKEN}"
    assert ENVIRONMENT_TOKEN not in json.dumps(payload) + diagnostics


def test_status_reports_an_environment_token_that_studio_rejects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("JUNJO_AI_STUDIO_CLI_TOKEN", ENVIRONMENT_TOKEN)
    _store()

    async def handler(request: httpx.Request) -> httpx.Response:
        return _unauthorized()

    requests = _studio(monkeypatch, handler)

    exit_code, payload, _ = _run(capsys, "status")

    assert exit_code == EXIT_AUTHENTICATION
    assert payload["ok"] is True
    assert payload["data"]["credential_source"] == "environment"
    assert payload["data"]["studio_check"] == "rejected"
    assert payload["data"]["token"] is None
    assert payload["data"]["message"] == (
        "Studio rejects the token in JUNJO_AI_STUDIO_CLI_TOKEN: the token was revoked or has expired."
    )
    assert [request.headers["authorization"] for request in requests] == [f"Bearer {ENVIRONMENT_TOKEN}"]


def test_status_reports_no_credential_without_calling_studio(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store(OTHER_ORIGIN, OTHER_TOKEN, "other-token")

    exit_code, payload, diagnostics = _run(capsys, "status")

    assert exit_code == EXIT_AUTHENTICATION
    assert diagnostics == ""
    assert payload == {
        "command": "auth.status",
        "data": {
            "credential_source": "none",
            "credentials_path": str(credentials_path()),
            "message": (
                "No credential for https://studio.test. Run `junjo auth login`, or set JUNJO_AI_STUDIO_CLI_TOKEN."
            ),
            "origin": ORIGIN,
            "studio_check": "not_checked",
            "token": None,
        },
        "ok": True,
        "schema_version": 1,
    }


def test_status_reports_a_studio_that_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _store()

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    _studio(monkeypatch, handler)

    exit_code, payload, _ = _run(capsys, "status")

    assert exit_code == EXIT_TRANSIENT
    assert payload["ok"] is True
    assert payload["data"]["credential_source"] == "stored"
    assert payload["data"]["studio_check"] == "unreachable"
    assert payload["data"]["token"] is None
    assert payload["data"]["message"] == (
        "Studio could not be reached at https://studio.test, so the stored credential was not checked."
    )
    assert read_stored_credential(ORIGIN) is not None


def test_auth_commands_use_the_same_origin_resolution_as_every_other_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def origin_of(*arguments: str) -> str:
        exit_code = cli.main(["auth", *arguments, "status"])
        payload = json.loads(capsys.readouterr().out)
        assert exit_code == EXIT_AUTHENTICATION
        assert payload["data"]["credential_source"] == "none"
        return payload["data"]["origin"]

    assert origin_of() == "http://localhost:26154"

    monkeypatch.setenv("JUNJO_AI_STUDIO_BACKEND_BASE_URL", "https://environment.test/")
    assert origin_of() == "https://environment.test"
    assert origin_of("--studio-backend-base-url", "HTTPS://Flag.Test") == "https://flag.test"

    monkeypatch.setenv("JUNJO_AI_STUDIO_BACKEND_BASE_URL", "")
    exit_code = cli.main(["auth", "status"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == EXIT_USAGE
    assert payload["error"]["message"] == "JUNJO_AI_STUDIO_BACKEND_BASE_URL cannot be empty."
