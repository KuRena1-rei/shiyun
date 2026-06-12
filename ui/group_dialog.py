from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QWidget, QCheckBox,
    QFrame, QScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QPaintEvent, QKeyEvent
from ui.style import COLORS, make_confirm_button, make_cancel_button
from ui.title_bar import DialogTitleBar
from ui.message_dialog import show_message


class GroupDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, group: dict | None = None) -> None:
        super().__init__(parent)
        self.group = group
        self.result_data = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(480)
        self.setMinimumHeight(500)
        self.setMaximumHeight(700)
        self.setWindowModality(Qt.ApplicationModal)
        self._build_ui()
        self._load_data()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title_text = "编辑备份组" if self.group else "新建备份组"
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

        lbl = QLabel("组名称")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        layout.addWidget(lbl)
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText("给备份组起个名字")
        self.name_entry.setFixedHeight(32)
        layout.addWidget(self.name_entry)
        layout.addSpacing(12)

        # === 备份模板选择 ===
        backup_lbl = QLabel("选择备份模板")
        backup_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        layout.addWidget(backup_lbl)

        self._checkboxes: dict[int, QCheckBox] = {}
        self._backup_hint = None
        self._build_backup_list()

        layout.addSpacing(4)
        hint_lbl = QLabel("不同服务器的模板可以选入同一组，执行时会自动连接对应服务器")
        hint_lbl.setStyleSheet(f"font-size: 10px; color: {COLORS['text_hint']}; font-style: italic;")
        hint_lbl.setWordWrap(True)
        layout.addWidget(hint_lbl)

        layout.addSpacing(12)

        # === 增量备份 ===
        self.incremental_check = QCheckBox("增量备份（仅下载变化的文件）")
        self.incremental_check.setStyleSheet(f"font-size: 12px; color: {COLORS['text']};")
        layout.addWidget(self.incremental_check)
        layout.addSpacing(8)

        # === 定时设置 ===
        self.schedule_check = QCheckBox("启用定时备份")
        self.schedule_check.setStyleSheet(f"font-size: 12px; color: {COLORS['text']};")
        layout.addWidget(self.schedule_check)

        from ui.schedule_picker import SchedulePicker
        self.schedule_picker = SchedulePicker()
        self.schedule_picker.setVisible(False)
        layout.addWidget(self.schedule_picker)

        self.schedule_check.toggled.connect(self.schedule_picker.setVisible)

        layout.addSpacing(8)

        self.shutdown_check = QCheckBox("备份成功后自动关机")
        self.shutdown_check.setStyleSheet(f"font-size: 12px; color: {COLORS['text']};")
        self.shutdown_check.setEnabled(False)
        self.schedule_check.toggled.connect(self.shutdown_check.setEnabled)
        layout.addWidget(self.shutdown_check)

        layout.addSpacing(8)

        hint_lbl = QLabel("组内模板将使用此处的定时和增量设置，覆盖模板自身的设置")
        hint_lbl.setStyleSheet(f"font-size: 10px; color: {COLORS['text_hint']}; font-style: italic;")
        hint_lbl.setWordWrap(True)
        layout.addWidget(hint_lbl)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = make_cancel_button("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = make_confirm_button("保存")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

    def _build_backup_list(self) -> None:
        """Build the backup template checkbox list."""
        from core.config import load_backups
        backups = load_backups()
        if backups:
            for b in backups:
                cb = QCheckBox(b.get("name", "未命名"))
                cb.setStyleSheet(f"font-size: 12px; color: {COLORS['text']};")
                cb._backup_id = b.get("id")
                self._checkboxes[b.get("id")] = cb
                self.name_entry.parentWidget().layout().addWidget(cb)
        else:
            self._backup_hint = QLabel("暂无备份模板，请先在侧边栏创建")
            self._backup_hint.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']};")
            self.name_entry.parentWidget().layout().addWidget(self._backup_hint)

    def _load_data(self) -> None:
        if not self.group:
            return
        self.name_entry.setText(self.group.get("name", ""))
        self.shutdown_check.setChecked(self.group.get("auto_shutdown", False))
        self.incremental_check.setChecked(self.group.get("incremental", False))

        schedule_enabled = self.group.get("schedule_enabled", False)
        self.schedule_check.setChecked(schedule_enabled)

        backup_ids = self.group.get("backup_ids", [])
        for bid in backup_ids:
            if bid in self._checkboxes:
                self._checkboxes[bid].setChecked(True)

        schedule_rule = self.group.get("schedule_rule")
        if schedule_rule:
            self.schedule_picker.set_schedule(self.group)
        else:
            time_str = self.group.get("schedule_time", "01:00")
            h, m = time_str.split(":")
            from PySide6.QtCore import QTime
            self.schedule_picker.time_edit.setTime(QTime(int(h), int(m)))

    def _on_save(self) -> None:
        name = self.name_entry.text().strip()
        if not name:
            show_message(self, "提示", "请填写组名称", "warning")
            return

        selected_ids = [bid for bid, cb in self._checkboxes.items() if cb.isChecked()]
        if not selected_ids:
            show_message(self, "提示", "请至少选择一个备份模板", "warning")
            return

        schedule_enabled = self.schedule_check.isChecked()
        schedule_data = self.schedule_picker.get_schedule() if schedule_enabled else {}

        self.result_data = {
            "name": name,
            "backup_ids": selected_ids,
            "incremental": self.incremental_check.isChecked(),
            "schedule_enabled": schedule_enabled,
            "schedule_rule": schedule_data.get("schedule_rule"),
            "next_run": schedule_data.get("next_run"),
            "schedule_time": schedule_data.get("schedule_time", "01:00"),
            "auto_shutdown": self.shutdown_check.isChecked() if schedule_enabled else False,
        }
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
            focused = self.focusWidget()
            if isinstance(focused, QLineEdit):
                focused.clearFocus()
                return
            return
        else:
            super().keyPressEvent(event)
