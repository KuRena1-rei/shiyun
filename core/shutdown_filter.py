from __future__ import annotations

# core/shutdown_filter.py
"""
QAbstractNativeEventFilter to intercept WM_QUERYENDSESSION.
Uses Windows ShutdownBlockReasonCreate to show a reason on the shutdown screen.
"""
import ctypes
import ctypes.wintypes
from typing import Any, Tuple

from PySide6.QtCore import QAbstractNativeEventFilter

WM_QUERYENDSESSION = 0x0011

_main_window = None


def set_main_window(window: Any) -> None:
    global _main_window
    _main_window = window


class ShutdownFilter(QAbstractNativeEventFilter):

    def nativeEventFilter(self, eventType: bytes, message: Any) -> Tuple[bool, int]:
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_QUERYENDSESSION:
                if _should_block_shutdown():
                    _show_block_reason()
                    return True, 0  # Block shutdown
                else:
                    return True, 1  # Allow shutdown
        return False, 0


def _should_block_shutdown() -> bool:
    if _main_window is None:
        return False
    try:
        from core.settings_manager import SettingsManager
        from core.config import has_upcoming_backup
        mgr = SettingsManager.instance()
        if not mgr.get("prevent_shutdown", True):
            return False
        if not has_upcoming_backup(hours=12):
            return False
        return True
    except Exception:
        return False


def _show_block_reason() -> None:
    if _main_window is None:
        return
    try:
        hwnd = int(_main_window.winId())
        reason = "拾云有备份任务即将执行，请勿关机".encode("utf-16-le") + b"\x00\x00"
        ctypes.windll.kernel32.ShutdownBlockReasonCreate(hwnd, reason)
    except Exception:
        pass
