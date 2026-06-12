from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QPaintEvent, QKeyEvent
from ui.style import COLORS, make_confirm_button, make_cancel_button
from ui.title_bar import DialogTitleBar


class RenameDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, title: str = "重命名", current_name: str = "") -> None:
        super().__init__(parent)
        self.result_name = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(360, 180)
        self.setWindowModality(Qt.ApplicationModal)

        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title_bar = DialogTitleBar(title)
        title_bar.close_clicked.connect(self.reject)
        root.addWidget(title_bar)

        content = QWidget()
        content.setObjectName("connDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        field_label = QLabel("新名称")
        field_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']};")
        layout.addWidget(field_label)

        self.name_edit = QLineEdit()
        self.name_edit.setText(current_name)
        self.name_edit.selectAll()
        self.name_edit.setFixedHeight(32)
        layout.addWidget(self.name_edit)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = make_cancel_button("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = make_confirm_button("确定")
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        root.addWidget(content, 1)

        self.name_edit.returnPressed.connect(self._on_ok)
        self.name_edit.setFocus()

    def _on_ok(self) -> None:
        name = self.name_edit.text().strip()
        if name:
            self.result_name = name
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
        else:
            super().keyPressEvent(event)
