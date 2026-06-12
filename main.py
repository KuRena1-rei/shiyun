import os
os.environ["CRYPTOGRAPHY_OPENSSL_NO_LEGACY"] = "1"
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from ui.style import setup_theme

# Fix taskbar icon grouping on Windows 10+ (dev mode)
import ctypes
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("shiyun.app")
except Exception:
    pass
from ui.main_window import MainWindow
from core.shutdown_filter import ShutdownFilter, set_main_window

LOG_DIR = Path.home() / ".shiyun"
LOG_FILE = LOG_DIR / "shiyun.log"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 控制台输出
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.DEBUG)
    # 文件输出（5MB 轮转，保留 3 个备份）
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


_setup_logging()
logger = logging.getLogger("shiyun.main")

LOCK_FILE = Path.home() / ".shiyun" / "shiyun.lock"


def _check_single_instance():
    """Return True if another instance is already running."""
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            if sys.platform == "win32":
                import ctypes
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, old_pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    return True
            else:
                os.kill(old_pid, 0)
            return True
        except (ValueError, OSError, ProcessLookupError):
            pass
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    return False


def _remove_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def main():
    if _check_single_instance():
        logger.info("拾云已在运行，退出本次启动")
        return

    app = QApplication(sys.argv)

    # Set app icon (works for taskbar, title bar, etc.)
    if getattr(sys, 'frozen', False):
        icon_path = os.path.join(sys._MEIPASS, "icon.ico")
    else:
        icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    setup_theme(app)

    from core.settings_manager import SettingsManager
    SettingsManager.instance()

    shutdown_filter = ShutdownFilter()
    app.installNativeEventFilter(shutdown_filter)

    startup_mode = "--startup" in sys.argv

    if startup_mode:
        from core.config import has_backup_today
        mgr = SettingsManager.instance()
        if not mgr.get("startup_backup_reminder", True):
            logger.info("启动模式：启动时备份提醒已关闭，自动退出")
            _remove_lock()
            return
        if not has_backup_today():
            logger.info("启动模式：今天没有备份任务，自动退出")
            _remove_lock()
            return
        logger.info("启动模式：今天有备份任务，保持后台运行")

    window = MainWindow(startup_mode=startup_mode)
    set_main_window(window)
    window.show()

    exit_code = app.exec()
    _remove_lock()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
