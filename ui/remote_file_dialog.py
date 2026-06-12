import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QWidget, QAbstractItemView,
    QStyledItemDelegate, QStyle
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen
from ui.style import COLORS
from ui.title_bar import DialogTitleBar


class _ExplorerTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._click_selected_rows = set()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            index = self.indexAt(event.pos())
            if index.isValid():
                row = index.row()
                modifiers = event.modifiers()
                selected_rows = set(idx.row() for idx in self.selectionModel().selectedRows())

                if modifiers & Qt.ControlModifier:
                    super().mousePressEvent(event)
                elif modifiers & Qt.ShiftModifier:
                    super().mousePressEvent(event)
                else:
                    if row in selected_rows:
                        self.selectionModel().clear()
                        self._click_selected_rows = set()
                    else:
                        super().mousePressEvent(event)
            else:
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)


class _FocusDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if option.state & QStyle.State_HasFocus:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor(COLORS['mint']), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
            painter.restore()


class RemoteFileDialog(QDialog):
    def __init__(self, sftp_client, parent=None, start_path="/",
                 select_mode="multi", file_filter=None):
        super().__init__(parent)
        self.sftp = sftp_client
        self._current_path = start_path
        self._history = []
        self._forward = []
        self._select_mode = select_mode
        self._file_filter = file_filter
        self.result_paths = []
        self._rows = []
        self._nav_lock = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(640, 480)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()
        self._navigate(start_path)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title = "选择远程文件" if self._select_mode == "multi" else "选择远程路径"
        title_bar = DialogTitleBar(title)
        title_bar.close_clicked.connect(self.reject)
        root.addWidget(title_bar)

        content = QWidget()
        content.setObjectName("connDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        nav = QHBoxLayout()
        nav.setSpacing(4)

        btn_style = (
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
            f"border-radius: 3px; font-size: 14px; color: {COLORS['text']}; min-width: 24px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; }}"
            f"QPushButton:disabled {{ color: {COLORS['text_hint']}; border-color: {COLORS['border']}; }}"
        )

        self.back_btn = QPushButton("←")
        self.back_btn.setFixedSize(28, 28)
        self.back_btn.setStyleSheet(btn_style)
        self.back_btn.clicked.connect(self._go_back)
        self.back_btn.setEnabled(False)
        nav.addWidget(self.back_btn)

        self.up_btn = QPushButton("↑")
        self.up_btn.setFixedSize(28, 28)
        self.up_btn.setStyleSheet(btn_style)
        self.up_btn.clicked.connect(self._go_up)
        nav.addWidget(self.up_btn)

        self.path_edit = QLineEdit()
        self.path_edit.setFixedHeight(28)
        self.path_edit.setStyleSheet(
            f"border: 1px solid {COLORS['border']}; border-radius: 3px; padding: 2px 8px; font-size: 12px;"
        )
        self.path_edit.returnPressed.connect(self._on_path_enter)
        nav.addWidget(self.path_edit, 1)

        layout.addLayout(nav)

        self.table = _ExplorerTable()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["名称", "大小", "修改日期"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 140)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setItemDelegate(_FocusDelegate(self.table))

        header = self.table.horizontalHeader()
        header.setStyleSheet(f"""
            QHeaderView::section {{
                background-color: {COLORS['sidebar_bg']};
                border: none;
                border-bottom: 1px solid {COLORS['border']};
                padding: 6px 8px;
                font-size: 12px;
                font-weight: bold;
                color: {COLORS['text_sec']};
            }}
        """)

        self.table.setStyleSheet(f"""
            QTableWidget {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                background: {COLORS['bg']};
                outline: none;
            }}
            QTableWidget::item {{
                padding: 0px 8px;
                border-bottom: 1px solid {COLORS['border']};
            }}
            QTableWidget::item:selected {{
                background-color: {COLORS['mint_light']};
                color: {COLORS['text']};
            }}
            QTableWidget::item:hover:!selected {{
                background-color: {COLORS['card_hover']};
            }}
        """)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_double_click)

        layout.addWidget(self.table, 1)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']};")
        layout.addWidget(self.status_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.addStretch()

        from ui.style import make_cancel_button, make_confirm_button
        cancel_btn = make_cancel_button("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        if self._select_mode == "multi":
            self.confirm_btn = make_confirm_button("选择 (0)")
            self.confirm_btn.setMinimumWidth(100)
            self.confirm_btn.clicked.connect(self._on_confirm)
            btn_layout.addWidget(self.confirm_btn)

        layout.addLayout(btn_layout)
        root.addWidget(content, 1)

    def _navigate(self, path):
        self._nav_lock = True
        self.table.setRowCount(0)
        self._rows = []

        path = path.rstrip("/") or "/"

        try:
            entries = self.sftp.list_dir(path)
        except Exception as e:
            self.status_label.setText(f"无法访问: {e}")
            self._nav_lock = False
            return

        if self._file_filter == "file":
            entries = [e for e in entries if not e.is_dir]
        elif self._file_filter == "dir":
            entries = [e for e in entries if e.is_dir]

        if path != "/":
            parent = "/".join(path.split("/")[:-1]) or "/"
            self._rows.append({
                "name": "..",
                "is_dir": True,
                "size": "",
                "mtime": "",
                "path": parent,
            })

        for entry in entries:
            if entry.name in (".", ".."):
                continue
            full_path = f"{path}/{entry.name}"
            size_str = self._format_size(entry.size) if not entry.is_dir else ""
            mtime_str = self._format_time(entry.mtime) if entry.mtime else ""
            self._rows.append({
                "name": entry.name,
                "is_dir": entry.is_dir,
                "size": size_str,
                "mtime": mtime_str,
                "path": full_path,
            })

        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            icon = "📁" if row["is_dir"] else "📄"
            name_item = QTableWidgetItem(f"{icon}  {row['name']}")
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, name_item)

            size_item = QTableWidgetItem(row["size"])
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setForeground(QColor(COLORS['text_sec']))
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, size_item)

            mtime_item = QTableWidgetItem(row["mtime"])
            mtime_item.setForeground(QColor(COLORS['text_hint']))
            mtime_item.setFlags(mtime_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, mtime_item)

        self._current_path = path
        self.path_edit.setText(path)
        self.back_btn.setEnabled(len(self._history) > 0)
        item_count = len(self._rows) - (1 if path != "/" else 0)
        self.status_label.setText(f"{path}  |  {item_count} 个项目")
        self._nav_lock = False

    def _go_back(self):
        if self._history:
            prev = self._history.pop()
            self._forward.append(self._current_path)
            self._navigate(prev)

    def _go_up(self):
        if self._current_path == "/":
            return
        parent = "/".join(self._current_path.split("/")[:-1]) or "/"
        self._history.append(self._current_path)
        self._forward.clear()
        self._navigate(parent)

    def _on_path_enter(self):
        path = self.path_edit.text().strip()
        if path and path != self._current_path:
            self._history.append(self._current_path)
            self._forward.clear()
            self._navigate(path)

    def _on_double_click(self, item):
        row = item.row()
        if row < 0 or row >= len(self._rows):
            return
        r = self._rows[row]
        if r["is_dir"]:
            if r["name"] == "..":
                self._go_up()
            else:
                self._history.append(self._current_path)
                self._forward.clear()
                self._navigate(r["path"])
        elif self._select_mode == "single":
            self.result_paths = [r["path"]]
            self.accept()

    def _on_selection_changed(self):
        if self._nav_lock:
            return
        if self._select_mode == "multi":
            selected = self.table.selectionModel().selectedRows()
            count = len(selected)
            self.confirm_btn.setText(f"选择 ({count})")
            if count > 0:
                self.status_label.setText(f"已选择 {count} 个项目")
            else:
                item_count = len(self._rows) - (1 if self._current_path != "/" else 0)
                self.status_label.setText(f"{self._current_path}  |  {item_count} 个项目")

    def _on_confirm(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        self.result_paths = [self._rows[idx.row()]["path"] for idx in selected]
        self.accept()

    @staticmethod
    def _format_size(size):
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}" if size < 1000 else f"{size:.0f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @staticmethod
    def _format_time(timestamp):
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor(COLORS['mint']), 3))
        painter.setBrush(QColor(COLORS['bg']))
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
        painter.end()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            focused = self.focusWidget()
            if focused == self.path_edit:
                self._on_path_enter()
                return
            return
        else:
            super().keyPressEvent(event)
