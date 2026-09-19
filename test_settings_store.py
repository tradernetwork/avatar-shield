"""Unit tests for settings_store.py — no Discord connection required.

Run with:  pytest -q
"""
import pytest

import settings_store


def test_get_returns_defaults_when_no_row_exists(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        result = store.get(123)
        assert result.guild_id == 123
        assert result.mod_log_channel_id is None
        assert result.mode is None
        assert result.protected_user_ids == set()
        assert result.threshold_ban is None
        assert result.threshold_alert is None
    finally:
        store.close()


def test_set_mod_log_channel_persists(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        store.set_mod_log_channel(123, 555)
        assert store.get(123).mod_log_channel_id == 555
    finally:
        store.close()


def test_set_mode_persists_and_validates(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        store.set_mode(123, "ban")
        assert store.get(123).mode == "ban"
        store.set_mode(123, "alert")
        assert store.get(123).mode == "alert"
        with pytest.raises(ValueError):
            store.set_mode(123, "bogus")
    finally:
        store.close()


def test_protected_users_add_remove(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        store.add_protected_user(123, 1)
        store.add_protected_user(123, 2)
        assert store.get(123).protected_user_ids == {1, 2}
        store.add_protected_user(123, 1)
        assert store.get(123).protected_user_ids == {1, 2}
        store.remove_protected_user(123, 1)
        assert store.get(123).protected_user_ids == {2}
        store.remove_protected_user(123, 999)
    finally:
        store.close()


def test_protected_users_independent_of_other_settings(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        store.add_protected_user(123, 1)
        result = store.get(123)
        assert result.protected_user_ids == {1}
        assert result.mod_log_channel_id is None
        assert result.mode is None
    finally:
        store.close()


def test_set_thresholds_persists(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        store.set_thresholds(123, 4, 12)
        result = store.get(123)
        assert result.threshold_ban == 4
        assert result.threshold_alert == 12
        store.set_thresholds(123, None, None)
        result = store.get(123)
        assert result.threshold_ban is None
        assert result.threshold_alert is None
    finally:
        store.close()


def test_settings_are_per_guild(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        store.set_mod_log_channel(1, 100)
        store.set_mode(1, "ban")
        store.add_protected_user(1, 42)
        result2 = store.get(2)
        assert result2.mod_log_channel_id is None
        assert result2.mode is None
        assert result2.protected_user_ids == set()
    finally:
        store.close()


def test_persists_across_reconnect(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        store.set_mod_log_channel(123, 555)
        store.set_mode(123, "ban")
        store.add_protected_user(123, 99)
        store.close()
        new_store = settings_store.SettingsStore(str(db_path))
        try:
            result = new_store.get(123)
            assert result.mod_log_channel_id == 555
            assert result.mode == "ban"
            assert result.protected_user_ids == {99}
        finally:
            new_store.close()
    finally:
        pass  # already closed above before reopening


def test_resolve_db_path_returns_configured_when_writable(tmp_path):
    path = tmp_path / "sub" / "avatar-shield.db"
    resolved = settings_store.resolve_db_path(str(path))
    assert resolved == str(path)
    assert (tmp_path / "sub").is_dir()


def test_resolve_db_path_falls_back_when_directory_is_not_creatable(tmp_path):
    blocked = tmp_path / "blocked"
    blocked.touch()
    path = tmp_path / "blocked" / "avatar-shield.db"
    resolved = settings_store.resolve_db_path(str(path))
    assert resolved == "./avatar-shield.db"


def test_get_after_ensure_row_created_by_a_setter_has_none_mode_still_distinguishable(tmp_path):
    db_path = tmp_path / "test.db"
    store = settings_store.SettingsStore(str(db_path))
    try:
        store.add_protected_user(456, 1)
        result = store.get(456)
        assert result.mode is None
    finally:
        store.close()