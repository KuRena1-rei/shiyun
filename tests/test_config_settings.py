import json
from pathlib import Path


def _reset_manager():
    from core.settings_manager import SettingsManager
    SettingsManager._instance = None


def test_load_settings_returns_defaults(tmp_path, monkeypatch):
    """When no settings.json exists, load_settings should return defaults."""
    _reset_manager()
    monkeypatch.setattr("core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("core.config.SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr("core.settings_manager.SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr("core.settings_manager.CONFIG_DIR", tmp_path)
    (tmp_path / "settings.json").unlink(missing_ok=True)

    from core.config import load_settings
    result = load_settings()

    assert result.get("prevent_shutdown") is True
    assert result.get("startup_backup_reminder") is True
    assert result.get("minimize_to_tray") is True
    _reset_manager()


def test_load_settings_preserves_existing(tmp_path, monkeypatch):
    """Existing settings should not be overwritten by defaults."""
    _reset_manager()
    monkeypatch.setattr("core.config.CONFIG_DIR", tmp_path)
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("core.config.SETTINGS_FILE", settings_file)
    monkeypatch.setattr("core.settings_manager.SETTINGS_FILE", settings_file)
    monkeypatch.setattr("core.settings_manager.CONFIG_DIR", tmp_path)
    settings_file.write_text(json.dumps({"prevent_shutdown": False}), encoding="utf-8")

    from core.config import load_settings
    result = load_settings()

    assert result.get("prevent_shutdown") is False
    assert result.get("startup_backup_reminder") is True  # default
    assert result.get("minimize_to_tray") is True  # default
    _reset_manager()


def test_save_settings_persists(tmp_path, monkeypatch):
    """Saved settings should round-trip through file."""
    _reset_manager()
    monkeypatch.setattr("core.config.CONFIG_DIR", tmp_path)
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("core.config.SETTINGS_FILE", settings_file)
    monkeypatch.setattr("core.settings_manager.SETTINGS_FILE", settings_file)
    monkeypatch.setattr("core.settings_manager.CONFIG_DIR", tmp_path)

    from core.config import save_settings, load_settings
    save_settings({"prevent_shutdown": False, "startup_backup_reminder": False})
    result = load_settings()

    assert result.get("prevent_shutdown") is False
    assert result.get("startup_backup_reminder") is False
    assert result.get("minimize_to_tray") is True  # default preserved
    _reset_manager()
