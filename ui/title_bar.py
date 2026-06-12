from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from ui.style import COLORS


class TitleBar(QWidget):
    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setObjectName("titleBar")
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(0)

        icon_label = QLabel("☁")
        icon_label.setStyleSheet(f"font-size: 15px; color: {COLORS['mint']}; margin-right: 6px;")
        layout.addWidget(icon_label)

        title = QLabel("拾云")
        title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLORS['text']};")
        layout.addWidget(title)

        layout.addStretch()

        self.min_btn = QPushButton("─")
        self.min_btn.setObjectName("minBtn")
        self.min_btn.setFixedSize(36, 36)
        self.min_btn.clicked.connect(self.minimize_clicked)
        layout.addWidget(self.min_btn)

        self.max_btn = QPushButton("□")
        self.max_btn.setObjectName("maxBtn")
        self.max_btn.setFixedSize(36, 36)
        self.max_btn.clicked.connect(self._on_maximize)
        layout.addWidget(self.max_btn)

        self.close_btn = QPushButton("×")
        self.close_btn.setObjectName("closeTitleBarBtn")
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.clicked.connect(self.close_clicked)
        layout.addWidget(self.close_btn)

    def _on_maximize(self) -> None:
        self.maximize_clicked.emit()
        if self.window().isMaximized():
            self.max_btn.setText("□")
        else:
            self.max_btn.setText("❐")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None:
            if self.window().isMaximized():
                self.window().showNormal()
                self.max_btn.setText("□")
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._on_maximize()
        event.accept()


class DialogTitleBar(QWidget):
    close_clicked = Signal()

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setObjectName("titleBar")
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 4, 0)

        if title:
            lbl = QLabel(title)
            lbl.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLORS['text']};")
            layout.addWidget(lbl)

        layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setObjectName("closeTitleBarBtn")
        close_btn.setFixedSize(36, 36)
        close_btn.clicked.connect(self.close_clicked)
        layout.addWidget(close_btn)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.window().pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None:
            self.window().move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(event)
