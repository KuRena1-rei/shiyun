from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QPaintEvent
from ui.style import COLORS, make_cancel_button, make_confirm_button, make_danger_button
from ui.title_bar import DialogTitleBar


class ProgressDialog(QDialog):
    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None, title: str = "正在处理", message: str = "") -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(400, 180)
        self._cancelled = False
        self._finished = False

        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title_bar = DialogTitleBar(title)
        title_bar.close_clicked.connect(self._on_cancel)
        root.addWidget(title_bar)

        content = QWidget()
        content.setObjectName("connDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)

        self.msg_label = QLabel(message)
        self.msg_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']};")
        self.msg_label.setWordWrap(True)
        layout.addWidget(self.msg_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['mint_light']};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['mint']};
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self.progress_bar)

        self.detail_label = QLabel("0%")
        self.detail_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']};")
        layout.addWidget(self.detail_label)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = make_cancel_button("取消")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        root.addWidget(content, 1)

    def update_progress(self, value: int, total: int = 100, message: str | None = None,
                        file_pct: int | None = None) -> None:
        if self._finished:
            return
        if total > 0:
            pct = int(value / total * 100)
        else:
            pct = 0
        self.progress_bar.setValue(pct)
        if file_pct is not None:
            self.detail_label.setText(f"当前文件: {file_pct}%  |  整体: {value}/{total}")
        else:
            self.detail_label.setText(f"{pct}%  ({value}/{total})")
        if message:
            self.msg_label.setText(message)

    def set_complete(self, message: str = "完成") -> None:
        if self._finished:
            return
        self._finished = True
        self.progress_bar.setValue(100)
        self.detail_label.setText("100%")
        self.msg_label.setText(message)
        self.cancel_btn.setText("关闭")
        self._apply_button_style(self.cancel_btn, 'confirm')
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self.accept)

    def set_error(self, message: str) -> None:
        if self._finished:
            return
        self._finished = True
        self.msg_label.setText(f"错误: {message}")
        self.msg_label.setStyleSheet(f"font-size: 12px; color: {COLORS['danger']};")
        self.cancel_btn.setText("关闭")
        self._apply_button_style(self.cancel_btn, 'danger')
        self.cancel_btn.clicked.disconnect()
        self.cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def _apply_button_style(button: QPushButton, style_type: str) -> None:
        styles = {
            'cancel': (
                f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
                f"color: {COLORS['text']}; border-radius: 4px; }}"
                f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; }}"
            ),
            'confirm': (
                f"QPushButton {{ background-color: {COLORS['mint']}; color: white; border: none; "
                f"border-radius: 4px; font-weight: bold; }}"
                f"QPushButton:hover {{ background-color: {COLORS['mint_dark']}; }}"
            ),
            'danger': (
                f"QPushButton {{ border: 1px solid {COLORS['danger']}; background: transparent; "
                f"color: {COLORS['danger']}; border-radius: 4px; }}"
                f"QPushButton:hover {{ background-color: {COLORS['danger_bg']}; }}"
            ),
        }
        button.setStyleSheet(styles[style_type])

    def _on_cancel(self) -> None:
        self._cancelled = True
        self.cancelled.emit()

    def show_centered(self, parent: QWidget | None) -> None:
        if parent:
            parent_geo = parent.geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
            self.move(x, y)
        self.show()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(COLORS['mint']), 3))
        painter.setBrush(QColor(COLORS['bg']))
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
        painter.end()
