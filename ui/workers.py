import threading
from typing import Any, Callable
from PySide6.QtCore import QThread, Signal


class SFTPWorker(QThread):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)
    # Signal: (error_message, file_path) — emitted when download fails, needs user decision
    error_ask = Signal(str, str)

    def __init__(self, sftp_client: Any, operation: Callable, *args: Any, progress_callback: bool = False, **kwargs: Any) -> None:
        super().__init__()
        self.sftp = sftp_client
        self.operation = operation
        self.args = args
        self.kwargs = kwargs
        self._progress_callback = progress_callback
        self._cancelled = threading.Event()
        self._error_decision = None
        self._error_event = threading.Event()

    def cancel(self) -> None:
        """Cancel the operation. Aborts SFTP transport to interrupt blocking calls."""
        # Set flag FIRST to prevent abort-induced errors from being treated as real errors
        self._cancelled.set()
        try:
            self.sftp.abort()
        except Exception:
            pass

    def set_error_decision(self, decision: str) -> None:
        """Called from main thread after user chooses an action in error dialog."""
        self._error_decision = decision
        self._error_event.set()

    def ask_user_decision(self, error_msg: str, file_path: str) -> str:
        """Called from worker thread. Emits signal and waits for main thread response."""
        self._error_event.clear()
        self._error_decision = None
        self.error_ask.emit(str(error_msg), file_path)
        self._error_event.wait()
        return self._error_decision or "abort"

    def run(self) -> None:
        try:
            if self._progress_callback:
                def _cb(transferred: int, total: int) -> None:
                    if self._cancelled.is_set():
                        raise ConnectionError("用户取消")
                    self.progress.emit(transferred, total)
                self.kwargs["progress_callback"] = _cb
            result = self.operation(*self.args, **self.kwargs)
            if not self._cancelled.is_set():
                self.finished.emit(result)
        except Exception as e:
            if not self._cancelled.is_set():
                self.error.emit(str(e))
