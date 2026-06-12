from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QTextEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QPaintEvent, QKeyEvent
from ui.style import COLORS, make_confirm_button, make_cancel_button, make_danger_button
from ui.title_bar import DialogTitleBar


def _draw_error_icon(size: int = 40) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    # Red circle
    painter.setBrush(QColor(COLORS['danger']))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    # White X
    painter.setPen(QPen(QColor("white"), 3))
    m = size // 4
    painter.drawLine(m, m, size - m, size - m)
    painter.drawLine(size - m, m, m, size - m)
    painter.end()
    return pixmap


class ErrorDialog(QDialog):
    """
    WinSCP-style error dialog with Abort/Retry/Skip/Skip All options.

    Usage:
        dialog = ErrorDialog(parent, title="下载失败",
            message="无法写入文件",
            details="C:\\Users\\file.jar\n系统错误 代码: 32\n另一个程序正在使用此文件",
            file_path="file.jar")
        result = dialog.exec()
        # result: "abort" | "retry" | "skip" | "skip_all"
    """

    RESULT_ABORT = "abort"
    RESULT_RETRY = "retry"
    RESULT_SKIP = "skip"
    RESULT_SKIP_ALL = "skip_all"

    def __init__(self, parent: QWidget | None = None, title: str = "错误", message: str = "", details: str = "",
                 file_path: str = "", show_skip_all: bool = True) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)
        self.result_action = self.RESULT_ABORT
        self._show_skip_all = show_skip_all

        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title_bar = DialogTitleBar(title)
        title_bar.close_clicked.connect(lambda: self._on_action(self.RESULT_ABORT))
        root.addWidget(title_bar)

        content = QWidget()
        content.setObjectName("connDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        # Icon + message row
        msg_layout = QHBoxLayout()
        msg_layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(_draw_error_icon(40))
        icon_label.setFixedSize(40, 40)
        msg_layout.addWidget(icon_label, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(6)

        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLORS['text']};")
        text_col.addWidget(msg_label)

        if file_path:
            path_label = QLabel(file_path)
            path_label.setWordWrap(True)
            path_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_sec']};")
            text_col.addWidget(path_label)

        msg_layout.addLayout(text_col, 1)
        layout.addLayout(msg_layout)

        # Details (collapsible)
        if details:
            self.details_edit = QTextEdit()
            self.details_edit.setReadOnly(True)
            self.details_edit.setMaximumHeight(80)
            self.details_edit.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {COLORS['sidebar_bg']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                    padding: 6px 8px;
                    font-size: 11px;
                    color: {COLORS['text_sec']};
                    font-family: Consolas, monospace;
                }}
            """)
            self.details_edit.setPlainText(details)
            layout.addWidget(self.details_edit)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        abort_btn = make_danger_button("中止(A)")
        abort_btn.setFixedHeight(30)
        abort_btn.clicked.connect(lambda: self._on_action(self.RESULT_ABORT))
        abort_btn.setShortcut("A")
        btn_layout.addWidget(abort_btn)

        retry_btn = make_confirm_button("重试(R)")
        retry_btn.setFixedHeight(30)
        retry_btn.clicked.connect(lambda: self._on_action(self.RESULT_RETRY))
        retry_btn.setShortcut("R")
        btn_layout.addWidget(retry_btn)

        skip_btn = make_cancel_button("跳过(S)")
        skip_btn.setFixedHeight(30)
        skip_btn.clicked.connect(lambda: self._on_action(self.RESULT_SKIP))
        skip_btn.setShortcut("S")
        btn_layout.addWidget(skip_btn)

        if show_skip_all:
            skip_all_btn = make_cancel_button("全部跳过(P)")
            skip_all_btn.setFixedHeight(30)
            skip_all_btn.clicked.connect(lambda: self._on_action(self.RESULT_SKIP_ALL))
            skip_all_btn.setShortcut("P")
            btn_layout.addWidget(skip_all_btn)

        layout.addLayout(btn_layout)
        root.addWidget(content, 1)

    def _on_action(self, action: str) -> None:
        self.result_action = action
        self.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(COLORS['danger']), 3))
        painter.setBrush(QColor(COLORS['bg']))
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self._on_action(self.RESULT_ABORT)
        else:
            super().keyPressEvent(event)


def show_error(parent: QWidget, title: str = "错误", message: str = "", details: str = "",
               file_path: str = "", show_skip_all: bool = True) -> str:
    """
    Show error dialog and return user action.
    Returns: "abort" | "retry" | "skip" | "skip_all"
    """
    dialog = ErrorDialog(parent, title=title, message=message,
                         details=details, file_path=file_path,
                         show_skip_all=show_skip_all)
    dialog.exec()
    return dialog.result_action
