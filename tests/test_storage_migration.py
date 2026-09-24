"""The 2.1.x -> 2.2.0 storage move.

Before the HOME redirect, colab_cli's files were forced flat into
``storage/``. After it they resolve under ``storage/home/.config/...``.
Without the migration an upgrading user loses login, sessions, and
history — the exact regression this guards.
"""

import json
import os

import pytest

from core.storage_patch import migrate_legacy_colab_paths, resolve_storage_dir


@pytest.fixture
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path))
    base = resolve_storage_dir()
    os.makedirs(base, exist_ok=True)
    return base


def test_migrates_flat_2_1_files(storage):
    with open(os.path.join(storage, "token.json"), "w") as f:
        json.dump({"token": "abc"}, f)
    with open(os.path.join(storage, "sessions.json"), "w") as f:
        json.dump({"mine": {"name": "mine"}}, f)
    with open(os.path.join(storage, "oauth_config.json"), "w") as f:
        json.dump({"installed": {"client_id": "x"}}, f)
    history = os.path.join(storage, "history")
    os.makedirs(history)
    with open(os.path.join(history, "old.jsonl"), "w") as f:
        f.write("{}\n")

    copied = migrate_legacy_colab_paths()
    assert copied == 4

    config_dir = os.path.join(storage, "home", ".config", "colab-cli")
    with open(os.path.join(config_dir, "token.json")) as f:
        assert json.load(f)["token"] == "abc"
    with open(os.path.join(config_dir, "sessions.json")) as f:
        assert "mine" in json.load(f)
    with open(os.path.join(storage, "home", ".colab-cli-oauth-config.json")) as f:
        assert json.load(f)["installed"]["client_id"] == "x"
    assert os.path.isfile(os.path.join(config_dir, "history", "old.jsonl"))


def test_never_overwrites_new_layout(storage):
    config_dir = os.path.join(storage, "home", ".config", "colab-cli")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "token.json"), "w") as f:
        json.dump({"token": "new"}, f)
    with open(os.path.join(storage, "token.json"), "w") as f:
        json.dump({"token": "old"}, f)

    assert migrate_legacy_colab_paths() == 0
    with open(os.path.join(config_dir, "token.json")) as f:
        assert json.load(f)["token"] == "new"


def test_noop_on_fresh_install(storage):
    assert migrate_legacy_colab_paths() == 0
