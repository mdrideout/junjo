"""The developer access token that ``junjo auth login`` stores for each Studio origin.

The stored credential is one JSON file, ``credentials.json``, in a ``junjo``
directory inside the user's configuration directory:

- on POSIX systems, ``$XDG_CONFIG_HOME/junjo/credentials.json`` when
  ``XDG_CONFIG_HOME`` is set to an absolute path, otherwise
  ``~/.config/junjo/credentials.json``; and
- on Windows, ``%APPDATA%\\junjo\\credentials.json``.

The file holds one credential per Studio origin, so several Studio instances
can be signed in at once::

    {
      "credentials": {
        "http://localhost:26154": {
          "token": "jcli_...",
          "token_id": "example-token-id"
        }
      }
    }

The file is private to its owner. It is created with mode ``0600`` inside a
directory created with mode ``0700``, and every change replaces it atomically.
On POSIX systems a file that group or others can access is refused. A file that
does not match this format is an error that names its path; it is never
replaced silently.

``JUNJO_AI_STUDIO_CLI_TOKEN`` always takes precedence over this file. Nothing
here reads that variable: :mod:`junjo.cli.main` owns the resolution order, and
a command that needs a token does not read this file when the variable is set.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from ..studio.client import _validate_base_url

_WINDOWS = os.name == "nt"
_DIRECTORY_MODE = 0o700
_GROUP_AND_OTHERS = stat.S_IRWXG | stat.S_IRWXO


class CredentialFileError(Exception):
    """The stored credential file cannot be located, trusted, read, or written."""


class StoredCredential(BaseModel):
    """One developer access token stored for one Studio origin."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    token: SecretStr = Field(min_length=1)
    """Token value, held as a secret so representations never contain it."""
    token_id: str = Field(min_length=1)
    """Studio identifier of the token, as listed on the Developer Access Tokens page."""


class _CredentialFile(BaseModel):
    """Complete content of the credential file."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    credentials: dict[str, StoredCredential]


def studio_origin(base_url: str) -> str:
    """Return the Studio origin that keys a stored credential.

    The origin is the scheme, host, and port of the base URL exactly as
    :class:`junjo.studio.StudioClient` normalizes them: the scheme and host are
    lowercase, and the port is omitted when it is the scheme's default.
    ``http://LOCALHOST:26154/`` and ``http://localhost:26154`` are therefore one
    origin, while ``http://127.0.0.1:26154`` is a different one.

    :param base_url: Resolved Studio backend base URL.
    :return: The origin, such as ``http://localhost:26154``.
    :raises ValueError: If the base URL is not a Studio origin the client
        accepts.
    """

    url = httpx.URL(_validate_base_url(base_url))
    return f"{url.scheme}://{url.netloc.decode('ascii')}"


def credentials_path() -> Path:
    """Return where the credential file lives for the current user.

    :raises CredentialFileError: If Windows does not provide ``APPDATA``.
    """

    if _WINDOWS:
        application_data = os.environ.get("APPDATA")
        if not application_data:
            raise CredentialFileError("APPDATA is not set, so the credential file has no location.")
        return Path(application_data) / "junjo" / "credentials.json"
    # The XDG Base Directory Specification ignores an empty or relative value.
    configuration_home = os.environ.get("XDG_CONFIG_HOME")
    if configuration_home and os.path.isabs(configuration_home):
        return Path(configuration_home) / "junjo" / "credentials.json"
    return Path.home() / ".config" / "junjo" / "credentials.json"


def read_stored_credential(origin: str) -> StoredCredential | None:
    """Return the credential stored for a Studio origin, or None when there is none.

    :param origin: Origin returned by :func:`studio_origin`.
    :raises CredentialFileError: If the file can be accessed by group or
        others, cannot be read, or is not valid for this format.
    """

    return _read_file(credentials_path()).get(origin)


def store_credential(origin: str, credential: StoredCredential) -> None:
    """Store the credential for a Studio origin, replacing an earlier one for that origin.

    Credentials stored for other origins are kept.

    :param origin: Origin returned by :func:`studio_origin`.
    :param credential: Token and token identifier to store.
    :raises CredentialFileError: If the existing file cannot be used or the
        new file cannot be written.
    """

    path = credentials_path()
    credentials = _read_file(path)
    credentials[origin] = credential
    _write_file(path, credentials)


def delete_stored_credential(origin: str) -> None:
    """Delete the credential stored for a Studio origin.

    Credentials stored for other origins are kept. Deleting an origin that has
    no stored credential changes nothing.

    :param origin: Origin returned by :func:`studio_origin`.
    :raises CredentialFileError: If the existing file cannot be used or the
        new file cannot be written.
    """

    path = credentials_path()
    credentials = _read_file(path)
    if origin not in credentials:
        return
    del credentials[origin]
    _write_file(path, credentials)


def _read_file(path: Path) -> dict[str, StoredCredential]:
    try:
        with path.open("rb") as handle:
            if not _WINDOWS:
                mode = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
                if mode & _GROUP_AND_OTHERS:
                    raise CredentialFileError(
                        f"The credential file {path} can be accessed by group or others (mode {mode:04o}). "
                        "It holds developer access tokens and must be private to its owner. "
                        f"Run `chmod 600 {path}` and try again."
                    )
            content = handle.read()
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise CredentialFileError(f"Unable to read the credential file {path}: {error.strerror or error}.") from error
    try:
        return dict(_CredentialFile.model_validate_json(content).credentials)
    except ValidationError:
        # The validation error quotes the file's content, which holds tokens,
        # so it is deliberately not chained or repeated.
        raise CredentialFileError(
            f"The credential file {path} is not a valid Junjo credential file. "
            "Correct it or delete it, then run `junjo auth login`."
        ) from None


def _write_file(path: Path, credentials: dict[str, StoredCredential]) -> None:
    content = json.dumps(
        {
            "credentials": {
                origin: {
                    "token": credential.token.get_secret_value(),
                    "token_id": credential.token_id,
                }
                for origin, credential in sorted(credentials.items())
            }
        },
        indent=2,
    )
    try:
        path.parent.mkdir(mode=_DIRECTORY_MODE, parents=True, exist_ok=True)
        # mkstemp creates the sibling file readable and writable by its owner
        # only, so the token is never on disk with broader permissions.
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content + "\n")
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    except OSError as error:
        raise CredentialFileError(f"Unable to write the credential file {path}: {error.strerror or error}.") from error
