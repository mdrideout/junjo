"""Isolation shared by every SDK test."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_user_configuration(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch):
    """Point the user's configuration directory at a temporary directory.

    The CLI stores the credential from ``junjo auth login`` in the user's
    configuration directory and looks there whenever
    ``JUNJO_AI_STUDIO_CLI_TOKEN`` is not set. No test may read or write the
    real directory, so every test gets its own empty one.
    """

    directory = tmp_path_factory.mktemp("user-configuration")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(directory))
    monkeypatch.setenv("APPDATA", str(directory))
    return directory
