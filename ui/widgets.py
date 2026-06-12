from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QMenu
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QPaintEvent, QMouseEvent
from ui.style import COLORS, menu_stylesheet


class StatusDot(QWidget):
    def __init__(self, color: str = "#A0B0B0", size: int = 8, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, self.width(), self.height())
        painter.end()


class ConnectionCard(QWidget):
    clicked = Signal()
    edit_requested = Signal()
    delete_requested = Signal()

    def __init__(self, conn: dict, is_active: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.conn = conn
        self.setObjectName("connCard")
        self.setProperty("active", is_active)
        self.setFixedHeight(56)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        dot_color = COLORS['mint'] if is_active else COLORS['text_hint']
        self.dot = StatusDot(dot_color, 8)
        layout.addWidget(self.dot)

        text_col = QWidget()
        text_layout = QVBoxLayout(text_col)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(4)

        self.name_label = QLabel(conn.get("name", "未命名"))
        self.name_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        top_row.addWidget(self.name_label)

        self.test_tag = QLabel()
        self.test_tag.setStyleSheet(
            f"font-size: 10px; color: {COLORS['mint']}; background: {COLORS['mint_light']}; "
            f"border-radius: 3px; padding: 2px 6px; font-weight: bold;"
        )
        self.test_tag.setVisible(False)
        top_row.addWidget(self.test_tag)
        top_row.addStretch()

        text_layout.addLayout(top_row)

        self.host_label = QLabel(f"{conn.get('host', '')}:{conn.get('port', 22)}")
        self.host_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_sec']};")
        text_layout.addWidget(self.host_label)

        layout.addWidget(text_col, 1)

    def set_test_status(self, ok: bool, text: str = "") -> None:
        self.test_tag.setText(text)
        if ok:
            self.test_tag.setStyleSheet(
                f"font-size: 10px; color: {COLORS['mint']}; background: {COLORS['mint_light']}; "
                f"border-radius: 3px; padding: 2px 6px; font-weight: bold;"
            )
        else:
            self.test_tag.setStyleSheet(
                f"font-size: 10px; color: {COLORS['danger']}; background: {COLORS['danger_bg']}; "
                f"border-radius: 3px; padding: 2px 6px; font-weight: bold;"
            )
        self.test_tag.setVisible(True)

    def _show_menu(self, pos: "QPoint") -> None:
        menu = QMenu(self)
        menu.setStyleSheet(menu_stylesheet())
        edit_action = menu.addAction("编辑")
        delete_action = menu.addAction("删除")
        action = menu.exec(self.mapToGlobal(pos))
        if action == edit_action:
            self.edit_requested.emit()
        elif action == delete_action:
            self.delete_requested.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class FileRow(QWidget):
    clicked = Signal()
    right_clicked = Signal(object)

    def __init__(self, name: str, size: str, mtime: str, is_dir: bool = False, is_parent: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.file_name = name
        self.is_dir = is_dir
        self.is_parent = is_parent
        self.setObjectName("fileRow")
        self.setFixedHeight(40)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setCursor(Qt.PointingHandCursor if (is_dir or is_parent) else Qt.ArrowCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(0)

        self.name_label = QLabel(name)
        self.name_label.setStyleSheet("font-size: 12px;")
        layout.addWidget(self.name_label, 1)

        self.size_label = QLabel(size)
        self.size_label.setFixedWidth(100)
        self.size_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_sec']};")
        layout.addWidget(self.size_label)

        self.time_label = QLabel(mtime)
        self.time_label.setFixedWidth(140)
        self.time_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']};")
        layout.addWidget(self.time_label)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(event.globalPosition().toPoint())
        super().mousePressEvent(event)


class WelcomeIcon(QWidget):
    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QColor(COLORS['mint_light']))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(10, 10, 100, 100)

        painter.setBrush(QColor(COLORS['mint']))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(30, 45, 60, 40)
        painter.drawEllipse(20, 50, 30, 25)
        painter.drawEllipse(55, 50, 35, 28)

        painter.setPen(QPen(QColor("white"), 3))
        painter.drawLine(60, 40, 60, 65)
        painter.drawLine(48, 50, 60, 38)
        painter.drawLine(72, 50, 60, 38)

        painter.end()


class ToggleSwitch(QWidget):
    """Custom toggle switch widget."""

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        if self._checked != checked:
            self._checked = checked
            self.toggled.emit(checked)
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Groove
        groove_color = QColor(COLORS['mint']) if self._checked else QColor(COLORS['border'])
        painter.setPen(Qt.NoPen)
        painter.setBrush(groove_color)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        # Handle
        handle_color = QColor("white")
        painter.setBrush(handle_color)
        border_color = QColor(COLORS['mint']) if self._checked else QColor(COLORS['border'])
        painter.setPen(QPen(border_color, 1))
        if self._checked:
            hx = self.width() - 22
        else:
            hx = 2
        painter.drawEllipse(hx, 2, 20, 20)
        painter.end()
