from core.config import load_connections, add_connection, update_connection, delete_connection
from ui.widgets import ConnectionCard
from ui.connection_dialog import ConnectionDialog
from ui.message_dialog import show_message, ask_question
from ui.workers import SFTPWorker


class ConnectionManager:
    def __init__(self, window: "MainWindow") -> None:
        self.window = window
        self.sftp = window.sftp
        self.current_conn_id: str | None = None
        self._last_conn: dict | None = None
        self._test_status: dict[str, bool] = {}  # conn_id -> success
        self._card_map: dict[str, "ConnectionCard"] = {}  # conn_id -> card widget
        self._test_bridge = None  # prevent GC of test bridge

    def refresh_connections(self) -> None:
        while self.window.conn_list_layout.count():
            item = self.window.conn_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._card_map.clear()
        connections = load_connections()
        for conn in connections:
            is_active = self.sftp.connected and self.current_conn_id == conn.get("id")
            card = ConnectionCard(conn, is_active)
            conn_id = conn.get("id")
            self._card_map[conn_id] = card
            # Restore existing test status
            if conn_id in self._test_status:
                ok = self._test_status[conn_id]
                card.set_test_status(ok, "正常" if ok else "失败")
            card.clicked.connect(lambda c=conn: self.on_connect(c))
            card.edit_requested.connect(lambda c=conn: self.on_edit_conn(c))
            card.delete_requested.connect(lambda c=conn: self.on_delete_conn(c))
            self.window.conn_list_layout.addWidget(card)

    def on_search(self, query: str) -> None:
        query = query.lower()
        while self.window.conn_list_layout.count():
            item = self.window.conn_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        connections = load_connections()
        for conn in connections:
            name = conn.get("name", "").lower()
            host = conn.get("host", "").lower()
            if query in name or query in host:
                is_active = self.sftp.connected and self.current_conn_id == conn.get("id")
                card = ConnectionCard(conn, is_active)
                card.clicked.connect(lambda c=conn: self.on_connect(c))
                card.edit_requested.connect(lambda c=conn: self.on_edit_conn(c))
                card.delete_requested.connect(lambda c=conn: self.on_delete_conn(c))
                self.window.conn_list_layout.addWidget(card)

    def on_add_connection(self) -> None:
        dialog = ConnectionDialog(self.window)
        if dialog.exec() and dialog.result_data:
            add_connection(dialog.result_data)
            self.refresh_connections()

    def on_edit_conn(self, conn: dict) -> None:
        dialog = ConnectionDialog(self.window, conn=conn)
        if dialog.exec() and dialog.result_data:
            update_connection(conn["id"], dialog.result_data)
            self.refresh_connections()

    def on_delete_conn(self, conn: dict) -> None:
        reply = ask_question(self.window, "确认", f"删除连接 \"{conn.get('name', '')}\"？")
        if reply:
            if self.current_conn_id == conn.get("id"):
                self.on_disconnect()
            delete_connection(conn["id"])
            self.refresh_connections()

    def on_connect(self, conn: dict) -> None:
        if self.sftp.connected and self.current_conn_id == conn.get("id"):
            self.window.content_stack.setCurrentIndex(1)
            return
        self.window.status_label.setText(f"正在连接 {conn['name']}…")

        worker = SFTPWorker(
            self.sftp, self.sftp.connect,
            host=conn["host"], port=conn["port"],
            username=conn["username"], password=conn.get("password", "")
        )
        worker.finished.connect(lambda _: self._on_connect_success(conn))
        worker.error.connect(lambda err: self._on_connect_error(conn, err))
        self.window._worker = worker
        worker.start()

    def _on_connect_success(self, conn: dict) -> None:
        conn_id = conn.get("id")
        self.current_conn_id = conn_id
        self._last_conn = conn
        self._test_status[conn_id] = True
        card = self._card_map.get(conn_id)
        if card:
            card.set_test_status(True, "正常")
        self.window.status_label.setText(f"已连接: {conn['name']}")
        self.window.content_stack.setCurrentIndex(1)
        self.window.file_manager.refresh_files(conn.get("remote_path", "/"))
        self.refresh_connections()

    def _on_connect_error(self, conn: dict, err: str) -> None:
        conn_id = conn.get("id")
        self._test_status[conn_id] = False
        card = self._card_map.get(conn_id)
        if card:
            card.set_test_status(False, "失败")
        self.window.status_label.setText("连接失败")
        show_message(self.window, "连接失败", f"无法连接到服务器:\n{err}", "error")

    def try_reconnect(self) -> bool:
        if not self._last_conn:
            return False
        self.sftp._connected = False
        self.sftp._sftp = None
        self.sftp._transport = None
        self.sftp._aborted = False
        self.window.status_label.setText("正在重连…")
        conn = self._last_conn
        worker = SFTPWorker(
            self.sftp, self.sftp.connect,
            host=conn["host"], port=conn["port"],
            username=conn["username"], password=conn.get("password", "")
        )
        worker.finished.connect(lambda _: self._on_reconnect_success())
        worker.error.connect(self._on_reconnect_error)
        self.window._worker = worker
        worker.start()
        return True

    def _on_reconnect_success(self) -> None:
        self.window.status_label.setText("已重新连接")
        self.window.file_manager.refresh_files()

    def _on_reconnect_error(self, err: str) -> None:
        self.window.status_label.setText("重连失败")
        show_message(self.window, "连接断开", f"无法重新连接到服务器:\n{err}\n请手动重新连接。", "error")
        self.current_conn_id = None
        self.window.content_stack.setCurrentIndex(0)
        self.refresh_connections()

    def on_disconnect(self) -> None:
        if self.window._worker and self.window._worker.isRunning():
            self.window._worker.wait(3000)
        if self.sftp.connected:
            self.sftp.disconnect()
        self.current_conn_id = None
        self.window.content_stack.setCurrentIndex(0)
        self.refresh_connections()

    def handle_op_error(self, op_name: str, err: Exception) -> None:
        err_str = str(err)
        if "Garbage packet" in err_str or "Connection" in err_str or "EOF" in err_str:
            self.window.status_label.setText(f"{op_name}失败，正在重连…")
            self.try_reconnect()
        else:
            show_message(self.window, f"{op_name}失败", err_str, "warning")

    def test_all_connections(self) -> None:
        """Test all server connections on startup with full SFTP test."""
        import logging
        import threading
        from PySide6.QtCore import Signal, QObject
        from core.sftp_client import SFTPClient

        _log = logging.getLogger("shiyun.conn_test")
        connections = load_connections()
        if not connections:
            return
        self._pending_tests = len(connections)
        _log.info(f"Testing {len(connections)} connections...")

        class _TestBridge(QObject):
            done = Signal(object, object, bool)

        self._test_bridge = _TestBridge()
        self._test_bridge.done.connect(self._on_test_done)

        def _test_one(conn):
            conn_id = conn.get("id")
            host = conn.get("host", "")
            port = conn.get("port", 22)
            username = conn.get("username", "")
            password = conn.get("password", "")
            test_client = SFTPClient()
            try:
                test_client.connect(host, port, username, password, timeout=5)
                test_client.disconnect()
                ok = True
            except Exception:
                ok = False
            _log.info(f"  SFTP test {'OK' if ok else 'FAIL'} for '{conn.get('name')}'")
            self._test_bridge.done.emit(conn_id, conn, ok)

        for conn in connections:
            conn_id = conn.get("id")
            if self.sftp.connected and self.current_conn_id == conn_id:
                self._test_status[conn_id] = True
                card = self._card_map.get(conn_id)
                if card:
                    card.set_test_status(True, "正常")
                self._pending_tests -= 1
                continue
            t = threading.Thread(target=_test_one, args=(conn,), daemon=True)
            t.start()

    def _on_test_done(self, conn_id, conn, success):
        import logging
        _log = logging.getLogger("shiyun.conn_test")
        try:
            self._test_status[conn_id] = success
            card = self._card_map.get(conn_id)
            if card:
                card.set_test_status(success, "正常" if success else "失败")
            self._pending_tests = getattr(self, '_pending_tests', 1) - 1
            _log.info(f"  Test {'OK' if success else 'FAIL'} for '{conn.get('name')}', remaining={self._pending_tests}")
            if self._pending_tests <= 0:
                self.window.status_label.setText("服务器检测完成")
        except Exception as e:
            _log.error(f"_on_test_done crashed: {e}", exc_info=True)
