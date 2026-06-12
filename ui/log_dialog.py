from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QPainter, QPen, QCursor, QPaintEvent

from ui.style import COLORS, menu_stylesheet
from ui.message_dialog import show_message, ask_question
from ui.title_bar import DialogTitleBar
from core.config import load_backup_logs, clear_backup_logs


STATUS_COLORS = {
    "success": QColor(COLORS['mint']),
    "partial": QColor(COLORS['warning']),
    "failed": QColor(COLORS['danger']),
}

STATUS_TEXT = {
    "success": "成功",
    "partial": "部分失败",
    "failed": "失败",
}

TRIGGER_TEXT = {
    "manual": "手动",
    "scheduled": "定时",
    "group": "组执行",
}

TYPE_TEXT = {
    "template": "模板",
    "group": "备份组",
    "group_member": "组成员",
}


def _format_duration(seconds: float) -> str:
    if not seconds or seconds <= 0:
        return ""
    if seconds < 60:
        return f"{seconds:.0f}秒"
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}分{s}秒" if s else f"{m}分钟"


class LogDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("备份日志")
        self.setMinimumSize(700, 400)
        self.setWindowModality(Qt.ApplicationModal)
        self._build_ui()
        self._load_data()
        self._auto_resize()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title_bar = DialogTitleBar("备份日志")
        title_bar.close_clicked.connect(self.reject)
        root.addWidget(title_bar)

        content = QWidget()
        content.setObjectName("connDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels(
            ["时间", "模板", "状态", "类型", "触发", "服务器", "耗时",
             "新增", "更新", "跳过", "错误"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 140)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 60)
        self.table.setColumnWidth(3, 55)
        self.table.setColumnWidth(4, 45)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 50)
        self.table.setColumnWidth(7, 35)
        self.table.setColumnWidth(8, 35)
        self.table.setColumnWidth(9, 35)

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
        """)

        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.table, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        clear_btn = QPushButton("清除日志")
        clear_btn.setFixedHeight(30)
        clear_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['danger']}; background: transparent; "
            f"color: {COLORS['danger']}; border-radius: 4px; padding: 6px 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['danger_bg']}; }}"
        )
        clear_btn.clicked.connect(self._on_clear)
        btn_layout.addWidget(clear_btn)

        close_btn = QPushButton("关闭")
        close_btn.setFixedHeight(30)
        close_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
            f"color: {COLORS['text']}; border-radius: 4px; padding: 6px 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; }}"
        )
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        root.addWidget(content, 1)

    def _load_data(self) -> None:
        logs = load_backup_logs()
        logs.sort(key=lambda l: l.get("timestamp", ""), reverse=True)

        self.table.setRowCount(len(logs))
        for i, log in enumerate(logs):
            ts = log.get("timestamp", "")
            try:
                dt = ts.replace("T", " ")[:19]
            except Exception:
                dt = ts
            time_item = QTableWidgetItem(dt)
            time_item.setFlags(time_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, time_item)

            name_text = log.get("backup_name", "")
            member_summary = log.get("member_summary", "")
            backup_type = log.get("backup_type", "")
            if member_summary and backup_type == "group":
                name_text = f"{name_text} ({member_summary})"
            name_item = QTableWidgetItem(name_text)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 1, name_item)

            status = log.get("status", "unknown")
            status_item = QTableWidgetItem(STATUS_TEXT.get(status, status))
            status_item.setForeground(STATUS_COLORS.get(status, QColor(COLORS['text'])))
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 2, status_item)
            type_item = QTableWidgetItem(TYPE_TEXT.get(backup_type, ""))
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 3, type_item)

            trigger = log.get("trigger", "manual")
            trigger_item = QTableWidgetItem(TRIGGER_TEXT.get(trigger, trigger))
            trigger_item.setFlags(trigger_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 4, trigger_item)

            conn_name = log.get("connection_name", "")
            conn_item = QTableWidgetItem(conn_name)
            conn_item.setFlags(conn_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 5, conn_item)

            duration = log.get("duration_seconds", 0)
            dur_item = QTableWidgetItem(_format_duration(duration))
            dur_item.setFlags(dur_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 6, dur_item)

            new_count = log.get("new_files", 0)
            new_item = QTableWidgetItem(str(new_count) if new_count else "")
            new_item.setForeground(QColor(COLORS['mint']))
            new_item.setFlags(new_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 7, new_item)

            upd_count = log.get("updated_files", 0)
            upd_item = QTableWidgetItem(str(upd_count) if upd_count else "")
            upd_item.setForeground(QColor(COLORS['warning']))
            upd_item.setFlags(upd_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 8, upd_item)

            skip_count = log.get("skipped_files", 0)
            skip_item = QTableWidgetItem(str(skip_count) if skip_count else "")
            skip_item.setForeground(QColor(COLORS['text_hint']))
            skip_item.setFlags(skip_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 9, skip_item)

            errors = log.get("errors", [])
            err_text = " | ".join(errors[:3]) if errors else ""
            if len(errors) > 3:
                err_text += f" (+{len(errors) - 3})"
            # For group logs, show member summary
            member_summary = log.get("member_summary", "")
            if member_summary and backup_type == "group":
                if err_text:
                    err_text = f"{member_summary} | {err_text}"
                else:
                    err_text = member_summary
            err_item = QTableWidgetItem(err_text)
            if errors:
                err_item.setForeground(QColor(COLORS['danger']))
            err_item.setFlags(err_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 10, err_item)

    def _on_context_menu(self, pos: QPoint) -> None:
        row = self.table.rowAt(pos.y())
        if row < 0:
            return

        menu = QMenu(self)
        menu.setStyleSheet(menu_stylesheet())

        detail_action = menu.addAction("查看详情")
        action = menu.exec(QCursor.pos())

        if action == detail_action:
            logs = load_backup_logs()
            logs.sort(key=lambda l: l.get("timestamp", ""), reverse=True)
            if row < len(logs):
                log = logs[row]
                parts = []

                # Basic info
                name = log.get("backup_name", "")
                status = STATUS_TEXT.get(log.get("status", ""), "未知")
                parts.append(f"模板: {name}    状态: {status}")

                backup_type = log.get("backup_type", "")
                if backup_type:
                    parts.append(f"类型: {TYPE_TEXT.get(backup_type, backup_type)}")

                trigger = log.get("trigger", "manual")
                parts.append(f"触发: {TRIGGER_TEXT.get(trigger, trigger)}")

                conn = log.get("connection_name", "")
                if conn:
                    parts.append(f"服务器: {conn}")

                duration = log.get("duration_seconds", 0)
                if duration:
                    parts.append(f"耗时: {_format_duration(duration)}")

                file_count = log.get("file_count", 0)
                if file_count:
                    parts.append(f"文件数: {file_count}")

                # Incremental stats
                new_c = log.get("new_files", 0)
                upd_c = log.get("updated_files", 0)
                skip_c = log.get("skipped_files", 0)
                if new_c or upd_c or skip_c:
                    parts.append(f"新增: {new_c}  |  更新: {upd_c}  |  跳过: {skip_c}")

                # Group member details
                member_results = log.get("member_results", [])
                if member_results:
                    parts.append("成员详情:")
                    for m in member_results:
                        m_name = m.get("name", "?")
                        m_status = "成功" if m.get("status") == "success" else "失败"
                        m_files = m.get("file_count", 0)
                        m_new = m.get("new_files", 0)
                        m_upd = m.get("updated_files", 0)
                        m_skip = m.get("skipped_files", 0)
                        m_errs = m.get("error_count", 0)
                        line = f"  {m_name}: {m_status}, {m_files}个文件"
                        if m_new or m_upd or m_skip:
                            line += f" (新{m_new}/改{m_upd}/跳{m_skip})"
                        if m_errs:
                            line += f", {m_errs}个错误"
                        parts.append(line)

                errors = log.get("errors", [])
                if errors:
                    parts.append("错误:\n" + "\n".join(errors[:20]))

                show_message(self, "详情", "\n\n".join(parts) if parts else "无信息", "info")

    def _on_clear(self) -> None:
        reply = ask_question(self, "确认", "清除所有备份日志？")
        if reply:
            clear_backup_logs()
            self.table.setRowCount(0)
            self._auto_resize()

    def _auto_resize(self) -> None:
        self.table.resizeColumnsToContents()
        total = 0
        for col in range(self.table.columnCount()):
            total += self.table.columnWidth(col)
        total += self.table.verticalHeader().width()
        total += 40  # padding
        screen = self.screen()
        if screen:
            geo = screen.availableGeometry()
            max_w = geo.width() - 200
            max_h = geo.height() - 200
        else:
            max_w = 1100
            max_h = 700
        rows = self.table.rowCount()
        w = min(max(total, 700), max_w)
        h = min(max(120 + rows * 32, 400), max_h)
        self.resize(w, h)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setPen(QPen(QColor(COLORS['mint']), 3))
        painter.setBrush(QColor(COLORS['bg']))
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
        painter.end()
