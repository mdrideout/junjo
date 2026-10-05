"""The ``junjo auth`` commands: browser sign-in, sign-out, and credential status.

``junjo auth login`` follows the OAuth device authorization grant (RFC 8628)
in Studio's own JSON conventions. The terminal starts a sign-in, shows a short
code, and polls. A person signed in to Studio compares the code on the approval
page and approves or denies. Approval mints an ordinary developer access token,
which the terminal collects once and stores for that Studio origin.

Each command returns a closed result that :mod:`junjo.cli.main` writes as the
data of the one JSON envelope on standard output. The lines a person reads
while a sign-in waits go to standard error. No command accepts a Studio
password, and none prints a token value.

:mod:`junjo.cli.main` resolves the Studio origin and reads
``JUNJO_AI_STUDIO_CLI_TOKEN``. The functions here receive both as arguments and
never read that variable themselves.
"""

from __future__ import annotations

import asyncio
import socket
import sys
import webbrowser
from collections.abc import Sequence
from typing import Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, SecretStr

from ..studio import (
    CliSignInExpired,
    CliSignInPending,
    CliSignInStart,
    CliSignInStarted,
    CliSignInToken,
    CurrentTokenRead,
    StudioAuthenticationError,
    StudioClient,
    StudioTransientError,
    TokenScope,
)
from .credentials import (
    StoredCredential,
    credentials_path,
    delete_stored_credential,
    read_stored_credential,
    store_credential,
)

_ENVIRONMENT_TOKEN = "JUNJO_AI_STUDIO_CLI_TOKEN"


class AuthResult(BaseModel):
    """Closed immutable result of one ``junjo auth`` command."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AuthLogin(AuthResult):
    """Result of ``junjo auth login``. It never contains the token value."""

    origin: str
    """Studio origin the terminal signed in to; the stored credential is keyed by it."""
    token_id: str
    """Studio identifier of the minted token, as listed on the Developer Access Tokens page."""
    scopes: tuple[TokenScope, ...]
    """Scopes the minted token holds."""
    credentials_path: str
    """File the token was stored in."""
    environment_token_set: bool
    """True when JUNJO_AI_STUDIO_CLI_TOKEN is set: commands keep using it instead of what was just stored."""
    message: str
    """Plain-language summary of what happened."""


class AuthLogout(AuthResult):
    """Result of ``junjo auth logout``."""

    origin: str
    """Studio origin whose stored credential was signed out."""
    credentials_path: str
    """File the stored credential was looked for in."""
    stored_credential: Literal["deleted", "none"]
    """Whether a stored credential for the origin was deleted or there was none."""
    token_id: str | None
    """Studio identifier of the token the stored credential held; None when nothing was stored."""
    revocation: Literal["revoked", "rejected", "unreachable", "not_attempted"]
    """What Studio did with the token: revoked it now, already rejected it, could not be reached, or was not asked."""
    environment_token_set: bool
    """True when JUNJO_AI_STUDIO_CLI_TOKEN is set: commands keep using it after this sign-out."""
    message: str
    """Plain-language summary of what happened."""


class AuthStatus(AuthResult):
    """Result of ``junjo auth status``. It never contains the token value."""

    origin: str
    """Studio origin the status is about."""
    credential_source: Literal["environment", "stored", "none"]
    """Where commands that need a token get it for this origin."""
    credentials_path: str | None
    """File consulted for a stored credential; None when the environment variable made it unnecessary."""
    studio_check: Literal["accepted", "rejected", "unreachable", "not_checked"]
    """Whether Studio accepts the credential; not_checked when there is no credential to check."""
    token: CurrentTokenRead | None
    """Identifier, name, scopes, expiry, and creation time Studio reports for an accepted token."""
    message: str
    """Plain-language summary of the status."""


async def login(
    *,
    base_url: str,
    origin: str,
    client_name: str | None,
    scopes: Sequence[TokenScope] | None,
    open_browser: bool,
    environment_token_set: bool,
) -> AuthLogin:
    """Sign this terminal in to Studio through the browser and store the minted token.

    :param base_url: Resolved Studio backend base URL.
    :param origin: Studio origin of ``base_url``; it keys the stored credential
        and is where the approval page is opened.
    :param client_name: Name shown on the approval page and given to the
        token. None uses ``junjo CLI on <hostname>``.
    :param scopes: Scopes to ask for. None asks for every scope.
    :param open_browser: Whether to open the approval page in the default
        browser. The page address is printed either way.
    :param environment_token_set: Whether ``JUNJO_AI_STUDIO_CLI_TOKEN`` is set.
    :return: Where the token was stored and what it may do, without its value.
    :raises CliSignInDenied: If a person denied the sign-in.
    :raises CliSignInExpired: If the sign-in expired before it was approved.
    """

    # A credential file that cannot be used must stop the sign-in before a
    # person is asked to approve anything.
    read_stored_credential(origin)
    request = CliSignInStart(
        client_name=f"junjo CLI on {socket.gethostname()}" if client_name is None else client_name,
        scopes=tuple(TokenScope) if scopes is None else tuple(scopes),
    )
    async with StudioClient(base_url=base_url) as client:
        started = await client.start_cli_sign_in(request)
        approval_page = f"{origin}{started.verification_path}?{urlencode({'code': started.user_code})}"
        _tell(f"Sign-in code: {started.user_code}")
        _tell(f"Approval page: {approval_page}")
        if not open_browser:
            _tell("Open the approval page in your browser.")
        elif _open_browser(approval_page):
            _tell("The approval page was opened in your browser.")
        else:
            _tell("A browser could not be opened. Open the approval page in your browser.")
        _tell("Approve the sign-in only if the page shows the same code.")
        _tell(f"Waiting for approval. The code expires in {started.expires_in} seconds.")
        collected = await _collect_token(client, started)

    store_credential(
        origin,
        StoredCredential(token=collected.access_token, token_id=collected.token_id),
    )
    path = credentials_path()
    message = f"Signed in to {origin}. The developer access token is stored in {path}."
    if environment_token_set:
        message += f" {_ENVIRONMENT_TOKEN} is set and takes precedence, so commands keep using it."
    return AuthLogin(
        origin=origin,
        token_id=collected.token_id,
        scopes=collected.scopes,
        credentials_path=str(path),
        environment_token_set=environment_token_set,
        message=message,
    )


async def logout(
    *,
    base_url: str,
    origin: str,
    environment_token_set: bool,
) -> AuthLogout:
    """Revoke the token stored for a Studio origin and delete the stored copy.

    The stored copy is deleted even when Studio cannot be reached or already
    rejects the token. ``JUNJO_AI_STUDIO_CLI_TOKEN`` is never used or changed.

    :param base_url: Resolved Studio backend base URL.
    :param origin: Studio origin of ``base_url``; it keys the stored credential.
    :param environment_token_set: Whether ``JUNJO_AI_STUDIO_CLI_TOKEN`` is set.
    :return: What was deleted and what Studio did with the token.
    """

    environment_note = f" {_ENVIRONMENT_TOKEN} is set, so commands keep using it." if environment_token_set else ""
    path = str(credentials_path())
    stored = read_stored_credential(origin)
    if stored is None:
        return AuthLogout(
            origin=origin,
            credentials_path=path,
            stored_credential="none",
            token_id=None,
            revocation="not_attempted",
            environment_token_set=environment_token_set,
            message=f"No credential is stored for {origin}.{environment_note}",
        )

    revocation = await _revoke(base_url, stored)
    delete_stored_credential(origin)
    if revocation == "revoked":
        message = f"Studio revoked the token. The stored credential for {origin} was deleted."
    elif revocation == "rejected":
        message = (
            "Studio already rejects the token: it was revoked or has expired. "
            f"The stored credential for {origin} was deleted."
        )
    else:
        message = (
            "Studio could not be reached, so the token was not revoked. "
            f"The stored credential for {origin} was deleted. "
            f"Delete token {stored.token_id} on the Developer Access Tokens page in Studio."
        )
    return AuthLogout(
        origin=origin,
        credentials_path=path,
        stored_credential="deleted",
        token_id=stored.token_id,
        revocation=revocation,
        environment_token_set=environment_token_set,
        message=f"{message}{environment_note}",
    )


async def status(
    *,
    base_url: str,
    origin: str,
    environment_token: str | None,
) -> AuthStatus:
    """Report which credential commands use for a Studio origin and whether Studio accepts it.

    The stored credential is not read when the environment variable provides a
    token. A rejected or unreachable result is part of the returned status
    rather than an error.

    :param base_url: Resolved Studio backend base URL.
    :param origin: Studio origin of ``base_url``; it keys the stored credential.
    :param environment_token: Value of ``JUNJO_AI_STUDIO_CLI_TOKEN``, or None
        when it is not set.
    :return: The credential source and Studio's answer, without a token value.
    """

    if environment_token is not None:
        return await _checked_status(
            base_url=base_url,
            origin=origin,
            credential_source="environment",
            path=None,
            token=environment_token,
        )

    path = str(credentials_path())
    stored = read_stored_credential(origin)
    if stored is None:
        return AuthStatus(
            origin=origin,
            credential_source="none",
            credentials_path=path,
            studio_check="not_checked",
            token=None,
            message=f"No credential for {origin}. Run `junjo auth login`, or set {_ENVIRONMENT_TOKEN}.",
        )
    return await _checked_status(
        base_url=base_url,
        origin=origin,
        credential_source="stored",
        path=path,
        token=stored.token,
    )


async def _checked_status(
    *,
    base_url: str,
    origin: str,
    credential_source: Literal["environment", "stored"],
    path: str | None,
    token: str | SecretStr,
) -> AuthStatus:
    """Ask Studio to describe the credential and report its answer."""

    described = f"token in {_ENVIRONMENT_TOKEN}" if credential_source == "environment" else "stored credential"
    try:
        async with StudioClient(base_url=base_url, token=token) as client:
            current = await client.get_current_token()
    except StudioAuthenticationError:
        message = f"Studio rejects the {described}: the token was revoked or has expired."
        if credential_source == "stored":
            message += " Run `junjo auth login` to sign in again."
        return AuthStatus(
            origin=origin,
            credential_source=credential_source,
            credentials_path=path,
            studio_check="rejected",
            token=None,
            message=message,
        )
    except StudioTransientError:
        return AuthStatus(
            origin=origin,
            credential_source=credential_source,
            credentials_path=path,
            studio_check="unreachable",
            token=None,
            message=f"Studio could not be reached at {origin}, so the {described} was not checked.",
        )
    return AuthStatus(
        origin=origin,
        credential_source=credential_source,
        credentials_path=path,
        studio_check="accepted",
        token=current,
        message=f"Studio accepts the {described}.",
    )


async def _collect_token(client: StudioClient, started: CliSignInStarted) -> CliSignInToken:
    """Poll at the interval Studio gave until the sign-in is decided or its lifetime has passed."""

    waited = 0
    while waited < started.expires_in:
        await _wait(started.interval)
        waited += started.interval
        try:
            return await client.collect_cli_sign_in_token(started.device_code)
        except CliSignInPending:
            continue
    raise CliSignInExpired()


async def _revoke(base_url: str, stored: StoredCredential) -> Literal["revoked", "rejected", "unreachable"]:
    """Ask Studio to delete the stored token and report what Studio did."""

    try:
        async with StudioClient(base_url=base_url, token=stored.token) as client:
            await client.delete_current_token()
    except StudioAuthenticationError:
        return "rejected"
    except StudioTransientError:
        return "unreachable"
    return "revoked"


async def _wait(seconds: int) -> None:
    """Wait between two attempts to collect the token."""

    await asyncio.sleep(seconds)


def _open_browser(address: str) -> bool:
    """Open an address in the default browser and report whether a browser was opened."""

    try:
        return webbrowser.open(address)
    except (webbrowser.Error, OSError):
        return False


def _tell(line: str) -> None:
    """Write one line for a person to standard error; standard output carries only the JSON envelope."""

    print(line, file=sys.stderr)
