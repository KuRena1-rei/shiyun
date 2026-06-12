from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from croniter import croniter
from PySide6.QtCore import QObject, QTimer, Signal

from core.config import load_backups, add_backup_log, update_backup, load_connections
from core.config import load_backup_groups, update_backup_group
from core.sftp_client import BackupFile
from ui.message_dialog import show_message

MAX_RETRIES = 3
RETRY_DELAY_MS = 5 * 60 * 1000  # 5 minutes

logger = logging.getLogger("shiyun.scheduler")


class BackupScheduler(QObject):
    backup_triggered = Signal(dict)

    def __init__(self, main_window: Any) -> None:
        super().__init__()
        self.window = main_window
        self._running = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(60000)

    @staticmethod
    def _build_cron(rule: dict) -> str:
        time_str = rule.get("time", "01:00")
        hour, minute = time_str.split(":")
        freq = rule.get("freq", "daily")

        if freq == "daily":
            return f"{minute} {hour} * * *"
        elif freq == "interval":
            interval = rule.get("interval", 1)
            return f"{minute} {hour} */{interval} * *"
        elif freq == "weekly":
            # weekday 存储为 0=周一..6=周日（Python datetime 约定）
            # croniter 使用 0=周日..6=周六，需要 +1 转换
            weekdays = rule.get("weekdays", [0])
            cron_weekdays = [(d + 1) % 7 for d in weekdays]
            return f"{minute} {hour} * * {','.join(str(d) for d in cron_weekdays)}"
        elif freq == "monthly":
            day = rule.get("month_day", 1)
            return f"{minute} {hour} {day} * *"
        return f"{minute} {hour} * * *"

    @staticmethod
    def should_run(backup: dict, now: datetime) -> bool:
        if not backup.get("schedule_enabled"):
            return False

        next_run_str = backup.get("next_run")
        if next_run_str:
            try:
                next_run = datetime.fromisoformat(next_run_str)
                if now >= next_run:
                    retry_count = backup.get("_retry_count", 0)
                    if retry_count >= MAX_RETRIES:
                        logger.debug(f"should_run: 已达最大重试次数 {MAX_RETRIES}, 跳过")
                        return False
                    logger.debug(f"should_run: next_run={next_run_str}, now={now.isoformat()}, retry={retry_count}/{MAX_RETRIES}, result=True")
                    return True
                logger.debug(f"should_run: next_run={next_run_str}, now={now.isoformat()}, result=False")
                return False
            except (ValueError, TypeError):
                logger.warning(f"should_run: 无法解析 next_run={next_run_str}")

        schedule_time = backup.get("schedule_time", "01:00")
        now_hm = now.strftime("%H:%M")
        result = now_hm == schedule_time
        logger.debug(f"should_run fallback: schedule_time={schedule_time}, now={now_hm}, result={result}")
        return result

    def _advance_next_run(self, backup_id: int, backup_mem: dict) -> None:
        backups = load_backups()
        backup = None
        for b in backups:
            if b.get("id") == backup_id:
                backup = b
                break
        if not backup:
            return

        rule = backup.get("schedule_rule")
        if not rule:
            return

        end_type = rule.get("end_type", "never")
        if end_type == "count":
            run_count = backup.get("_run_count", 0) + 1
            max_count = rule.get("end_count", 0)
            update_data = {"_run_count": run_count}
            if run_count >= max_count:
                update_data["next_run"] = None
                update_data["schedule_enabled"] = False
            else:
                cron_expr = self._build_cron(rule)
                try:
                    cron = croniter(cron_expr, datetime.now())
                    next_dt = cron.get_next(datetime)
                    update_data["next_run"] = next_dt.isoformat()
                except Exception:
                    update_data["next_run"] = None
                    update_data["schedule_enabled"] = False
            update_backup(backup_id, update_data)
            return

        cron_expr = self._build_cron(rule)
        try:
            cron = croniter(cron_expr, datetime.now())
            next_dt = cron.get_next(datetime)
        except Exception:
            update_backup(backup_id, {"next_run": None, "schedule_enabled": False})
            return

        if end_type == "date":
            end_date = rule.get("end_date", "")
            if end_date:
                time_str = rule.get("time", "01:00")
                h, m = time_str.split(":")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                end_dt = end_dt.replace(hour=int(h), minute=int(m))
                if next_dt > end_dt:
                    update_backup(backup_id, {
                        "next_run": None,
                        "schedule_enabled": False,
                    })
                    return

        update_backup(backup_id, {"next_run": next_dt.isoformat()})

    def _check(self) -> None:
        try:
            if self._running:
                logger.debug("_check: 跳过，已有备份在运行中")
                return

            backups = load_backups()
            now = datetime.now()
            logger.debug(f"_check: 检查 {len(backups)} 个备份模板, 当前时间={now.isoformat()}")
            for backup in backups:
                nr = backup.get('next_run', 'None')
                se = backup.get('schedule_enabled', False)
                rc = backup.get('_retry_count', 0)
                logger.debug(f"  备份 '{backup.get('name')}': enabled={se}, next_run={nr}, retry={rc}/{MAX_RETRIES}")
                if self.should_run(backup, now):
                    logger.debug(f"  -> 触发备份!")
                    self._run_backup(backup)
                    break
            else:
                # Check backup groups
                groups = load_backup_groups()
                for group in groups:
                    if self.should_run(group, now):
                        logger.debug(f"  -> 触发备份组 '{group.get('name')}'!")
                        self._run_group(group)
                        break
                else:
                    logger.debug("  没有需要执行的备份")
        except Exception as e:
            logger.error(f"_check 异常: {e}", exc_info=True)
            self.window.status_label.setText(f"调度器错误: {e}")

    def _find_connection(self, backup: dict) -> dict | None:
        conn_id = backup.get("connection_id")
        if conn_id is None:
            return None
        connections = load_connections()
        for conn in connections:
            if conn.get("id") == conn_id:
                return conn
        return None

    def _run_backup(self, backup: dict) -> None:
        self._running = True
        backup_id = backup.get("id")
        name = backup.get("name", "未命名")
        logger.debug(f"_run_backup: 开始备份 '{name}' (id={backup_id})")

        remote_paths = backup.get("remote_paths", [])
        if not remote_paths and backup.get("remote_path"):
            remote_paths = [backup["remote_path"]]
        local_path = backup.get("local_path", "")

        already_connected = self.window.sftp.connected
        conn = self._find_connection(backup) if not already_connected else None

        bid = backup.get("id")
        widgets = self.window._backup_widgets.get(bid)

        import os
        import stat as _stat

        def _backup_with_connect(progress_callback=None):
            auto_connected = False
            if not self.window.sftp.connected and conn:
                self.window.sftp.connect(
                    host=conn["host"], port=conn["port"],
                    username=conn["username"], password=conn.get("password", "")
                )
                auto_connected = True

            from core.settings_manager import SettingsManager
            max_workers = SettingsManager.instance().get("download_concurrency", 3)
            MAX_VERIFY_RETRIES = 3
            base_dir = os.path.abspath(local_path)
            os.makedirs(base_dir, exist_ok=True)
            incremental = backup.get("incremental", False)
            new_files = updated_files = skipped_files = 0

            for attempt in range(MAX_VERIFY_RETRIES):
                # Collect all files for parallel download
                files_to_download = []
                classified_files = []
                for rpath in remote_paths:
                    rpath = rpath.replace("\\", "/").rstrip("/") or "/"
                    parts = [p for p in rpath.split("/") if p]
                    item_name = parts[-1] if parts else "root"
                    local_dest = os.path.join(base_dir, item_name)
                    try:
                        st = self.window.sftp.stat(rpath)
                        if _stat.S_ISDIR(st.st_mode):
                            if incremental:
                                self.window.sftp._collect_files_for_backup_incremental(
                                    rpath, local_dest, classified_files)
                            else:
                                self.window.sftp._collect_files_for_backup(
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
                        return [f"{rpath}: {e}"], 0, 0, auto_connected, 0, 0, 0

                if incremental:
                    new_files = sum(1 for f in classified_files if f.status == "new")
                    updated_files = sum(1 for f in classified_files if f.status == "updated")
                    skipped_files = sum(1 for f in classified_files if f.status == "skipped")
                    files_to_download = [(f.remote, f.local) for f in classified_files
                                         if f.status in ("new", "updated")]

                def _file_progress(name, transferred, total_bytes):
                    if progress_callback:
                        progress_callback(transferred, total_bytes)

                errors = self.window.sftp.download_parallel(
                    files_to_download,
                    file_progress=_file_progress,
                    max_workers=max_workers,
                )
                completed_files = len(files_to_download) - len(errors)

                if errors:
                    return errors, completed_files, 0, auto_connected, new_files, updated_files, skipped_files

                # Verify
                verify_errors = []
                for rpath in remote_paths:
                    rpath = rpath.replace("\\", "/").rstrip("/") or "/"
                    parts = [p for p in rpath.split("/") if p]
                    item_name = parts[-1] if parts else "root"
                    local_dest = os.path.join(base_dir, item_name)
                    verify_errors.extend(self.window.sftp.verify_download(rpath, local_dest))

                if not verify_errors:
                    return [], completed_files, 0, auto_connected, new_files, updated_files, skipped_files

                if attempt < MAX_VERIFY_RETRIES - 1:
                    logger.warning(f"验证失败 (第{attempt+1}次), {len(verify_errors)} 个文件不匹配, 重试中…")
                else:
                    errors = [f"验证失败: {e}" for e in verify_errors]
                    return errors, completed_files, 0, auto_connected, new_files, updated_files, skipped_files

            return [], completed_files, 0, auto_connected, new_files, updated_files, skipped_files

        from ui.workers import SFTPWorker
        worker = SFTPWorker(self.window.sftp, _backup_with_connect, progress_callback=True)
        worker.finished.connect(lambda result: self._on_done(backup_id, name, result))
        worker.error.connect(lambda err: self._on_error(backup_id, name, err))
        self.window._worker = worker
        logger.debug("worker 已创建, 信号已连接, 准备启动线程")

        if widgets:
            widgets["progress"].setVisible(True)
            widgets["progress"].setValue(0)
            widgets["status"].setVisible(True)
            widgets["status"].setText("定时备份中...")
            widgets["run_btn"].setEnabled(False)

            def _update_card(v, t):
                if widgets["progress"].isVisible():
                    pct = int(v / t * 100) if t > 0 else 0
                    widgets["progress"].setValue(pct)
                    widgets["status"].setText(f"{pct}%")

            worker.progress.connect(_update_card)

            def _cleanup_card():
                widgets["progress"].setVisible(False)
                widgets["status"].setVisible(False)
                widgets["run_btn"].setEnabled(True)

            worker.finished.connect(lambda _: _cleanup_card())
            worker.error.connect(lambda _: _cleanup_card())

        worker.start()
        logger.debug("worker.start() 已调用")

    def _on_done(self, backup_id: int, name: str, result: Any) -> None:
        logger.debug(f"_on_done: 备份 '{name}' (id={backup_id}) 完成")
        try:
            auto_connected = False
            new_files = updated_files = skipped_files = 0
            if isinstance(result, tuple):
                if len(result) == 7:
                    errors, file_count, total_bytes, auto_connected, new_files, updated_files, skipped_files = result
                else:
                    errors, file_count, total_bytes, auto_connected = result
            else:
                errors = result
                file_count = 0
                total_bytes = 0

            if auto_connected and self.window.sftp.connected:
                try:
                    self.window.sftp.abort()
                except Exception:
                    pass

            # Connection name
            conn_name = ""
            backups = load_backups()
            backup = None
            for b in backups:
                if b.get("id") == backup_id:
                    backup = b
                    break
            if backup:
                conn_id = backup.get("connection_id")
                if conn_id is not None:
                    for c in load_connections():
                        if c.get("id") == conn_id:
                            conn_name = c.get("name", "")
                            break

            status = "success" if not errors else "partial"
            add_backup_log({
                "backup_id": backup_id,
                "backup_name": name,
                "timestamp": datetime.now().isoformat(),
                "status": status,
                "file_count": file_count,
                "retry_count": 0,
                "errors": errors,
                "trigger": "scheduled",
                "backup_type": "template",
                "connection_name": conn_name,
                "duration_seconds": 0,
                "new_files": new_files,
                "updated_files": updated_files,
                "skipped_files": skipped_files,
            })
            self.window.status_label.setText(f"定时备份完成: {name}")
            update_backup(backup_id, {"_retry_count": 0})
            self._advance_next_run(backup_id, {})
            if not errors:
                backups = load_backups()
                for b in backups:
                    if b.get("id") == backup_id and b.get("auto_shutdown"):
                        self._do_shutdown()
                        break
        finally:
            self._running = False

    def _on_error(self, backup_id: int, name: str, err: Exception) -> None:
        logger.debug(f"_on_error: 备份 '{name}' (id={backup_id}) 失败: {err}")
        try:
            if self.window.sftp.connected:
                try:
                    self.window.sftp.abort()
                except Exception:
                    pass

            backups = load_backups()
            backup = None
            for b in backups:
                if b.get("id") == backup_id:
                    backup = b
                    break

            retry_count = (backup or {}).get("_retry_count", 0) + 1

            conn_name = ""
            if backup:
                conn_id = backup.get("connection_id")
                if conn_id is not None:
                    for c in load_connections():
                        if c.get("id") == conn_id:
                            conn_name = c.get("name", "")
                            break

            add_backup_log({
                "backup_id": backup_id,
                "backup_name": name,
                "timestamp": datetime.now().isoformat(),
                "status": "failed",
                "file_count": 0,
                "retry_count": retry_count,
                "errors": [str(err)],
                "trigger": "scheduled",
                "backup_type": "template",
                "connection_name": conn_name,
                "duration_seconds": 0,
            })

            update_backup(backup_id, {"_retry_count": retry_count})

            if retry_count >= MAX_RETRIES:
                logger.warning(f"已重试 {MAX_RETRIES} 次仍失败，放弃备份 '{name}'")
                self.window.status_label.setText(f"定时备份失败: {name}")
                self._advance_next_run(backup_id, {})
                update_backup(backup_id, {"_retry_count": 0})
                # 失败后也执行自动关机（如果开启了）
                if backup and backup.get("auto_shutdown"):
                    self._do_shutdown()
                # 托盘通知
                if hasattr(self.window, '_tray') and self.window._tray.isVisible():
                    from PySide6.QtWidgets import QSystemTrayIcon
                    self.window._tray.showMessage(
                        "拾云 - 备份失败",
                        f'模板 "{name}" 失败 {MAX_RETRIES} 次，已放弃。请检查服务器连接。',
                        QSystemTrayIcon.Critical, 8000
                    )
            else:
                logger.debug(f"备份 '{name}' 失败，{RETRY_DELAY_MS // 60000} 分钟后重试 ({retry_count}/{MAX_RETRIES})")
                self.window.status_label.setText(f"备份失败: {name}，{RETRY_DELAY_MS // 60000} 分钟后重试")
                # 托盘通知
                if hasattr(self.window, '_tray') and self.window._tray.isVisible():
                    from PySide6.QtWidgets import QSystemTrayIcon
                    self.window._tray.showMessage(
                        "拾云 - 备份重试",
                        f'模板 "{name}" 失败，{RETRY_DELAY_MS // 60000} 分钟后自动重试 ({retry_count}/{MAX_RETRIES})',
                        QSystemTrayIcon.Warning, 5000
                    )
                # 延迟重试
                QTimer.singleShot(RETRY_DELAY_MS, lambda bid=backup_id, n=name: self._retry_backup(bid, n))
        finally:
            self._running = False

    def _retry_backup(self, backup_id: int, name: str) -> None:
        """Execute a delayed retry for a failed backup."""
        backups = load_backups()
        backup = None
        for b in backups:
            if b.get("id") == backup_id:
                backup = b
                break
        if backup and backup.get("_retry_count", 0) < MAX_RETRIES:
            logger.debug(f"延迟重试备份 '{name}' (id={backup_id})")
            self._run_backup(backup)

    def _run_group(self, group: dict) -> None:
        """Execute all backups in a group sequentially."""
        self._running = True
        group_id = group.get("id")
        group_name = group.get("name", "未命名")
        backup_ids = group.get("backup_ids", [])
        logger.debug(f"_run_group: 开始执行备份组 '{group_name}' ({len(backup_ids)} 个模板)")

        backups = load_backups()
        backups_map = {b.get("id"): b for b in backups}
        queue = [backups_map[bid] for bid in backup_ids if bid in backups_map]
        group_errors = []

        def _run_next():
            if not queue:
                # All done — aggregate member errors into group status
                status = "success" if not group_errors else "partial"
                add_backup_log({
                    "backup_id": group_id,
                    "backup_name": f"[组] {group_name}",
                    "timestamp": datetime.now().isoformat(),
                    "status": status,
                    "file_count": len(backup_ids),
                    "retry_count": 0,
                    "errors": group_errors,
                    "trigger": "scheduled",
                    "backup_type": "group",
                    "connection_name": "",
                    "duration_seconds": 0,
                })
                self._advance_group_next_run(group_id)
                self._running = False
                self.window.status_label.setText(f"备份组完成: {group_name}")
                if group.get("auto_shutdown"):
                    self._do_shutdown()
                return

            backup = queue.pop(0)
            bid = backup.get("id")
            name = backup.get("name", "未命名")
            logger.debug(f"  执行模板 '{name}' (id={bid})")

            # Use the existing _run_backup but chain to next on done
            backup_id = bid

            def _on_group_backup_done(result):
                try:
                    if isinstance(result, tuple):
                        errors = result[0]
                    else:
                        errors = result
                    if errors:
                        err_list = errors if isinstance(errors, list) else [str(errors)]
                        group_errors.extend([f"[{name}] {e}" for e in err_list])
                        add_backup_log({
                            "backup_id": backup_id,
                            "backup_name": name,
                            "timestamp": datetime.now().isoformat(),
                            "status": "partial",
                            "file_count": 0,
                            "retry_count": 0,
                            "errors": err_list,
                            "trigger": "scheduled",
                        })
                except Exception as e:
                    logger.error(f"_on_group_backup_done 异常: {e}")
                finally:
                    self._running = False
                    _run_next()

            from ui.workers import SFTPWorker
            remote_paths = backup.get("remote_paths", [])
            if not remote_paths and backup.get("remote_path"):
                remote_paths = [backup["remote_path"]]
            local_path = backup.get("local_path", "")
            conn = self._find_connection(backup)

            def _backup_with_connect(progress_callback=None):
                auto_connected = False
                if not self.window.sftp.connected and conn:
                    self.window.sftp.connect(
                        host=conn["host"], port=conn["port"],
                        username=conn["username"], password=conn.get("password", "")
                    )
                    auto_connected = True

                from core.settings_manager import SettingsManager
                max_workers = SettingsManager.instance().get("download_concurrency", 3)
                import os
                import stat as _stat
                base_dir = os.path.abspath(local_path)
                os.makedirs(base_dir, exist_ok=True)

                files_to_download = []
                for rpath in remote_paths:
                    rpath = rpath.replace("\\", "/").rstrip("/") or "/"
                    parts = [p for p in rpath.split("/") if p]
                    item_name = parts[-1] if parts else "root"
                    local_dest = os.path.join(base_dir, item_name)
                    try:
                        st = self.window.sftp.stat(rpath)
                        if _stat.S_ISDIR(st.st_mode):
                            self.window.sftp._collect_files_for_backup(
                                rpath, local_dest, files_to_download)
                        else:
                            files_to_download.append((rpath, local_dest))
                    except Exception as e:
                        return [f"{rpath}: {e}"], 0, 0, auto_connected, 0, 0, 0

                def _file_progress(name, transferred, total_bytes):
                    if progress_callback:
                        progress_callback(transferred, total_bytes)

                errors = self.window.sftp.download_parallel(
                    files_to_download,
                    file_progress=_file_progress,
                    max_workers=max_workers,
                )
                completed_files = len(files_to_download) - len(errors)

                if errors:
                    return errors, completed_files, 0, auto_connected, 0, 0, 0

                verify_errors = []
                for rpath in remote_paths:
                    rpath = rpath.replace("\\", "/").rstrip("/") or "/"
                    parts = [p for p in rpath.split("/") if p]
                    item_name = parts[-1] if parts else "root"
                    local_dest = os.path.join(base_dir, item_name)
                    verify_errors.extend(self.window.sftp.verify_download(rpath, local_dest))

                if not verify_errors:
                    return [], completed_files, 0, auto_connected, 0, 0, 0

                errors = [f"验证失败: {e}" for e in verify_errors]
                return errors, completed_files, 0, auto_connected, 0, 0, 0

            worker = SFTPWorker(self.window.sftp, _backup_with_connect, progress_callback=True)
            worker.finished.connect(_on_group_backup_done)
            worker.error.connect(lambda err: (_on_group_backup_done([str(err)])))
            self.window._worker = worker

            widgets = self.window._backup_widgets.get(bid)
            if widgets:
                widgets["progress"].setVisible(True)
                widgets["progress"].setValue(0)
                widgets["status"].setVisible(True)
                widgets["status"].setText(f"组执行中...")
                widgets["run_btn"].setEnabled(False)

                def _update_card(v, t, w=widgets):
                    if w["progress"].isVisible():
                        pct = int(v / t * 100) if t > 0 else 0
                        w["progress"].setValue(pct)
                        w["status"].setText(f"{pct}%")

                worker.progress.connect(_update_card)

                def _cleanup_card(w=widgets):
                    w["progress"].setVisible(False)
                    w["status"].setVisible(False)
                    w["run_btn"].setEnabled(True)

                worker.finished.connect(lambda _: _cleanup_card())
                worker.error.connect(lambda _: _cleanup_card())

            worker.start()

        self._running = True
        _run_next()

    def _advance_group_next_run(self, group_id: int) -> None:
        """Advance the next run time for a backup group."""
        groups = load_backup_groups()
        group = None
        for g in groups:
            if g.get("id") == group_id:
                group = g
                break
        if not group:
            return

        rule = group.get("schedule_rule")
        if not rule:
            return

        cron_expr = self._build_cron(rule)
        try:
            cron = croniter(cron_expr, datetime.now())
            next_dt = cron.get_next(datetime)
        except Exception:
            update_backup_group(group_id, {"next_run": None, "schedule_enabled": False})
            return

        end_type = rule.get("end_type", "never")
        if end_type == "date":
            end_date = rule.get("end_date", "")
            if end_date:
                time_str = rule.get("time", "01:00")
                h, m = time_str.split(":")
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                end_dt = end_dt.replace(hour=int(h), minute=int(m))
                if next_dt > end_dt:
                    update_backup_group(group_id, {"next_run": None, "schedule_enabled": False})
                    return

        if end_type == "count":
            run_count = group.get("_run_count", 0) + 1
            max_count = rule.get("end_count", 0)
            update_data = {"_run_count": run_count}
            if run_count >= max_count:
                update_data["next_run"] = None
                update_data["schedule_enabled"] = False
            else:
                update_data["next_run"] = next_dt.isoformat()
            update_backup_group(group_id, update_data)
            return

        update_backup_group(group_id, {"next_run": next_dt.isoformat()})

    @staticmethod
    def _do_shutdown() -> None:
        import subprocess
        subprocess.Popen(["shutdown", "/s", "/t", "60", "/c", "拾云备份完成，即将关机"])
