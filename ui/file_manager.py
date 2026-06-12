import datetime
import os
import tempfile
import subprocess
import threading

from PySide6.QtCore import Qt, QTimer, QPoint, QObject, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QTableWidgetItem
from typing import Callable

from ui.style import COLORS, menu_stylesheet
from ui.message_dialog import show_message, ask_question
from ui.rename_dialog import RenameDialog
from ui.progress_dialog import ProgressDialog
from ui.workers import SFTPWorker


class _ErrorBridge(QObject):
    """Bridge for showing error dialogs from worker threads."""
    ask = Signal(str, str)


class FileManager:
    def __init__(self, window: "MainWindow") -> None:
        self.window = window
        self.sftp = window.sftp
        self.current_remote_path = "/"
        self._upload_queue = []
        self._upload_index = 0
        self._editing_remote_path = None
        self._error_bridge = _ErrorBridge()
        self._error_bridge.ask.connect(self._show_error_dialog)
        self._error_event = threading.Event()
        self._error_result = None
        self._editing_local_file = None
        self._editing_name = None
        self._files = []
        self._rows = []
        self._show_hidden = True

    def refresh_files(self, remote_path: str | None = None) -> None:
        if remote_path is not None:
            self.current_remote_path = remote_path
        if not self.sftp.connected:
            return

        self.window.status_label.setText("加载中…")

        worker = SFTPWorker(self.sftp, self.sftp.list_dir, self.current_remote_path)
        worker.finished.connect(self._on_files_loaded)
        worker.error.connect(self._on_files_error)
        self.window._worker = worker
        worker.start()

    def _on_files_loaded(self, files: list) -> None:
        self.window.path_label.setText(self.current_remote_path)
        self._files = list(files)

        table = self.window.file_table
        table.setRowCount(0)

        rows = []
        if self.current_remote_path != "/":
            rows.append({
                "name": "..",
                "is_dir": True,
                "size": "",
                "mtime": "",
                "path": "/".join(self.current_remote_path.rstrip("/").split("/")[:-1]) or "/",
            })

        for f in files:
            if f.name in (".", ".."):
                continue
            if not self._show_hidden and f.name.startswith("."):
                continue
            full_path = f"{self.current_remote_path.rstrip('/')}/{f.name}"
            size_str = self._format_size(f.size) if not f.is_dir else ""
            mtime_str = self._format_time(f.mtime) if f.mtime else ""
            rows.append({
                "name": f.name,
                "is_dir": f.is_dir,
                "size": size_str,
                "mtime": mtime_str,
                "path": full_path,
            })

        self._rows = rows
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            icon = "📁" if row["is_dir"] else "📄"
            name_item = QTableWidgetItem(f"{icon}  {row['name']}")
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(i, 0, name_item)

            size_item = QTableWidgetItem(row["size"])
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            size_item.setForeground(QColor(COLORS['text_sec']))
            size_item.setFlags(size_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(i, 1, size_item)

            mtime_item = QTableWidgetItem(row["mtime"])
            mtime_item.setForeground(QColor(COLORS['text_hint']))
            mtime_item.setFlags(mtime_item.flags() & ~Qt.ItemIsEditable)
            table.setItem(i, 2, mtime_item)

        item_count = len(rows) - (1 if self.current_remote_path != "/" else 0)
        self.window.status_label.setText(f"{self.current_remote_path}  |  {item_count} 个项目")

    def _on_files_error(self, err: str) -> None:
        self.window.status_label.setText("读取失败")
        if "Garbage packet" in str(err) or "Connection" in str(err) or "EOF" in str(err):
            self.window.conn_manager.try_reconnect()
        else:
            show_message(self.window, "错误", f"无法读取目录:\n{err}", "warning")

    def _get_selected_rows(self) -> list[dict]:
        table = self.window.file_table
        selected = table.selectionModel().selectedRows()
        rows = []
        for idx in selected:
            row = idx.row()
            if 0 <= row < len(self._rows):
                rows.append(self._rows[row])
        return rows

    def _on_table_double_click(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if row < 0 or row >= len(self._rows):
            return
        r = self._rows[row]
        if r["is_dir"]:
            if r["name"] == "..":
                self._go_parent()
            else:
                self.current_remote_path = r["path"]
                self.refresh_files()
        else:
            self._on_edit_remote(r["name"])

    def _on_table_context_menu(self, pos: QPoint) -> None:
        selected = self._get_selected_rows()

        table = self.window.file_table
        global_pos = table.viewport().mapToGlobal(pos)

        from PySide6.QtWidgets import QMenu
        menu = QMenu(self.window)
        menu.setStyleSheet(menu_stylesheet("""
            QMenu::item:disabled { color: """ + COLORS['text_hint'] + """; }
            QMenu::separator { height: 1px; background: """ + COLORS['border'] + """; margin: 4px 8px; }
        """))

        new_menu = menu.addMenu("新建")
        new_file_action = new_menu.addAction("文件")
        new_folder_action = new_menu.addAction("文件夹")

        if not selected:
            menu.addSeparator()
            toggle_text = "隐藏隐藏文件" if self._show_hidden else "显示隐藏文件"
            toggle_action = menu.addAction(toggle_text)
            action = menu.exec(global_pos)
            if action == new_file_action:
                self._on_create_file()
            elif action == new_folder_action:
                self._on_create_folder()
            elif action == toggle_action:
                self._show_hidden = not self._show_hidden
                self.refresh_files()
            return

        single = len(selected) == 1
        only_dirs = all(r["is_dir"] for r in selected)
        only_files = all(not r["is_dir"] for r in selected)
        has_files = any(not r["is_dir"] for r in selected)

        if single:
            if selected[0]["is_dir"]:
                open_action = menu.addAction("打开")
            else:
                open_action = menu.addAction("编辑")
                menu.addSeparator()
        else:
            open_action = None

        download_action = menu.addAction("下载")

        menu.addSeparator()
        rename_action = menu.addAction("重命名")
        if not single:
            rename_action.setEnabled(False)

        delete_action = menu.addAction("删除")

        menu.addSeparator()
        toggle_text = "隐藏隐藏文件" if self._show_hidden else "显示隐藏文件"
        toggle_action = menu.addAction(toggle_text)

        action = menu.exec(global_pos)
        if action is None:
            return

        if single and action == open_action:
            r = selected[0]
            if r["is_dir"]:
                if r["name"] == "..":
                    self._go_parent()
                else:
                    self.current_remote_path = r["path"]
                    self.refresh_files()
            else:
                self._on_edit_remote(r["name"])
        elif action == download_action:
            self._on_download_multi(selected)
        elif action == rename_action and single:
            self._on_rename(selected[0]["name"])
        elif action == delete_action:
            self._on_delete_multi(selected)
        elif action == new_file_action:
            self._on_create_file()
        elif action == new_folder_action:
            self._on_create_folder()
        elif action == toggle_action:
            self._show_hidden = not self._show_hidden
            self.refresh_files()
        elif action == toggle_action:
            self._show_hidden = not self._show_hidden
            self.refresh_files()

    def _go_parent(self) -> None:
        parent = "/".join(self.current_remote_path.rstrip("/").split("/")[:-1]) or "/"
        self.current_remote_path = parent
        self.refresh_files()

    def _on_download_multi(self, items: list[dict]) -> None:
        if not items:
            return
        local_dir = QFileDialog.getExistingDirectory(self.window, "选择保存位置")
        if not local_dir:
            return
        self._download_items(items, local_dir)

    def _download_items(self, items: list[dict], local_dir: str, progress: "ProgressDialog | None" = None, on_done: "Callable | None" = None) -> None:
        if not items:
            return
        if progress is None:
            progress = ProgressDialog(self.window, title="下载中",
                message=f"正在下载 {len(items)} 个项目…")
            progress.cancelled.connect(lambda: self._cancel_worker(progress))

        # Phase 1: collect all files recursively
        files_to_download: list[tuple[str, str]] = []
        for item in items:
            dst = os.path.join(local_dir, item["name"])
            if item["is_dir"]:
                self._collect_files(item["path"], dst, files_to_download)
            else:
                files_to_download.append((item["path"], dst))

        total_files = len(files_to_download) or 1
        from core.settings_manager import SettingsManager
        max_workers = SettingsManager.instance().get("download_concurrency", 3)

        done_count = [0]

        def _on_progress(_done, _total):
            done_count[0] = _done
            progress.update_progress(_done, total_files)

        def _on_file_progress(name, transferred, total_bytes):
            pct = int(transferred / total_bytes * 100) if total_bytes > 0 else 0
            progress.update_progress(done_count[0], total_files, file_pct=pct)

        def _on_download_error(error, file_path):
            self._error_event.clear()
            self._error_result = None
            self._error_bridge.ask.emit(str(error), file_path)
            self._error_event.wait()
            result = self._error_result or "abort"
            if result == "abort":
                self.sftp._aborted = True
            return result

        def _do_download():
            return self.sftp.download_parallel(
                files_to_download,
                progress_callback=_on_progress,
                file_progress=_on_file_progress,
                on_error=_on_download_error,
                max_workers=max_workers,
            )

        worker = SFTPWorker(self.sftp, _do_download)
        worker.finished.connect(lambda errs: self._on_items_downloaded(errs, progress, on_done))
        worker.error.connect(lambda err: self._on_op_progress_error("下载", err, progress))
        self.window._worker = worker
        worker.start()
        progress.show_centered(self.window)

    def _on_items_downloaded(self, errors: list[str], progress: "ProgressDialog", on_done: "Callable | None" = None) -> None:
        if progress.isVisible():
            if errors:
                total = len(errors)
                shown = errors[:10]
                msg = f"下载完成，但 {total} 个文件失败:\n" + "\n".join(shown)
                if total > 10:
                    msg += f"\n...还有 {total - 10} 个错误"
                progress.set_error(msg)
            else:
                progress.set_complete("下载完成")
        if on_done:
            on_done(errors)

    def _on_op_progress_error(self, op_name: str, err: str, progress: "ProgressDialog") -> None:
        if progress.isVisible():
            progress.set_error(f"{op_name}失败: {err}")
        err_str = str(err)
        if "Garbage packet" in err_str or "Connection" in err_str or "EOF" in err_str:
            self.window.conn_manager.try_reconnect()

    def _show_error_dialog(self, error_msg: str, file_path: str) -> None:
        from ui.error_dialog import show_error
        details = error_msg
        try:
            if hasattr(error_msg, 'winerror'):
                details = f"系统错误 代码: {error_msg.winerror}\n{error_msg}"
        except Exception:
            pass
        action = show_error(
            self.window, title="下载失败",
            message="无法下载文件",
            details=details,
            file_path=file_path,
            show_skip_all=True
        )
        self._error_result = action
        self._error_event.set()

    def _collect_files(self, remote_path: str, local_path: str,
                       result: list[tuple[str, str]]) -> None:
        """Recursively collect remote files into (remote, local) pairs."""
        import stat
        with self.sftp._lock:
            if not self.sftp._connected or not self.sftp._sftp:
                return
            try:
                os.makedirs(local_path, exist_ok=True)
                for attr in self.sftp._sftp.listdir_attr(remote_path):
                    name = attr.filename
                    if name in (".", ".."):
                        continue
                    remote_item = f"{remote_path.rstrip('/')}/{name}"
                    local_item = os.path.join(local_path, name)
                    if stat.S_ISDIR(attr.st_mode):
                        self._collect_files(remote_item, local_item, result)
                    else:
                        result.append((remote_item, local_item))
            except Exception:
                pass

    def _cancel_worker(self, progress: "ProgressDialog | None" = None) -> None:
        worker = self.window._worker
        if not worker or not worker.isRunning():
            if progress:
                progress.reject()
            return

        worker.cancel()

        if progress:
            progress.cancel_btn.setEnabled(False)
            progress.cancel_btn.setText("取消中…")
            progress.msg_label.setText("正在取消…")

            _cleaned = [False]

            def _cleanup():
                if _cleaned[0]:
                    return
                _cleaned[0] = True
                if progress.isVisible():
                    progress.hide()
                for sig_name in ('finished', 'error', 'progress', 'error_ask'):
                    try:
                        sig = getattr(worker, sig_name, None)
                        if sig:
                            sig.disconnect()
                    except (RuntimeError, AttributeError):
                        pass
                self.window._worker = None
                self.window.status_label.setText("已取消")
                QTimer.singleShot(300, lambda: self._reconnect_after_abort())

            def _check_done():
                if not worker.isRunning():
                    _cleanup()
                else:
                    _cleanup()

            QTimer.singleShot(1000, _check_done)
            timer = QTimer(progress)
            timer.setSingleShot(True)
            timer.timeout.connect(_cleanup)
            timer.start(3000)
            progress._force_timer = timer

    def _reconnect_after_abort(self) -> None:
        if self.sftp.connected:
            return
        if self.window.conn_manager.try_reconnect():
            return
        self.window.content_stack.setCurrentIndex(0)
        self.window.conn_manager.refresh_connections()

    def _on_upload(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self.window, "选择要上传的文件")
        if not files:
            return
        self._upload_queue = files
        self._upload_index = 0

        progress = ProgressDialog(self.window, title="上传中", message=f"正在上传: {os.path.basename(files[0])}")
        progress.cancelled.connect(lambda: self._cancel_worker(progress))
        self._progress = progress
        progress.show_centered(self.window)
        self._start_next_upload()

    def _start_next_upload(self) -> None:
        if not self._progress or not self._progress.isVisible():
            return
        if self._upload_index >= len(self._upload_queue):
            self._progress.set_complete(f"已上传 {len(self._upload_queue)} 个文件")
            self.refresh_files()
            return
        local_file = self._upload_queue[self._upload_index]
        name = os.path.basename(local_file)
        remote_path = f"{self.current_remote_path.rstrip('/')}/{name}"
        self._progress.msg_label.setText(f"正在上传 ({self._upload_index + 1}/{len(self._upload_queue)}): {name}")

        _skip_all = [False]

        def _on_error_ask(error_msg, file_path):
            worker = self.window._worker
            if not worker or worker._cancelled.is_set():
                return
            from ui.error_dialog import show_error
            details = str(error_msg)
            try:
                if hasattr(error_msg, 'winerror'):
                    details = f"系统错误 代码: {error_msg.winerror}\n{error_msg}"
            except Exception:
                pass
            action = show_error(
                self.window, title="上传失败",
                message="无法上传文件",
                details=details,
                file_path=file_path,
                show_skip_all=not _skip_all[0]
            )
            if worker and not worker._cancelled.is_set():
                if action == "skip_all":
                    _skip_all[0] = True
                worker.set_error_decision(action)

        def _on_upload_error(error, file_path):
            if _skip_all[0]:
                return "skip_all"
            worker = self.window._worker
            if worker and not worker._cancelled.is_set():
                return worker.ask_user_decision(str(error), file_path)
            return "abort"

        worker = SFTPWorker(
            self.sftp, self.sftp.upload_file,
            local_path=local_file, remote_path=remote_path,
            progress_callback=True,
            on_error=_on_upload_error
        )
        worker.progress.connect(lambda v, t: self._progress.update_progress(v, t, f"上传中: {name}"))
        worker.finished.connect(lambda _: self._on_single_upload_done())
        worker.error.connect(lambda err: self._on_op_progress_error("上传", err, self._progress))
        worker.error_ask.connect(_on_error_ask)
        self.window._worker = worker
        worker.start()

    def _on_single_upload_done(self) -> None:
        if not self._progress or not self._progress.isVisible():
            return
        self._upload_index += 1
        self._start_next_upload()

    def _on_delete_multi(self, items: list[dict]) -> None:
        if not items:
            return
        names = [r["name"] for r in items]
        if len(items) == 1:
            msg = f"确定要删除 \"{names[0]}\" 吗？\n此操作不可撤销。"
        else:
            msg = f"确定要删除 {len(items)} 个项目吗？\n{', '.join(names[:5])}{'…' if len(names) > 5 else ''}\n此操作不可撤销。"
        reply = ask_question(self.window, "确认删除", msg)
        if not reply:
            return

        progress = ProgressDialog(self.window, title="删除中",
            message=f"正在删除 {len(items)} 个项目…")
        progress.cancelled.connect(lambda: self._cancel_worker(progress))

        def _do_delete():
            errors = []
            for r in items:
                try:
                    self.sftp.delete(r["path"])
                except Exception as e:
                    errors.append(f"{r['name']}: {e}")
            return errors

        worker = SFTPWorker(self.sftp, _do_delete)
        worker.finished.connect(lambda errs: self._on_delete_done(errs, progress))
        worker.error.connect(lambda err: self._on_op_progress_error("删除", err, progress))
        self.window._worker = worker
        worker.start()
        progress.show_centered(self.window)

    def _on_delete_done(self, errors: list[str], progress: "ProgressDialog") -> None:
        if errors:
            progress.set_error(f"部分删除失败:\n" + "\n".join(errors[:5]))
        else:
            progress.set_complete("删除完成")
        self.refresh_files()

    def _on_rename(self, name: str) -> None:
        dialog = RenameDialog(self.window, current_name=name)
        if dialog.exec() and dialog.result_name and dialog.result_name != name:
            new_name = dialog.result_name
            old_path = f"{self.current_remote_path.rstrip('/')}/{name}"
            new_path = f"{self.current_remote_path.rstrip('/')}/{new_name}"
            worker = SFTPWorker(self.sftp, self.sftp.rename, old_path, new_path)
            worker.finished.connect(lambda _: self.refresh_files())
            worker.error.connect(lambda err: self.window.conn_manager.handle_op_error("重命名", err))
            self.window._worker = worker
            worker.start()

    def _on_create_file(self) -> None:
        dialog = RenameDialog(self.window, current_name="新建文件.txt", title="新建文件")
        if dialog.exec() and dialog.result_name:
            name = dialog.result_name
            path = f"{self.current_remote_path.rstrip('/')}/{name}"
            worker = SFTPWorker(self.sftp, self.sftp.write_file, path, "")
            worker.finished.connect(lambda _: self.refresh_files())
            worker.error.connect(lambda err: self.window.conn_manager.handle_op_error("创建文件", err))
            self.window._worker = worker
            worker.start()

    def _on_create_folder(self) -> None:
        dialog = RenameDialog(self.window, current_name="新建文件夹", title="新建文件夹")
        if dialog.exec() and dialog.result_name:
            name = dialog.result_name
            path = f"{self.current_remote_path.rstrip('/')}/{name}"
            worker = SFTPWorker(self.sftp, self.sftp.mkdir, path)
            worker.finished.connect(lambda _: self.refresh_files())
            worker.error.connect(lambda err: self.window.conn_manager.handle_op_error("创建文件夹", err))
            self.window._worker = worker
            worker.start()

    def _on_edit_remote(self, name: str) -> None:
        remote_path = f"{self.current_remote_path.rstrip('/')}/{name}"
        tmp_dir = tempfile.mkdtemp(prefix="shiyun_")
        local_file = os.path.join(tmp_dir, name)
        item = {"path": remote_path, "name": name, "is_dir": False}

        def _on_done(errors):
            if not errors:
                self._open_local_edit(remote_path, local_file, name)

        self._download_items([item], tmp_dir, on_done=_on_done)

    def _open_local_edit(self, remote_path: str, local_file: str, name: str) -> None:
        self.window.status_label.setText(f"正在用本地程序打开: {name}…")
        try:
            os.startfile(local_file)
        except Exception:
            try:
                subprocess.Popen(["xdg-open", local_file])
            except Exception:
                show_message(self.window, "打开失败", f"无法用默认程序打开:\n{local_file}", "warning")
                return

        self._editing_remote_path = remote_path
        self._editing_local_file = local_file
        self._editing_name = name
        self.window.save_back_btn.show()
        self.window.status_label.setText(f"已打开: {name}（编辑完成后点「保存回服务器」）")

    def save_back_to_server(self) -> None:
        if not self._editing_local_file:
            return
        if not os.path.exists(self._editing_local_file):
            show_message(self.window, "错误", "临时文件不存在，可能已被删除", "warning")
            return

        reply = ask_question(
            self.window, "保存回服务器",
            f"将修改后的 \"{self._editing_name}\" 保存回服务器？"
        )
        if not reply:
            return

        progress = ProgressDialog(self.window, title="上传中", message=f"正在上传: {self._editing_name}")
        progress.cancelled.connect(lambda: self._cancel_worker(progress))

        _skip_all = [False]

        def _on_error_ask(error_msg, file_path):
            worker = self.window._worker
            if not worker or worker._cancelled.is_set():
                return
            from ui.error_dialog import show_error
            details = str(error_msg)
            try:
                if hasattr(error_msg, 'winerror'):
                    details = f"系统错误 代码: {error_msg.winerror}\n{error_msg}"
            except Exception:
                pass
            action = show_error(
                self.window, title="上传失败",
                message="无法上传文件",
                details=details,
                file_path=file_path,
                show_skip_all=not _skip_all[0]
            )
            if worker and not worker._cancelled.is_set():
                if action == "skip_all":
                    _skip_all[0] = True
                worker.set_error_decision(action)

        def _on_save_error(error, file_path):
            if _skip_all[0]:
                return "skip_all"
            worker = self.window._worker
            if worker and not worker._cancelled.is_set():
                return worker.ask_user_decision(str(error), file_path)
            return "abort"

        worker = SFTPWorker(
            self.sftp, self.sftp.upload_file,
            local_path=self._editing_local_file,
            remote_path=self._editing_remote_path,
            progress_callback=True,
            on_error=_on_save_error
        )
        worker.progress.connect(lambda v, t: progress.update_progress(v, t, f"上传中: {self._editing_name}"))
        worker.finished.connect(lambda _: self._on_save_back_done(progress))
        worker.error.connect(lambda err: self._on_op_progress_error("上传", err, progress))
        worker.error_ask.connect(_on_error_ask)
        self.window._worker = worker
        worker.start()
        self._progress = progress
        progress.show_centered(self.window)

    def _on_save_back_done(self, progress: "ProgressDialog") -> None:
        progress.set_complete(f"已保存: {self._editing_name}")
        self.window.status_label.setText(f"已保存回服务器: {self._editing_name}")
        show_message(self.window, "成功", f"已保存回服务器: {self._editing_name}", "info")
        try:
            os.remove(self._editing_local_file)
            os.rmdir(os.path.dirname(self._editing_local_file))
        except Exception:
            pass
        self._editing_remote_path = None
        self._editing_local_file = None
        self._editing_name = None
        self.window.save_back_btn.hide()
        self.refresh_files()

    @staticmethod
    def _format_size(size: int | float) -> str:
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

    @staticmethod
    def _format_time(timestamp: float) -> str:
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")
