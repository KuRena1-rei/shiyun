from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPen, QPaintEvent, QKeyEvent
from ui.style import COLORS, make_confirm_button, make_cancel_button
from ui.title_bar import DialogTitleBar


def _draw_icon(icon_type: str, size: int = 32) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    if icon_type == "error":
        painter.setBrush(QColor(COLORS['danger']))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)
        painter.setPen(QColor("white"))
        font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "×")
    elif icon_type == "warning":
        painter.setBrush(QColor(COLORS['warning']))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)
        painter.setPen(QColor("white"))
        font = QFont("Arial", 18, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "!")
    elif icon_type == "info":
        painter.setBrush(QColor(COLORS['mint']))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)
        painter.setPen(QColor("white"))
        font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "i")
    elif icon_type == "question":
        painter.setBrush(QColor(COLORS['question']))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)
        painter.setPen(QColor("white"))
        font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "?")

    painter.end()
    return pixmap


class MessageDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, message: str, icon_type: str = "info", buttons: list[str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(340)
        self.setMaximumWidth(460)
        self.result = None

        if buttons is None:
            buttons = ["确定"]

        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title_bar = DialogTitleBar()
        title_bar.close_clicked.connect(self.reject)
        root.addWidget(title_bar)

        content = QWidget()
        content.setObjectName("connDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        msg_layout = QHBoxLayout()
        msg_layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(_draw_icon(icon_type, 32))
        icon_label.setFixedSize(32, 32)
        msg_layout.addWidget(icon_label, 0, Qt.AlignTop)

        msg_text = QLabel(message)
        msg_text.setWordWrap(True)
        msg_text.setStyleSheet(f"font-size: 13px; color: {COLORS['text']};")
        msg_layout.addWidget(msg_text, 1)

        layout.addLayout(msg_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        for btn_text in buttons:
            if btn_text in ("是", "确定", "登录"):
                btn = make_confirm_button(btn_text)
            else:
                btn = make_cancel_button(btn_text)
            btn.clicked.connect(lambda checked, t=btn_text: self._on_button(t))
            btn_layout.addWidget(btn)

        layout.addLayout(btn_layout)
        root.addWidget(content, 1)

        self._buttons = buttons

    def _on_button(self, text: str) -> None:
        self.result = text
        self.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(COLORS['mint']), 3))
        painter.setBrush(QColor(COLORS['bg']))
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
        painter.end()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            for btn in self.findChildren(QPushButton):
                if btn.text() in ("确定", "是", "登录"):
                    btn.click()
                    return
            self.accept()
        else:
            super().keyPressEvent(event)


def show_message(parent: QWidget, title: str, message: str, icon_type: str = "info", buttons: list[str] | None = None) -> str | None:
    dialog = MessageDialog(parent, title, message, icon_type, buttons)
    dialog.exec()
    return dialog.result


def ask_question(parent: QWidget, title: str, message: str) -> bool:
    result = show_message(parent, title, message, "question", ["是", "否"])
    return result == "是"
