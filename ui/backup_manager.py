import datetime
import logging
import os

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QProgressBar, QMenu
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor

from ui.style import COLORS, menu_stylesheet
from ui.backup_dialog import BackupDialog
from ui.progress_dialog import ProgressDialog
from ui.workers import SFTPWorker
from ui.message_dialog import show_message, ask_question
from core.config import (
    load_backups, add_backup, update_backup, delete_backup, add_backup_log
)
from core.sftp_client import BackupFile


logger = logging.getLogger("shiyun.backup_manager")


class BackupManager:
    """Manages backup template cards, execution, and restore operations."""

    def __init__(self, main_window) -> None:
        self.mw = main_window
        self._backup_widgets: dict[int, dict] = {}
        self.mw._backup_widgets = self._backup_widgets

    def refresh(self) -> None:
        self._backup_widgets.clear()
        while self.mw.backup_list_layout.count():
            item = self.mw.backup_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        backups = load_backups()
        for backup in backups:
            card = self._create_backup_card(backup)
            self.mw.backup_list_layout.addWidget(card)

    def _create_backup_card(self, backup: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("connCard")
        card.setFixedHeight(64)
        card.setCursor(Qt.PointingHandCursor)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        icon = QLabel("📋")
        icon.setStyleSheet("font-size: 14px;")
        layout.addWidget(icon)

        text_col = QWidget()
        text_layout = QVBoxLayout(text_col)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        name_label = QLabel(backup.get("name", "未命名"))
        name_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        text_layout.addWidget(name_label)

        remote_paths = backup.get("remote_paths", [])
        if not remote_paths and backup.get("remote_path"):
            remote_paths = [backup["remote_path"]]
        local_path = backup.get("local_path", "")
        if len(remote_paths) == 1:
            path_text = f"{remote_paths[0]} → {local_path}"
        elif len(remote_paths) > 1:
            path_text = f"{len(remote_paths)} 个项目 → {local_path}"
        else:
            path_text = local_path

        path_label = QLabel(path_text)
        path_label.setStyleSheet(f"font-size: 10px; color: {COLORS['text_sec']};")
        path_label.setWordWrap(True)
        text_layout.addWidget(path_label)

        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(4)

        conn_id = backup.get("connection_id")
        if conn_id is not None:
            from core.config import load_connections
            for c in load_connections():
                if c.get("id") == conn_id:
                    conn_label = QLabel(f"🔗 {c['name']}")
                    conn_label.setStyleSheet(f"font-size: 9px; color: {COLORS['text_hint']};")
                    info_row.addWidget(conn_label)
                    break

        if backup.get("schedule_enabled"):
            rule = backup.get("schedule_rule")
            if rule:
                from ui.schedule_picker import SchedulePicker
                picker = SchedulePicker()
                picker.set_schedule(backup)
                schedule_info = picker.get_summary_text()
                if backup.get("auto_shutdown"):
                    schedule_info += " | 关机"
            else:
                schedule_info = f"定时: {backup.get('schedule_time', '01:00')}"
                if backup.get("auto_shutdown"):
                    schedule_info += " | 关机"
            schedule_label = QLabel(schedule_info)
            schedule_label.setStyleSheet(f"font-size: 9px; color: {COLORS['mint']};")
            info_row.addWidget(schedule_label)

        info_row.addStretch()

        status_label = QLabel()
        status_label.setStyleSheet(f"font-size: 9px; color: {COLORS['text_hint']};")
        status_label.setVisible(False)
        info_row.addWidget(status_label)

        text_layout.addLayout(info_row)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setFixedHeight(3)
        progress_bar.setTextVisible(False)
        progress_bar.setVisible(False)
        progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['mint_light']};
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS['mint']};
                border-radius: 1px;
            }}
        """)
        text_layout.addWidget(progress_bar)

        layout.addWidget(text_col, 1)

        run_btn = QPushButton("▶")
        run_btn.setFixedSize(28, 28)
        run_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['mint']}; color: white; border: none; border-radius: 4px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['mint_dark']}; }}"
        )
        run_btn.clicked.connect(lambda: self.on_run(backup))
        layout.addWidget(run_btn)

        bid = backup.get("id")
        self._backup_widgets[bid] = {
            "progress": progress_bar,
            "status": status_label,
            "run_btn": run_btn,
            "card": card,
        }

        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(lambda pos, b=backup: self._context_menu(pos, b))

        return card

    def _context_menu(self, pos, backup):
        menu = QMenu(self.mw)
        menu.setStyleSheet(menu_stylesheet())
        edit_action = menu.addAction("编辑")
        restore_action = menu.addAction("恢复到服务器")
        delete_action = menu.addAction("删除")
        action = menu.exec(QCursor.pos())
        if action == edit_action:
            self.on_edit(backup)
        elif action == restore_action:
            self.on_restore(backup)
        elif action == delete_action:
            self.on_delete(backup)

    def on_add(self):
        dialog = BackupDialog(self.mw, sftp_client=self.mw.sftp)
        if dialog.exec() and dialog.result_data:
            add_backup(dialog.result_data)
            self.refresh()

    def on_edit(self, backup):
        dialog = BackupDialog(self.mw, backup=backup, sftp_client=self.mw.sftp)
        if dialog.exec() and dialog.result_data:
            update_backup(backup["id"], dialog.result_data)
            self.refresh()

    def on_delete(self, backup):
        reply = ask_question(self.mw, "确认", f"删除备份模板 \"{backup.get('name', '')}\"？")
        if reply:
            delete_backup(backup["id"])
            self.refresh()

    def on_restore(self, backup):
        if not self.mw.sftp.connected:
            show_message(self.mw, "提示", "请先连接到服务器", "warning")
            return

        local_path = backup.get("local_path", "")
        remote_paths = backup.get("remote_paths", [])
        if not remote_paths and backup.get("remote_path"):
            remote_paths = [backup["remote_path"]]
        if not remote_paths or not local_path:
            show_message(self.mw, "提示", "备份模板缺少路径配置", "warning")
            return

        reply = ask_question(self.mw, "恢复确认",
                             f"将本地 {local_path} 的文件恢复到服务器？\n目标: {', '.join(remote_paths)}")
        if not reply:
            return

        name = backup.get("name", "未命名")
        progress = ProgressDialog(self.mw, title=f"恢复: {name}")

        def _restore_multi(progress_callback=None):
            from core.settings_manager import SettingsManager
            max_workers = SettingsManager.instance().get("download_concurrency", 3)
            files_to_upload = []

            for rpath in remote_paths:
                rpath = rpath.replace("\\", "/").rstrip("/") or "/"
                parts = [p for p in rpath.split("/") if p]
                item_name = parts[-1] if parts else "root"
                local_dest = os.path.join(os.path.abspath(local_path), item_name)
                if not os.path.exists(local_dest):
                    continue
                if os.path.isfile(local_dest):
                    files_to_upload.append((local_dest, rpath))
                elif os.path.isdir(local_dest):
                    for dirpath, _, filenames in os.walk(local_dest):
                        for fname in filenames:
                            local_file = os.path.join(dirpath, fname)
                            rel = os.path.relpath(local_file, os.path.abspath(local_path))
                            remote_file = f"{rpath}/{rel.replace(os.sep, '/')}"
                            files_to_upload.append((local_file, remote_file))

            if not files_to_upload:
                return [], 0, 0

            remote_dirs = set()
            for _, remote_file in files_to_upload:
                remote_dir = "/".join(remote_file.split("/")[:-1])
                if remote_dir:
                    remote_dirs.add(remote_dir)
            for d in sorted(remote_dirs):
                try:
                    self.mw.sftp.mkdir_remote(d)
                except Exception as e:
                    logger.warning(f"创建远端目录失败 {d}: {e}")

            def _file_progress(fname, transferred, total_bytes):
                if progress_callback:
                    progress_callback(transferred, total_bytes)

            errors = self.mw.sftp.upload_parallel(
                files_to_upload,
                file_progress=_file_progress,
                max_workers=max_workers,
            )
            return errors, len(files_to_upload) - len(errors), 0

        worker = SFTPWorker(self.mw.sftp, _restore_multi, progress_callback=True)
        worker.finished.connect(lambda result: self._on_restore_done(name, progress, result))
        worker.error.connect(lambda err: self._on_restore_error(name, err, progress))
        worker.progress.connect(lambda v, t: progress.update_progress(v, t, f"恢复中: {name}"))
        self.mw._worker = worker
        worker.start()
        progress.show_centered(self.mw)

    def _on_restore_done(self, name, progress, result=None):
        if isinstance(result, tuple):
            errors, file_count, total_size = result
        else:
            errors = result
            file_count = 0
        status = "partial" if errors else "success"
        add_backup_log({
            "backup_id": 0,
            "backup_name": name,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": status,
            "file_count": file_count,
            "retry_count": 0,
            "errors": errors or [],
            "trigger": "manual",
            "backup_type": "template",
            "connection_name": "",
            "duration_seconds": 0,
        })
        progress.set_result(errors, file_count)

    def _on_restore_error(self, name, err, progress):
        add_backup_log({
            "backup_id": 0,
            "backup_name": name,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "failed",
            "file_count": 0,
            "retry_count": 0,
            "errors": [str(err)],
            "trigger": "manual",
            "backup_type": "template",
            "connection_name": "",
            "duration_seconds": 0,
        })
        progress.set_result([str(err)], 0)

    def on_run(self, backup):
        remote_paths = backup.get("remote_paths", [])
        if not remote_paths and backup.get("remote_path"):
            remote_paths = [backup["remote_path"]]
        local_path = backup.get("local_path", "")
        name = backup.get("name", "未命名")

        if not remote_paths:
            show_message(self.mw, "提示", "没有配置远程备份路径", "warning")
            return

        reply = ask_question(self.mw, "确认备份",
                             f"确认执行备份模板 \"{name}\"？\n"
                             f"远程: {', '.join(remote_paths)}\n"
                             f"本地: {local_path}")
        if not reply:
            return

        # Auto-connect if not connected
        if not self.mw.sftp.connected:
            conn_id = backup.get("connection_id")
            if conn_id is not None:
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
                            "backup_id": backup.get("id"),
                            "backup_name": name,
                            "timestamp": datetime.datetime.now().isoformat(),
                            "status": "failed",
                            "file_count": 0,
                            "retry_count": 0,
                            "errors": [f"连接失败: {e}"],
                            "trigger": "manual",
                            "backup_type": "template",
                            "connection_name": conn.get("name", ""),
                            "duration_seconds": 0,
                        })
                        show_message(self.mw, "连接失败",
                                     f"无法连接到服务器 {conn.get('name', '')}:\n{e}", "error")
                        return
                else:
                    show_message(self.mw, "提示", "关联的服务器不存在", "warning")
                    return
            else:
                show_message(self.mw, "提示", "未关联服务器且当前未连接，请先连接", "warning")
                return

        _start_time = datetime.datetime.now().isoformat()

        progress = ProgressDialog(self.mw, title="备份中", message=f"正在备份: {name}")
        progress.cancelled.connect(lambda: self.mw.file_manager._cancel_worker(progress))

        import stat as _stat

        def _backup_multi(progress_callback=None):
            from core.settings_manager import SettingsManager
            max_workers = SettingsManager.instance().get("download_concurrency", 3)
            base_dir = os.path.abspath(local_path)
            os.makedirs(base_dir, exist_ok=True)
            MAX_VERIFY_RETRIES = 3
            incremental = backup.get("incremental", False)
            new_files = updated_files = skipped_files = 0

            for attempt in range(MAX_VERIFY_RETRIES):
                files_to_download = []
                classified_files = []
                for rpath in remote_paths:
                    rpath = rpath.replace("\\", "/").rstrip("/") or "/"
                    parts = [p for p in rpath.split("/") if p]
                    item_name = parts[-1] if parts else "root"
                    local_dest = os.path.join(base_dir, item_name)
                    try:
                        st = self.mw.sftp.stat(rpath)
                        if _stat.S_ISDIR(st.st_mode):
                            if incremental:
                                self.mw.sftp._collect_files_for_backup_incremental(
                                    rpath, local_dest, classified_files)
                            else:
                                self.mw.sftp._collect_files_for_backup(
                                    rpath, local_dest, files_to_download)
                        else:
                            if incremental:
                                remote_mtime = st.st_mtime or 0
                                if not os.path.exists(local_dest):
                                    classified_files.append(
                                        BackupFile(rpath, local_dest, "new"))
                                else:
                                    local_mtime = os.path.getmtime(local_dest)
                                    if remote_mtime > local_mtime + 2.0:
                                        classified_files.append(
                                            BackupFile(rpath, local_dest, "updated"))
                                    else:
                                        classified_files.append(
                                            BackupFile(rpath, local_dest, "skipped"))
                            else:
                                files_to_download.append((rpath, local_dest))
                    except Exception as e:
                        return [f"{rpath}: {e}"], 0, 0, 0, 0, 0

                if incremental:
                    new_files = sum(1 for f in classified_files if f.status == "new")
                    updated_files = sum(1 for f in classified_files if f.status == "updated")
                    skipped_files = sum(1 for f in classified_files if f.status == "skipped")
                    files_to_download = [(f.remote, f.local) for f in classified_files
                                         if f.status in ("new", "updated")]

                total = len(files_to_download)

                def _file_progress(name, transferred, total_bytes):
                    if progress_callback:
                        progress_callback(transferred, total_bytes)

                errors = self.mw.sftp.download_parallel(
                    files_to_download,
                    file_progress=_file_progress,
                    max_workers=max_workers,
                )
                completed_files = total - len(errors)

                if errors:
                    if progress_callback:
                        progress_callback(total, total)
                    return errors, completed_files, 0, new_files, updated_files, skipped_files

                verify_errors = []
                for rpath in remote_paths:
                    rpath = rpath.replace("\\", "/").rstrip("/") or "/"
                    parts = [p for p in rpath.split("/") if p]
                    item_name = parts[-1] if parts else "root"
                    local_dest = os.path.join(base_dir, item_name)
                    verify_errors.extend(self.mw.sftp.verify_download(rpath, local_dest))

                if not verify_errors:
                    if progress_callback:
                        progress_callback(total, total)
                    return [], completed_files, 0, new_files, updated_files, skipped_files

                if attempt < MAX_VERIFY_RETRIES - 1:
                    logger.warning(f"验证失败 (第{attempt+1}次), {len(verify_errors)} 个文件不匹配, 重试中…")
                else:
                    errors = [f"验证失败: {e}" for e in verify_errors]
                    if progress_callback:
                        progress_callback(total, total)
                    return errors, completed_files, 0, new_files, updated_files, skipped_files

            return [], 0, 0, 0, 0, 0

        worker = SFTPWorker(self.mw.sftp, _backup_multi, progress_callback=True)
        worker.finished.connect(lambda result: self._on_backup_done(backup, name, progress, result, _start_time))
        worker.error.connect(lambda err: self._on_backup_error(backup, name, err, progress))
        worker.progress.connect(lambda v, t: progress.update_progress(v, t, f"备份中: {name}"))
        self.mw._worker = worker

        bid = backup.get("id")
        widgets = self._backup_widgets.get(bid)
        if widgets:
            widgets["progress"].setVisible(True)
            widgets["progress"].setValue(0)
            widgets["status"].setVisible(True)
            widgets["status"].setText("备份中...")
            widgets["run_btn"].setEnabled(False)

            def _update_card_progress(v, t):
                if widgets["progress"].isVisible():
                    pct = int(v / t * 100) if t > 0 else 0
                    widgets["progress"].setValue(pct)
                    widgets["status"].setText(f"{pct}%")

            worker.progress.connect(_update_card_progress)

            def _cleanup_card():
                widgets["progress"].setVisible(False)
                widgets["status"].setVisible(False)
                widgets["run_btn"].setEnabled(True)

            worker.finished.connect(lambda _: _cleanup_card())
            worker.error.connect(lambda _: _cleanup_card())

        worker.start()
        self.mw.file_manager._progress = progress
        progress.show_centered(self.mw)

    def _on_backup_done(self, backup, name, progress, result=None, start_time=None):
        new_files = updated_files = skipped_files = 0
        if isinstance(result, tuple):
            if len(result) == 6:
                errors, file_count, total_size, new_files, updated_files, skipped_files = result
            else:
                errors, file_count, total_size = result
        else:
            errors = result
            file_count = 0
            total_size = 0
        has_errors = errors and len(errors) > 0
        status = "partial" if has_errors else "success"

        # Compute duration
        duration = 0
        if start_time:
            try:
                start_dt = datetime.datetime.fromisoformat(start_time)
                duration = (datetime.datetime.now() - start_dt).total_seconds()
            except Exception:
                pass

        # Connection name
        conn_name = ""
        conn_id = backup.get("connection_id")
        if conn_id is not None:
            from core.config import load_connections
            for c in load_connections():
                if c.get("id") == conn_id:
                    conn_name = c.get("name", "")
                    break

        add_backup_log({
            "backup_id": backup.get("id"),
            "backup_name": name,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": status,
            "file_count": file_count,
            "retry_count": 0,
            "errors": errors or [],
            "trigger": "manual",
            "backup_type": "template",
            "connection_name": conn_name,
            "duration_seconds": round(duration, 1),
            "new_files": new_files,
            "updated_files": updated_files,
            "skipped_files": skipped_files,
        })
        if has_errors:
            total = len(errors)
            shown = errors[:10]
            msg = f"备份完成，但 {total} 个文件失败:\n" + "\n".join(shown)
            if total > 10:
                msg += f"\n...还有 {total - 10} 个错误"
            progress.set_error(msg)
            self.mw.status_label.setText(f"备份完成（有错误）: {name}")
        else:
            progress.set_complete(f"备份完成: {name}")
            self.mw.status_label.setText(f"备份完成: {name}")
            if backup.get("auto_shutdown"):
                self._do_shutdown()

    def _on_backup_error(self, backup, name, err, progress):
        conn_name = ""
        conn_id = backup.get("connection_id")
        if conn_id is not None:
            from core.config import load_connections
            for c in load_connections():
                if c.get("id") == conn_id:
                    conn_name = c.get("name", "")
                    break
        add_backup_log({
            "backup_id": backup.get("id"),
            "backup_name": name,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": "failed",
            "file_count": 0,
            "retry_count": 0,
            "errors": [str(err)],
            "trigger": "manual",
            "backup_type": "template",
            "connection_name": conn_name,
            "duration_seconds": 0,
        })
        progress.set_error(f"备份失败: {err}")
        self.mw.status_label.setText(f"备份失败: {name}")

    def _do_shutdown(self):
        reply = ask_question(self.mw, "自动关机",
                             "备份成功，60 秒后将自动关机。\n是否立即关机？\n（取消可终止关机）")
        if reply:
            import subprocess
            subprocess.Popen(["shutdown", "/s", "/t", "0", "/c", "拾云备份完成，即将关机"])
        else:
            import subprocess
            subprocess.Popen(["shutdown", "/a"])

    def on_run_for_group(self, backup, progress, on_done=None, group_settings=None):
        """Execute a backup with an external progress dialog (used by GroupManager).
        group_settings: dict with 'incremental' and 'auto_shutdown' from the group,
        which override individual backup settings.
        """
        import stat as _stat
        name = backup.get("name", "未命名")
        _start_time = datetime.datetime.now().isoformat()
        remote_paths = backup.get("remote_paths", [])
        if not remote_paths and backup.get("remote_path"):
            remote_paths = [backup["remote_path"]]
        local_path = backup.get("local_path", "")

        # Group settings override individual backup settings
        incremental = backup.get("incremental", False)
        if group_settings and "incremental" in group_settings:
            incremental = group_settings["incremental"]

        def _backup_op(progress_callback=None):
            from core.settings_manager import SettingsManager
            max_workers = SettingsManager.instance().get("download_concurrency", 3)
            base_dir = os.path.abspath(local_path)
            os.makedirs(base_dir, exist_ok=True)
            files_to_download = []
            classified_files = []
            new_files = updated_files = skipped_files = 0

            for rpath in remote_paths:
                rpath = rpath.replace("\\", "/").rstrip("/") or "/"
                parts = [p for p in rpath.split("/") if p]
                item_name = parts[-1] if parts else "root"
                local_dest = os.path.join(base_dir, item_name)
                try:
                    st = self.mw.sftp.stat(rpath)
                    if _stat.S_ISDIR(st.st_mode):
                        if incremental:
                            self.mw.sftp._collect_files_for_backup_incremental(
                                rpath, local_dest, classified_files)
                        else:
                            self.mw.sftp._collect_files_for_backup(
                                rpath, local_dest, files_to_download)
                    else:
                        if incremental:
                            remote_mtime = st.st_mtime or 0
                            if not os.path.exists(local_dest):
                                classified_files.append(
                                    BackupFile(rpath, local_dest, "new"))
                            else:
                                local_mtime = os.path.getmtime(local_dest)
                                if remote_mtime > local_mtime + 2.0:
                                    classified_files.append(
                                        BackupFile(rpath, local_dest, "updated"))
                                else:
                                    classified_files.append(
                                        BackupFile(rpath, local_dest, "skipped"))
                        else:
                            files_to_download.append((rpath, local_dest))
                except Exception as e:
                    return [f"{rpath}: {e}"], 0, 0, 0, 0, 0

            if incremental:
                new_files = sum(1 for f in classified_files if f.status == "new")
                updated_files = sum(1 for f in classified_files if f.status == "updated")
                skipped_files = sum(1 for f in classified_files if f.status == "skipped")
                files_to_download = [(f.remote, f.local) for f in classified_files
                                     if f.status in ("new", "updated")]

            def _file_progress(n, transferred, total_bytes):
                if progress_callback:
                    progress_callback(transferred, total_bytes)

            errors = self.mw.sftp.download_parallel(
                files_to_download,
                file_progress=_file_progress,
                max_workers=max_workers,
            )
            completed = len(files_to_download) - len(errors)
            return errors, completed, 0, new_files, updated_files, skipped_files

        worker = SFTPWorker(self.mw.sftp, _backup_op, progress_callback=True)
        worker.finished.connect(lambda result: self._on_group_member_done(name, progress, result, on_done))
        worker.error.connect(lambda err: self._on_group_member_done(name, progress, [str(err)], on_done))
        worker.progress.connect(lambda v, t: progress.update_progress(v, t, f"备份中: {name}"))
        self.mw._worker = worker
        worker.start()

    def _on_group_member_done(self, name, progress, result, on_done=None):
        new_files = updated_files = skipped_files = 0
        file_count = 0
        if isinstance(result, tuple):
            errors = result[0]
            if len(result) == 6:
                _, file_count, _, new_files, updated_files, skipped_files = result
        else:
            errors = result

        # Always log group member results (success or error)
        status = "success" if not errors else "partial"
        add_backup_log({
            "backup_id": 0,
            "backup_name": name,
            "timestamp": datetime.datetime.now().isoformat(),
            "status": status,
            "file_count": file_count,
            "retry_count": 0,
            "errors": errors if isinstance(errors, list) else [str(errors)] if errors else [],
            "trigger": "group",
            "backup_type": "group_member",
            "connection_name": "",
            "duration_seconds": 0,
            "new_files": new_files,
            "updated_files": updated_files,
            "skipped_files": skipped_files,
        })
        if on_done:
            on_done(errors, {
                "name": name,
                "status": status,
                "file_count": file_count,
                "new_files": new_files,
                "updated_files": updated_files,
                "skipped_files": skipped_files,
                "error_count": len(errors) if errors else 0,
            })
