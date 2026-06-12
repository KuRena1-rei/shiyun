from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QWidget, QFileDialog,
    QCheckBox, QFrame, QComboBox, QScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QPaintEvent, QKeyEvent
from ui.style import COLORS
from ui.title_bar import DialogTitleBar
from ui.message_dialog import show_message


class BackupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, backup: dict | None = None, sftp_client: object | None = None) -> None:
        super().__init__(parent)
        self.backup = backup
        self.sftp = sftp_client
        self.result_data = None
        self._remote_paths = []
        # Save original connection state for restore on close
        self._original_conn_id = None
        self._switched_conn = False
        if parent and hasattr(parent, 'conn_manager'):
            self._original_conn_id = parent.conn_manager.current_conn_id
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(520)
        self.setMinimumHeight(400)
        self.setMaximumHeight(600)
        self.setWindowModality(Qt.ApplicationModal)
        self._building = True
        self._build_ui()
        self._building = False
        # Set initial browse button state based on current selection
        self._on_conn_changed(self.conn_combo.currentIndex())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title_text = "编辑备份模板" if self.backup else "新建备份模板"
        title_bar = DialogTitleBar(title_text)
        title_bar.close_clicked.connect(self.reject)
        root.addWidget(title_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ width: 6px; background: transparent; }}"
            f"QScrollBar::handle:vertical {{ background: {COLORS['border']}; border-radius: 3px; min-height: 30px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {COLORS['text_hint']}; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )

        content = QWidget()
        content.setObjectName("connDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(0)

        lbl = QLabel("模板名称")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        layout.addWidget(lbl)
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText("给备份模板起个名字")
        self.name_entry.setFixedHeight(32)
        layout.addWidget(self.name_entry)
        layout.addSpacing(12)

        lbl = QLabel("关联服务器")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        layout.addWidget(lbl)

        self.conn_combo = QComboBox()
        self.conn_combo.setFixedHeight(32)
        self.conn_combo.setStyleSheet(
            f"QComboBox {{ border: 1px solid {COLORS['border']}; border-radius: 6px; padding: 4px 10px; font-size: 12px; }}"
            f"QComboBox:hover {{ border-color: {COLORS['mint']}; }}"
        )
        self._load_connections()
        self.conn_combo.currentIndexChanged.connect(self._on_conn_changed)
        layout.addWidget(self.conn_combo)
        layout.addSpacing(12)

        lbl = QLabel("远程备份项目")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        layout.addWidget(lbl)

        self.remote_paths_container = QWidget()
        self.remote_paths_layout = QVBoxLayout(self.remote_paths_container)
        self.remote_paths_layout.setContentsMargins(0, 0, 0, 0)
        self.remote_paths_layout.setSpacing(4)
        layout.addWidget(self.remote_paths_container)

        self.add_remote_btn = QPushButton("+ 浏览添加")
        self.add_remote_btn.setStyleSheet(
            f"QPushButton {{ border: 1px dashed {COLORS['border']}; background: transparent; "
            f"color: {COLORS['text_sec']}; border-radius: 4px; padding: 6px; font-size: 12px; }}"
            f"QPushButton:hover {{ border-color: {COLORS['mint']}; color: {COLORS['mint']}; }}"
        )
        self.add_remote_btn.setFixedHeight(32)
        self.add_remote_btn.clicked.connect(self._browse_remote)
        self.add_remote_btn.setEnabled(False)
        layout.addWidget(self.add_remote_btn)

        self.clear_all_btn = QPushButton("全部清除")
        self.clear_all_btn.setFixedHeight(28)
        self.clear_all_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
            f"color: {COLORS['text_hint']}; border-radius: 4px; font-size: 11px; }}"
            f"QPushButton:hover {{ color: {COLORS['danger']}; border-color: {COLORS['danger']}; }}"
        )
        self.clear_all_btn.clicked.connect(self._clear_all_remote_paths)
        self.clear_all_btn.setVisible(False)
        layout.addWidget(self.clear_all_btn)
        layout.addSpacing(12)

        lbl = QLabel("本地保存路径")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        layout.addWidget(lbl)

        local_row = QHBoxLayout()
        local_row.setSpacing(8)
        self.local_entry = QLineEdit()
        self.local_entry.setPlaceholderText("例: D:\\backup\\data")
        self.local_entry.setFixedHeight(32)
        local_row.addWidget(self.local_entry, 1)

        local_browse_btn = QPushButton("选择")
        local_browse_btn.setFixedSize(60, 32)
        local_browse_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; color: {COLORS['text']}; border-radius: 4px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; }}"
        )
        local_browse_btn.clicked.connect(self._browse_local)
        local_row.addWidget(local_browse_btn)

        layout.addLayout(local_row)
        layout.addSpacing(12)

        # === 定时备份 ===
        schedule_lbl = QLabel("定时备份")
        schedule_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        layout.addWidget(schedule_lbl)

        self.schedule_check = QCheckBox("启用定时备份")
        self.schedule_check.setStyleSheet(f"font-size: 12px; color: {COLORS['text']};")
        layout.addWidget(self.schedule_check)

        from ui.schedule_picker import SchedulePicker
        self.schedule_picker = SchedulePicker()
        self.schedule_picker.setVisible(False)
        layout.addWidget(self.schedule_picker)

        self.schedule_check.toggled.connect(self.schedule_picker.setVisible)
        self.schedule_check.toggled.connect(lambda _: self.adjustSize())

        layout.addSpacing(8)

        self.shutdown_check = QCheckBox("备份成功后自动关机")
        self.shutdown_check.setStyleSheet(f"font-size: 12px; color: {COLORS['text']};")
        self.shutdown_check.setEnabled(False)
        layout.addWidget(self.shutdown_check)

        self.schedule_check.toggled.connect(self.shutdown_check.setEnabled)

        layout.addSpacing(8)

        self.incremental_check = QCheckBox("增量备份（仅下载变化的文件）")
        self.incremental_check.setStyleSheet(f"font-size: 12px; color: {COLORS['text']};")
        layout.addWidget(self.incremental_check)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        from ui.style import make_cancel_button, make_confirm_button
        cancel_btn = make_cancel_button("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = make_confirm_button("保存")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        if self.backup:
            self._fill_data()

    def _load_connections(self) -> None:
        from core.config import load_connections
        self._connections = load_connections()
        self.conn_combo.addItem("未关联", None)
        for conn in self._connections:
            self.conn_combo.addItem(f"{conn['name']} ({conn['host']})", conn.get("id"))

    def _on_conn_changed(self, index: int) -> None:
        if self._building:
            return
        conn_id = self.conn_combo.currentData()
        if conn_id is None:
            self.add_remote_btn.setEnabled(False)
            # Clear remote paths when switching to unassociated
            self._clear_remote_paths()
            return
        self.add_remote_btn.setEnabled(True)
        self._switch_to_server(conn_id)

    def _clear_remote_paths(self) -> None:
        """Remove all remote path widgets and clear the path list."""
        while self.remote_paths_layout.count():
            item = self.remote_paths_layout.takeAt(0)
            layout = item.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    w = child.widget()
                    if w:
                        w.deleteLater()
            elif item.widget():
                item.widget().deleteLater()
        self._remote_paths.clear()
        self._update_clear_btn_visibility()

    def _switch_to_server(self, conn_id: str) -> None:
        from core.config import load_connections
        connections = load_connections()
        target = None
        for c in connections:
            if c.get("id") == conn_id:
                target = c
                break
        if not target:
            return
        # Already connected to this server
        if (self.sftp.connected
                and hasattr(self.window(), 'conn_manager')
                and self.window().conn_manager.current_conn_id == conn_id):
            return
        # Connect to the target server
        self.add_remote_btn.setEnabled(False)
        self.setCursor(Qt.WaitCursor)
        try:
            self.sftp.connect(
                host=target["host"], port=target["port"],
                username=target["username"],
                password=target.get("password", "")
            )
            self._switched_conn = True
            if hasattr(self.window(), 'conn_manager'):
                self.window().conn_manager.current_conn_id = conn_id
            self.add_remote_btn.setEnabled(True)
        except Exception as e:
            show_message(self, "连接失败", f"无法连接到服务器:\n{e}", "error")
        finally:
            self.setCursor(Qt.ArrowCursor)

    def _restore_connection(self) -> None:
        if not self._switched_conn:
            return
        window = self.window()
        if not window or not hasattr(window, 'conn_manager'):
            return
        conn_manager = window.conn_manager
        # Restore original connection
        if self._original_conn_id is not None:
            from core.config import load_connections
            connections = load_connections()
            for c in connections:
                if c.get("id") == self._original_conn_id:
                    try:
                        self.sftp.connect(
                            host=c["host"], port=c["port"],
                            username=c["username"],
                            password=c.get("password", "")
                        )
                        conn_manager.current_conn_id = self._original_conn_id
                    except Exception:
                        self.sftp.disconnect()
                        conn_manager.current_conn_id = None
                    break
            else:
                # Original connection no longer exists
                self.sftp.disconnect()
                conn_manager.current_conn_id = None
        else:
            # Was not connected before — disconnect
            self.sftp.disconnect()
            conn_manager.current_conn_id = None
        # Refresh file browser in main window
        if hasattr(window, 'file_manager'):
            if self.sftp.connected:
                window.file_manager.refresh_files()
            else:
                window.content_stack.setCurrentIndex(0)
                conn_manager.refresh_connections()

    def _fill_data(self) -> None:
        self.name_entry.setText(self.backup.get("name", ""))
        self.local_entry.setText(self.backup.get("local_path", ""))
        paths = self.backup.get("remote_paths", [])
        if not paths and self.backup.get("remote_path"):
            paths = [self.backup["remote_path"]]
        for path in paths:
            self._add_remote_path_item(path)

        conn_id = self.backup.get("connection_id")
        if conn_id is not None:
            for i in range(self.conn_combo.count()):
                if self.conn_combo.itemData(i) == conn_id:
                    self.conn_combo.setCurrentIndex(i)
                    break

        self.schedule_check.setChecked(self.backup.get("schedule_enabled", False))
        schedule_rule = self.backup.get("schedule_rule")
        if schedule_rule:
            self.schedule_picker.set_schedule(self.backup)
        else:
            time_str = self.backup.get("schedule_time", "01:00")
            h, m = time_str.split(":")
            from PySide6.QtCore import QTime
            self.schedule_picker.time_edit.setTime(QTime(int(h), int(m)))
        self.shutdown_check.setChecked(self.backup.get("auto_shutdown", False))
        self.incremental_check.setChecked(self.backup.get("incremental", False))

    def _add_remote_path_item(self, path: str) -> None:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        icon = QLabel("📁")
        icon.setStyleSheet("font-size: 12px;")
        icon.setFixedWidth(20)
        row.addWidget(icon)

        lbl = QLabel(path)
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text']}; border: none;")
        lbl.setWordWrap(True)
        row.addWidget(lbl, 1)

        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(26, 26)
        remove_btn.setStyleSheet(
            f"QPushButton {{ border: none; color: {COLORS['text_sec']}; font-size: 14px; font-weight: bold; }}"
            f"QPushButton:hover {{ color: {COLORS['danger']}; background-color: {COLORS['danger_bg']}; border-radius: 4px; }}"
        )
        row.addWidget(remove_btn)

        self.remote_paths_layout.addWidget(container)

        def _remove():
            if path in self._remote_paths:
                self._remote_paths.remove(path)
            self.remote_paths_layout.removeWidget(container)
            container.deleteLater()

        remove_btn.clicked.connect(_remove)
        self._remote_paths.append(path)
        self._update_clear_btn_visibility()

    def _clear_all_remote_paths(self) -> None:
        """Remove all remote paths."""
        self._clear_remote_paths()
        self._update_clear_btn_visibility()

    def _update_clear_btn_visibility(self) -> None:
        """Show/hide the clear-all button based on whether paths exist."""
        self.clear_all_btn.setVisible(len(self._remote_paths) > 0)

    def _rebuild_remote_list(self) -> None:
        while self.remote_paths_layout.count():
            item = self.remote_paths_layout.takeAt(0)
            layout = item.layout()
            if layout:
                while layout.count():
                    child = layout.takeAt(0)
                    w = child.widget()
                    if w:
                        w.deleteLater()
            elif item.widget():
                item.widget().deleteLater()
        self._remote_paths.clear()
        if self.backup:
            paths = self.backup.get("remote_paths", [])
            if not paths and self.backup.get("remote_path"):
                paths = [self.backup["remote_path"]]
            for path in paths:
                self._add_remote_path_item(path)
        self._update_clear_btn_visibility()

    def _browse_remote(self) -> None:
        if not self.sftp or not self.sftp.connected:
            show_message(self, "提示", "请先连接到服务器", "warning")
            return
        from ui.remote_file_dialog import RemoteFileDialog
        dialog = RemoteFileDialog(self.sftp, self, select_mode="multi")
        if dialog.exec() and dialog.result_paths:
            for path in dialog.result_paths:
                if path not in self._remote_paths:
                    self._add_remote_path_item(path)

    def _browse_local(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择本地保存路径")
        if path:
            self.local_entry.setText(path)

    def _on_save(self) -> None:
        name = self.name_entry.text().strip()
        remote_paths = [p for p in self._remote_paths if p.strip()]
        local_path = self.local_entry.text().strip()

        if not name or not remote_paths or not local_path:
            show_message(self, "提示", "请填写模板名称、远程路径和本地路径", "warning")
            return

        schedule_enabled = self.schedule_check.isChecked()
        schedule_data = self.schedule_picker.get_schedule() if schedule_enabled else {}

        self.result_data = {
            "name": name,
            "remote_paths": remote_paths,
            "local_path": local_path,
            "connection_id": self.conn_combo.currentData(),
            "schedule_enabled": schedule_enabled,
            "schedule_rule": schedule_data.get("schedule_rule"),
            "next_run": schedule_data.get("next_run"),
            "schedule_time": schedule_data.get("schedule_time", "01:00"),
            "auto_shutdown": self.shutdown_check.isChecked(),
            "incremental": self.incremental_check.isChecked(),
        }
        self.accept()

    def done(self, result: int) -> None:
        self._restore_connection()
        super().done(result)

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
            focused = self.focusWidget()
            if isinstance(focused, QLineEdit):
                focused.clearFocus()
                return
            return
        else:
            super().keyPressEvent(event)
