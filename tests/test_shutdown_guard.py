# tests/test_shutdown_guard.py
"""Tests for simplified shutdown prevention."""

def test_shutdown_guard_file_removed():
    """shutdown_guard.py should no longer exist (replaced by native ShutdownBlockReasonCreate)."""
    from pathlib import Path
    guard_path = Path(__file__).parent.parent / "shutdown_guard.py"
    assert not guard_path.exists(), "shutdown_guard.py should be deleted"


def test_shutdown_dialog_file_removed():
    """shutdown_dialog.py should no longer exist."""
    from pathlib import Path
    dialog_path = Path(__file__).parent.parent / "ui" / "shutdown_dialog.py"
    assert not dialog_path.exists(), "shutdown_dialog.py should be deleted"


def test_shutdown_filter_simplified():
    """ShutdownFilter should not have _launch_guard method."""
    from core.shutdown_filter import ShutdownFilter
    f = ShutdownFilter()
    assert not hasattr(f, "_launch_guard"), "shutdown_guard launch should be removed"
