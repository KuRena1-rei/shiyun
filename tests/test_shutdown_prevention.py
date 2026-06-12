# tests/test_shutdown_prevention.py
"""Tests for shutdown prevention logic."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock


# === has_upcoming_backup tests ===


def test_has_upcoming_backup_with_scheduled_backup(tmp_path):
    """has_upcoming_backup returns True when backup is scheduled within N hours."""
    from core.config import has_upcoming_backup

    backups = [
        {
            "id": 1,
            "schedule_enabled": True,
            "next_run": (datetime.now() + timedelta(hours=2)).isoformat(),
        }
    ]
    with patch("core.config.load_backups", return_value=backups):
        assert has_upcoming_backup(hours=12) is True


def test_has_upcoming_backup_no_scheduled_backup(tmp_path):
    """has_upcoming_backup returns False when no backup is scheduled."""
    from core.config import has_upcoming_backup

    backups = [
        {
            "id": 1,
            "schedule_enabled": False,
            "next_run": (datetime.now() + timedelta(hours=2)).isoformat(),
        }
    ]
    with patch("core.config.load_backups", return_value=backups):
        assert has_upcoming_backup(hours=12) is False


def test_has_upcoming_backup_far_future(tmp_path):
    """has_upcoming_backup returns False when backup is beyond the window."""
    from core.config import has_upcoming_backup

    backups = [
        {
            "id": 1,
            "schedule_enabled": True,
            "next_run": (datetime.now() + timedelta(hours=24)).isoformat(),
        }
    ]
    with patch("core.config.load_backups", return_value=backups):
        assert has_upcoming_backup(hours=12) is False


# === ShutdownFilter tests ===


def test_shutdown_filter_imports():
    """ShutdownFilter should be importable."""
    from core.shutdown_filter import ShutdownFilter
    assert ShutdownFilter is not None


def test_shutdown_filter_exists():
    """shutdown_filter.py should exist."""
    filter_path = Path(__file__).parent.parent / "core" / "shutdown_filter.py"
    assert filter_path.exists()


def test_shutdown_filter_has_native_event_filter():
    """ShutdownFilter should have nativeEventFilter method."""
    from core.shutdown_filter import ShutdownFilter
    f = ShutdownFilter()
    assert hasattr(f, "nativeEventFilter")


def test_shutdown_filter_blocks_with_upcoming_backup():
    """ShutdownFilter should block shutdown when backup is upcoming."""
    from core.shutdown_filter import ShutdownFilter, set_main_window

    mock_window = MagicMock()
    mock_window.winId.return_value = 12345
    set_main_window(mock_window)

    f = ShutdownFilter()
    with patch("core.shutdown_filter._main_window", mock_window):
        with patch("core.shutdown_filter._should_block_shutdown", return_value=True):
            import ctypes
            import ctypes.wintypes

            msg = ctypes.wintypes.MSG()
            msg.message = 0x0011
            msg_ptr = ctypes.addressof(msg)

            with patch("core.shutdown_filter.ctypes.wintypes.MSG.from_address", return_value=msg):
                result = f.nativeEventFilter(b"windows_generic_MSG", msg_ptr)
                assert result == (True, 0)  # Block shutdown


def test_shutdown_filter_allows_without_backup():
    """ShutdownFilter should allow shutdown when no backup is upcoming."""
    from core.shutdown_filter import ShutdownFilter, set_main_window

    mock_window = MagicMock()
    set_main_window(mock_window)

    f = ShutdownFilter()
    with patch("core.shutdown_filter._main_window", mock_window):
        with patch("core.shutdown_filter._should_block_shutdown", return_value=False):
            import ctypes
            import ctypes.wintypes

            msg = ctypes.wintypes.MSG()
            msg.message = 0x0011
            msg_ptr = ctypes.addressof(msg)

            with patch("core.shutdown_filter.ctypes.wintypes.MSG.from_address", return_value=msg):
                result = f.nativeEventFilter(b"windows_generic_MSG", msg_ptr)
                assert result == (True, 1)  # Allow shutdown


def test_shutdown_filter_ignores_other_messages():
    """ShutdownFilter should not intercept non-WM_QUERYENDSESSION messages."""
    from core.shutdown_filter import ShutdownFilter

    f = ShutdownFilter()
    import ctypes
    import ctypes.wintypes

    msg = ctypes.wintypes.MSG()
    msg.message = 0x000F  # WM_PAINT
    msg_ptr = ctypes.addressof(msg)

    with patch("core.shutdown_filter.ctypes.wintypes.MSG.from_address", return_value=msg):
        result = f.nativeEventFilter(b"windows_generic_MSG", msg_ptr)
        assert result == (False, 0)  # Don't intercept


# === Settings defaults ===


def test_settings_defaults():
    """Settings should have prevent_shutdown enabled."""
    from core.config import DEFAULT_SETTINGS
    assert DEFAULT_SETTINGS.get("prevent_shutdown") is True
    assert DEFAULT_SETTINGS.get("startup_backup_reminder") is True
    assert DEFAULT_SETTINGS.get("minimize_to_tray") is True
