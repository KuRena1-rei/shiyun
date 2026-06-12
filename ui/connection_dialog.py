import time
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QPaintEvent, QKeyEvent
from ui.style import COLORS, make_confirm_button, make_cancel_button
from ui.title_bar import DialogTitleBar
from ui.message_dialog import show_message
from ui.workers import SFTPWorker


class ConnectionDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, conn: dict | None = None) -> None:
        super().__init__(parent)
        self.conn = conn
        self.result_data = None
        self._test_worker = None
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(460, 370)
        self.setWindowModality(Qt.ApplicationModal)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(3, 3, 3, 3)
        root.setSpacing(0)

        title_text = "编辑连接" if self.conn else "新建连接"
        title_bar = DialogTitleBar(title_text)
        title_bar.close_clicked.connect(self.reject)
        root.addWidget(title_bar)

        content = QWidget()
        content.setObjectName("connDialogContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(0)

        lbl = QLabel("名称")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        layout.addWidget(lbl)
        self.name_entry = QLineEdit()
        self.name_entry.setPlaceholderText("给这个连接起个名字")
        self.name_entry.setFixedHeight(32)
        layout.addWidget(self.name_entry)
        layout.addSpacing(12)

        row1 = QHBoxLayout()
        row1.setSpacing(12)

        col1 = QVBoxLayout()
        col1.setSpacing(4)
        lbl = QLabel("地址")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']};")
        col1.addWidget(lbl)
        self.host_entry = QLineEdit()
        self.host_entry.setPlaceholderText("例: 192.168.1.100")
        self.host_entry.setFixedHeight(32)
        col1.addWidget(self.host_entry)

        col2 = QVBoxLayout()
        col2.setSpacing(4)
        lbl = QLabel("端口号")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']};")
        col2.addWidget(lbl)
        self.port_entry = QLineEdit()
        self.port_entry.setText("22")
        self.port_entry.setFixedHeight(32)
        self.port_entry.setMaximumWidth(100)
        col2.addWidget(self.port_entry)

        row1.addLayout(col1, 1)
        row1.addLayout(col2, 0)
        layout.addLayout(row1)
        layout.addSpacing(12)

        row2 = QHBoxLayout()
        row2.setSpacing(12)

        col3 = QVBoxLayout()
        col3.setSpacing(4)
        lbl = QLabel("用户名")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']};")
        col3.addWidget(lbl)
        self.username_entry = QLineEdit()
        self.username_entry.setPlaceholderText("SSH 用户名")
        self.username_entry.setFixedHeight(32)
        col3.addWidget(self.username_entry)

        col4 = QVBoxLayout()
        col4.setSpacing(4)
        lbl = QLabel("密码")
        lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_sec']};")
        col4.addWidget(lbl)
        self.password_entry = QLineEdit()
        self.password_entry.setEchoMode(QLineEdit.Password)
        self.password_entry.setPlaceholderText("SSH 密码")
        self.password_entry.setFixedHeight(32)
        col4.addWidget(self.password_entry)

        row2.addLayout(col3, 1)
        row2.addLayout(col4, 1)
        layout.addLayout(row2)

        layout.addStretch()

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._test_btn = QPushButton("测试连接")
        self._test_btn.setFixedHeight(32)
        self._test_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
            f"color: {COLORS['text']}; border-radius: 6px; padding: 4px 12px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; border-color: {COLORS['mint']}; }}"
        )
        self._test_btn.clicked.connect(self._on_test_connection)
        btn_layout.addWidget(self._test_btn)

        cancel_btn = make_cancel_button("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = make_confirm_button("登录")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

        self._test_result = QLabel("")
        self._test_result.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']}; margin-top: 4px;")
        self._test_result.setVisible(False)
        layout.addWidget(self._test_result)

        root.addWidget(content, 1)

        if self.conn:
            self._fill_data()

    def _fill_data(self) -> None:
        self.name_entry.setText(self.conn.get("name", ""))
        self.host_entry.setText(self.conn.get("host", ""))
        self.port_entry.setText(str(self.conn.get("port", 22)))
        self.username_entry.setText(self.conn.get("username", ""))
        self.password_entry.setText(self.conn.get("password", ""))

    def _on_save(self) -> None:
        name = self.name_entry.text().strip()
        host = self.host_entry.text().strip()
        username = self.username_entry.text().strip()
        password = self.password_entry.text()

        if not name or not host or not username:
            show_message(self, "提示", "请填写名称、地址和用户名", "warning")
            return

        try:
            port = int(self.port_entry.text().strip())
        except ValueError:
            port = 22

        self.result_data = {
            "name": name, "host": host, "port": port,
            "username": username, "password": password,
            "remote_path": "/",
        }
        self.accept()

    def _on_test_connection(self) -> None:
        host = self.host_entry.text().strip()
        username = self.username_entry.text().strip()
        password = self.password_entry.text()
        try:
            port = int(self.port_entry.text().strip())
        except ValueError:
            port = 22

        if not host or not username:
            show_message(self, "提示", "请填写地址和用户名", "warning")
            return

        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中...")
        self._test_result.setVisible(True)
        self._test_result.setText("连接中...")
        self._test_result.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']}; margin-top: 4px;")
        self.setCursor(Qt.WaitCursor)

        from core.sftp_client import SFTPClient
        temp_sftp = SFTPClient()

        def _do_test():
            t0 = time.time()
            temp_sftp.connect(host=host, port=port, username=username, password=password)
            elapsed = time.time() - t0
            temp_sftp.disconnect()
            return elapsed

        def _on_success(elapsed):
            self.setCursor(Qt.ArrowCursor)
            self._test_btn.setEnabled(True)
            self._test_btn.setText("测试连接")
            ms = int(elapsed * 1000)
            self._test_result.setText(f"✓ 连接成功 ({ms}ms)")
            self._test_result.setStyleSheet(f"font-size: 11px; color: {COLORS['mint']}; margin-top: 4px;")

        def _on_error(err):
            self.setCursor(Qt.ArrowCursor)
            self._test_btn.setEnabled(True)
            self._test_btn.setText("测试连接")
            self._test_result.setText(f"✗ 连接失败: {err}")
            self._test_result.setStyleSheet(f"font-size: 11px; color: {COLORS['danger']}; margin-top: 4px;")

        self._test_worker = SFTPWorker(temp_sftp, _do_test)
        self._test_worker.finished.connect(_on_success)
        self._test_worker.error.connect(_on_error)
        self._test_worker.start()

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

    def done(self, result: int) -> None:
        if self._test_worker and self._test_worker.isRunning():
            self._test_worker.wait(2000)
        super().done(result)
