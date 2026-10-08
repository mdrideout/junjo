"""Storage contracts for the credential that ``junjo auth login`` keeps."""

from __future__ import annotations

import json
import os
import stat
import traceback
from pathlib import Path

import pytest

from junjo.cli import credentials
from junjo.cli.credentials import (
    CredentialFileError,
    StoredCredential,
    credentials_path,
    delete_stored_credential,
    read_stored_credential,
    store_credential,
    studio_origin,
)

LOCAL = "http://localhost:26154"
REMOTE = "https://studio.example.com"
LOCAL_TOKEN = "jcli_" + "l" * 64
REMOTE_TOKEN = "jcli_" + "r" * 64

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file permissions")


def _credential(token: str, token_id: str) -> StoredCredential:
    return StoredCredential(token=token, token_id=token_id)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_credential_file_lives_in_the_xdg_configuration_directory(isolated_user_configuration: Path) -> None:
    assert credentials_path() == isolated_user_configuration / "junjo" / "credentials.json"


@pytest.mark.parametrize("configuration_home", [None, "", "relative/configuration"])
def test_credential_file_defaults_to_the_home_configuration_directory(
    configuration_home: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    if configuration_home is None:
        monkeypatch.delenv("XDG_CONFIG_HOME")
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", configuration_home)

    assert credentials_path() == tmp_path / ".config" / "junjo" / "credentials.json"


def test_credential_file_lives_in_application_data_on_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(credentials, "_WINDOWS", True)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert credentials_path() == tmp_path / "junjo" / "credentials.json"

    monkeypatch.delenv("APPDATA")
    with pytest.raises(CredentialFileError, match="APPDATA"):
        credentials_path()


@pytest.mark.parametrize(
    ("base_url", "origin"),
    [
        ("http://localhost:26154", "http://localhost:26154"),
        ("http://localhost:26154/", "http://localhost:26154"),
        ("HTTP://LOCALHOST:26154/", "http://localhost:26154"),
        ("http://127.0.0.1:26154", "http://127.0.0.1:26154"),
        ("http://[::1]:26154", "http://[::1]:26154"),
        ("https://studio.example.com", "https://studio.example.com"),
        ("https://Studio.Example.com:443/", "https://studio.example.com"),
        ("https://studio.example.com:8443", "https://studio.example.com:8443"),
    ],
)
def test_origin_is_the_scheme_host_and_port_as_the_client_normalizes_them(base_url: str, origin: str) -> None:
    assert studio_origin(base_url) == origin


@pytest.mark.parametrize(
    ("base_url", "reason"),
    [
        ("studio.example.com", "absolute HTTP or HTTPS"),
        ("http://studio.example.com", "loopback"),
        ("https://studio.example.com/prefix", "application path"),
        ("https://user:password@studio.example.com", "credentials"),
    ],
)
def test_origin_rejects_what_the_client_rejects(base_url: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        studio_origin(base_url)


def test_reading_without_a_file_finds_nothing_and_creates_nothing(isolated_user_configuration: Path) -> None:
    assert read_stored_credential(LOCAL) is None
    delete_stored_credential(LOCAL)

    assert list(isolated_user_configuration.iterdir()) == []


@posix_only
def test_store_creates_an_owner_only_directory_and_file() -> None:
    store_credential(LOCAL, _credential(LOCAL_TOKEN, "local-token"))

    path = credentials_path()
    assert _mode(path.parent) == 0o700
    assert _mode(path) == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "credentials": {
            LOCAL: {"token": LOCAL_TOKEN, "token_id": "local-token"},
        }
    }
    stored = read_stored_credential(LOCAL)
    assert stored is not None
    assert stored.token.get_secret_value() == LOCAL_TOKEN
    assert stored.token_id == "local-token"
    assert LOCAL_TOKEN not in repr(stored)


def test_credentials_are_keyed_by_origin_so_several_studios_stay_signed_in() -> None:
    store_credential(LOCAL, _credential(LOCAL_TOKEN, "local-token"))
    store_credential(REMOTE, _credential(REMOTE_TOKEN, "remote-token"))
    store_credential(LOCAL, _credential(LOCAL_TOKEN, "replaced-local-token"))

    local = read_stored_credential(LOCAL)
    remote = read_stored_credential(REMOTE)
    assert local is not None and local.token_id == "replaced-local-token"
    assert remote is not None and remote.token.get_secret_value() == REMOTE_TOKEN
    assert read_stored_credential("http://127.0.0.1:26154") is None

    delete_stored_credential(LOCAL)

    assert read_stored_credential(LOCAL) is None
    assert read_stored_credential(REMOTE) == remote


@posix_only
def test_every_change_replaces_the_file_from_an_owner_only_sibling(monkeypatch: pytest.MonkeyPatch) -> None:
    replacements: list[tuple[Path, Path, int]] = []
    replace = os.replace

    def recording_replace(source: str, destination: Path) -> None:
        replacements.append((Path(source), Path(destination), _mode(Path(source))))
        replace(source, destination)

    monkeypatch.setattr(credentials.os, "replace", recording_replace)
    path = credentials_path()

    store_credential(LOCAL, _credential(LOCAL_TOKEN, "local-token"))
    delete_stored_credential(LOCAL)

    assert len(replacements) == 2
    for source, destination, source_mode in replacements:
        assert destination == path
        assert source.parent == path.parent
        assert source != path
        assert source_mode == 0o600
    assert [item.name for item in path.parent.iterdir()] == ["credentials.json"]
    assert _mode(path) == 0o600


def test_a_failed_replace_keeps_the_previous_file_and_leaves_no_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_credential(LOCAL, _credential(LOCAL_TOKEN, "local-token"))
    path = credentials_path()
    before = path.read_bytes()

    def failing_replace(source: str, destination: Path) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(credentials.os, "replace", failing_replace)

    with pytest.raises(CredentialFileError) as failure:
        store_credential(REMOTE, _credential(REMOTE_TOKEN, "remote-token"))

    assert str(path) in str(failure.value)
    assert "No space left on device" in str(failure.value)
    assert REMOTE_TOKEN not in str(failure.value)
    assert path.read_bytes() == before
    assert [item.name for item in path.parent.iterdir()] == ["credentials.json"]


@posix_only
@pytest.mark.parametrize("mode", [0o640, 0o604, 0o620, 0o644])
def test_a_file_that_group_or_others_can_access_is_refused_with_the_fix(mode: int) -> None:
    store_credential(LOCAL, _credential(LOCAL_TOKEN, "local-token"))
    path = credentials_path()
    path.chmod(mode)
    before = path.read_bytes()

    for use in (
        lambda: read_stored_credential(LOCAL),
        lambda: store_credential(REMOTE, _credential(REMOTE_TOKEN, "remote-token")),
        lambda: delete_stored_credential(LOCAL),
    ):
        with pytest.raises(CredentialFileError) as refusal:
            use()
        assert str(path) in str(refusal.value)
        assert f"mode {mode:04o}" in str(refusal.value)
        assert f"chmod 600 {path}" in str(refusal.value)

    assert path.read_bytes() == before
    assert _mode(path) == mode

    path.chmod(0o600)
    assert read_stored_credential(LOCAL) is not None


@pytest.mark.parametrize(
    "content",
    [
        "",
        "not json",
        "[]",
        "{}",
        '{"credentials": []}',
        '{"credentials": {}, "version": 2}',
        '{"credentials": {"http://localhost:26154": "jcli_private-value"}}',
        '{"credentials": {"http://localhost:26154": {"token": "jcli_private-value"}}}',
        '{"credentials": {"http://localhost:26154": {"token": "", "token_id": "local-token"}}}',
        '{"credentials": {"http://localhost:26154": {"token": "jcli_private-value", "token_id": 7}}}',
        '{"credentials": {"http://localhost:26154": {"token": "jcli_private-value", "token_id": "a", "x": 1}}}',
    ],
)
def test_an_invalid_file_is_an_error_that_names_the_path_and_is_never_replaced(content: str) -> None:
    path = credentials_path()
    path.parent.mkdir(mode=0o700)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)

    for use in (
        lambda: read_stored_credential(LOCAL),
        lambda: store_credential(LOCAL, _credential(LOCAL_TOKEN, "local-token")),
        lambda: delete_stored_credential(LOCAL),
    ):
        with pytest.raises(CredentialFileError) as invalid:
            use()
        assert str(path) in str(invalid.value)
        assert "not a valid Junjo credential file" in str(invalid.value)
        # Neither the message nor a rendered traceback may quote the file, which holds tokens.
        assert "jcli_private-value" not in "".join(traceback.format_exception(invalid.value))

    assert path.read_text(encoding="utf-8") == content
    assert [item.name for item in path.parent.iterdir()] == ["credentials.json"]
