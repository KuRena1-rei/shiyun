import datetime

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMenu
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor

from ui.style import COLORS, menu_stylesheet
from ui.message_dialog import show_message, ask_question
from ui.progress_dialog import ProgressDialog
from core.config import (
    load_backup_groups, load_backups, add_backup_group,
    update_backup_group, delete_backup_group, update_backup,
    add_backup_log,
)


class GroupManager:
    """Manages backup group cards, CRUD, and group execution."""

    def __init__(self, main_window) -> None:
        self.mw = main_window

    def refresh(self) -> None:
        while self.mw.group_list_layout.count():
            item = self.mw.group_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        groups = load_backup_groups()
        backups_map = {b.get("id"): b for b in load_backups()}

        for group in groups:
            card = self._create_group_card(group, backups_map)
            self.mw.group_list_layout.addWidget(card)

        if not groups:
            hint = QLabel("暂无备份组")
            hint.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']}; padding: 8px;")
            hint.setAlignment(Qt.AlignCenter)
            self.mw.group_list_layout.addWidget(hint)

    def _create_group_card(self, group, backups_map) -> QWidget:
        card = QWidget()
        card.setObjectName("connCard")
        card.setFixedHeight(64)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            f"QWidget#connCard {{ border: 1px solid {COLORS['border']}; border-radius: 8px; "
            f"background: {COLORS['mint_light']}; }}"
            f"QWidget#connCard:hover {{ background: {COLORS['mint_hover']}; }}"
        )

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)

        icon = QLabel("📁📁")
        icon.setStyleSheet("font-size: 16px;")
        icon.setFixedWidth(28)
        layout.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name = group.get("name", "未命名")
        name_label = QLabel(name)
        name_label.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {COLORS['text']};")
        text_col.addWidget(name_label)

        bid_count = len(group.get("backup_ids", []))
        info_parts = [f"{bid_count} 个模板"]
        if group.get("schedule_enabled"):
            from ui.schedule_picker import SchedulePicker
            _picker = SchedulePicker()
            _picker.set_schedule(group)
            info_parts.append(_picker.get_summary_text())
        info_label = QLabel(" | ".join(info_parts))
        info_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_sec']};")
        text_col.addWidget(info_label)

        layout.addLayout(text_col, 1)

        run_btn = QPushButton("▶")
        run_btn.setFixedSize(28, 28)
        run_btn.setStyleSheet(
            f"QPushButton {{ border: none; background: {COLORS['mint']}; color: white; "
            f"border-radius: 14px; font-size: 10px; }}"
            f"QPushButton:hover {{ background: {COLORS['mint_dark']}; }}"
        )
        run_btn.clicked.connect(lambda _, g=group: self.on_run(g))
        layout.addWidget(run_btn, 0, Qt.AlignVCenter)

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos, g=group: self._context_menu(pos, g))

        return card

    def _context_menu(self, pos, group):
        menu = QMenu(self.mw)
        menu.setStyleSheet(menu_stylesheet())
        edit_action = menu.addAction("编辑")
        delete_action = menu.addAction("删除")
        action = menu.exec(QCursor.pos())
        if action == edit_action:
            self.on_edit(group)
        elif action == delete_action:
            self.on_delete(group)

    def on_add(self):
        from ui.group_dialog import GroupDialog
        dialog = GroupDialog(self.mw)
        if dialog.exec() and dialog.result_data:
            new_group = add_backup_group(dialog.result_data)
            for bid in new_group.get("backup_ids", []):
                update_backup(bid, {"schedule_enabled": False})
            self.refresh()
            self.mw.backup_manager.refresh()

    def on_edit(self, group):
        from ui.group_dialog import GroupDialog
        dialog = GroupDialog(self.mw, group=group)
        if dialog.exec() and dialog.result_data:
            old_ids = set(group.get("backup_ids", []))
            new_ids = set(dialog.result_data.get("backup_ids", []))
            update_backup_group(group["id"], dialog.result_data)
            for bid in old_ids - new_ids:
                update_backup(bid, {"schedule_enabled": True})
            for bid in new_ids - old_ids:
                update_backup(bid, {"schedule_enabled": False})
            self.refresh()
            self.mw.backup_manager.refresh()

    def on_delete(self, group):
        reply = ask_question(self.mw, "确认",
                             f"删除备份组 \"{group.get('name', '')}\"？\n组内模板的定时任务将恢复。")
        if reply:
            for bid in group.get("backup_ids", []):
                update_backup(bid, {"schedule_enabled": True})
            delete_backup_group(group["id"])
            self.refresh()
            self.mw.backup_manager.refresh()

    def on_run(self, group):
        backups = load_backups()
        backups_map = {b.get("id"): b for b in backups}
        bid_list = group.get("backup_ids", [])
        queue = [backups_map[bid] for bid in bid_list if bid in backups_map]
        if not queue:
            show_message(self.mw, "提示", "备份组内没有有效的备份模板", "warning")
            return

        group_name = group.get("name", "未命名")
        names = [b.get("name", "未命名") for b in queue]
        reply = ask_question(self.mw, "确认备份",
                             f"确认执行备份组 \"{group_name}\"？\n"
                             f"包含 {len(queue)} 个模板: {', '.join(names)}")
        if not reply:
            return

        # Auto-connect all needed servers before starting
        needed_conn_ids = set()
        for b in queue:
            cid = b.get("connection_id")
            if cid is not None:
                needed_conn_ids.add(cid)
        for conn_id in needed_conn_ids:
            if self.mw.sftp.connected and self.mw.conn_manager.current_conn_id == conn_id:
                continue
            from core.config import load_connections
            conn = None
            for c in load_connections():
                if c.get("id") == conn_id:
                    conn = c
                    break
            if conn:
                try:
                    self.mw.sftp.connect(
                        host=conn["host"], port=conn["port"],
                        username=conn["username"],
                        password=conn.get("password", "")
                    )
                    self.mw.conn_manager.current_conn_id = conn_id
                except Exception as e:
                    add_backup_log({
                        "backup_id": group.get("id"),
                        "backup_name": f"[组] {group_name}",
                        "timestamp": datetime.datetime.now().isoformat(),
                        "status": "failed",
                        "file_count": 0,
                        "retry_count": 0,
                        "errors": [f"连接失败: {e}"],
                        "trigger": "manual",
                        "backup_type": "group",
                        "connection_name": conn.get("name", ""),
                        "duration_seconds": 0,
                    })
                    show_message(self.mw, "连接失败",
                                 f"无法连接到服务器 {conn.get('name', '')}:\n{e}", "error")
                    return
            else:
                conn_name = conn_id
                for b in queue:
                    if b.get("connection_id") == conn_id:
                        conn_name = b.get("name", conn_id)
                        break
                show_message(self.mw, "提示",
                             f"模板 \"{conn_name}\" 关联的服务器不存在", "warning")
                return

        start_time = datetime.datetime.now()
        progress = ProgressDialog(self.mw, title=f"备份组: {group_name}")
        progress.cancelled.connect(lambda: self.mw.file_manager._cancel_worker(progress))

        # Group-level settings that override individual template settings
        group_settings = {
            "incremental": group.get("incremental", False),
            "auto_shutdown": group.get("auto_shutdown", False),
        }

        all_errors = []
        member_results = []
        total_members = len(queue)

        def _run_next():
            if not queue:
                # All backups done — log group result and show summary
                duration = (datetime.datetime.now() - start_time).total_seconds()
                status = "success" if not all_errors else "partial"

                # Aggregate stats from members
                total_new = sum(m.get("new_files", 0) for m in member_results)
                total_upd = sum(m.get("updated_files", 0) for m in member_results)
                total_skip = sum(m.get("skipped_files", 0) for m in member_results)
                total_files = sum(m.get("file_count", 0) for m in member_results)
                success_count = sum(1 for m in member_results if m.get("status") == "success")
                fail_count = len(member_results) - success_count

                add_backup_log({
                    "backup_id": group.get("id"),
                    "backup_name": f"[组] {group_name}",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "status": status,
                    "file_count": total_files,
                    "retry_count": 0,
                    "errors": all_errors,
                    "trigger": "manual",
                    "backup_type": "group",
                    "connection_name": "",
                    "duration_seconds": round(duration, 1),
                    "new_files": total_new,
                    "updated_files": total_upd,
                    "skipped_files": total_skip,
                    "member_results": member_results,
                    "member_summary": f"{success_count}成功/{fail_count}失败, 共{total_members}个模板",
                })
                if all_errors:
                    total = len(all_errors)
                    shown = all_errors[:10]
                    msg = f"备份组完成，但 {total} 个文件失败:\n" + "\n".join(shown)
                    if total > 10:
                        msg += f"\n...还有 {total - 10} 个错误"
                    progress.set_error(msg)
                else:
                    progress.set_complete(f"备份组完成: {group_name}")
                # Group-level auto shutdown
                if group_settings.get("auto_shutdown") and not all_errors:
                    self.mw.backup_manager._do_shutdown()
                return
            backup = queue.pop(0)

            def _on_member_done(errors=None, member_info=None):
                if errors:
                    all_errors.extend(errors if isinstance(errors, list) else [str(errors)])
                if member_info:
                    member_results.append(member_info)
                _run_next()

            self.mw.backup_manager.on_run_for_group(
                backup, progress, _on_member_done, group_settings=group_settings)

        _run_next()
        progress.show_centered(self.mw)
