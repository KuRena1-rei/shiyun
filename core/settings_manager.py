from __future__ import annotations

import json
from typing import Any
from PySide6.QtCore import QObject, Signal

from core.config import (
    CONFIG_DIR, SETTINGS_FILE, DEFAULT_SETTINGS,
    is_auto_start_enabled, set_auto_start, _ensure_config_dir,
)


class SettingsManager(QObject):
    """Unified settings manager. Single source of truth for all app settings."""

    _instance = None

    setting_changed = Signal(str, object)  # (key, value)

    def __init__(self) -> None:
        super().__init__()
        self._data = {}
        self._load()

    @classmethod
    def instance(cls) -> SettingsManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        if key == "auto_start":
            mode = self._data.get("auto_start_mode", "minimize")
            set_auto_start(value, mode)
        else:
            self._save()
        self.setting_changed.emit(key, value)

    def _load(self) -> None:
        _ensure_config_dir()
        self._data = dict(DEFAULT_SETTINGS)
        self._data["auto_start"] = is_auto_start_enabled()
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    self._data.update(json.load(f))
            except (json.JSONDecodeError, ValueError):
                pass

    def _save(self) -> None:
        _ensure_config_dir()
        to_save = {k: v for k, v in self._data.items() if k != "auto_start"}
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=2, ensure_ascii=False)
