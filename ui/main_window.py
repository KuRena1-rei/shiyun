import logging
import sys
import ctypes
import ctypes.wintypes

logger = logging.getLogger("shiyun.main_window")

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QMenu,
    QHeaderView, QAbstractItemView, QStyledItemDelegate, QStyle,
    QSystemTrayIcon, QApplication
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QCursor, QPainter, QColor, QPen, QIcon, QPixmap

from ui.style import COLORS
from ui.title_bar import TitleBar
from ui.widgets import WelcomeIcon
from ui.message_dialog import show_message
from core.sftp_client import SFTPClient
from core.scheduler import BackupScheduler
from ui.log_dialog import LogDialog
from ui.connection_manager import ConnectionManager
from ui.file_table import FileExplorerTable
from ui.file_manager import FileManager
from core.settings_manager import SettingsManager
from ui.backup_manager import BackupManager
from ui.group_manager import GroupManager


# Windows API constants
if sys.platform == "win32":
    GWL_STYLE = -16
    WS_THICKFRAME = 0x00040000
    WM_NCCALCSIZE = 0x0083
    WM_NCHITTEST = 0x0084
    HTCLIENT = 1
    HTTOPLEFT = 13
    HTTOPRIGHT = 14
    HTBOTTOMLEFT = 16
    HTBOTTOMRIGHT = 17
    HTLEFT = 10
    HTRIGHT = 11
    HTTOP = 12
    HTBOTTOM = 15
    WM_QUERYENDSESSION = 0x0011


class MainWindow(QMainWindow):
    def __init__(self, startup_mode=False):
        super().__init__()
        self.setWindowFlags(Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("拾云")
        self.setGeometry(100, 100, 1000, 680)
        self.setMinimumSize(800, 500)

        self.sftp = SFTPClient()
        self._worker = None
        self._startup_mode = startup_mode
        self.setMouseTracking(True)
        self._mgr = SettingsManager.instance()
        self._mgr.setting_changed.connect(self._on_settings_changed)

        self.conn_manager = ConnectionManager(self)
        self.file_manager = FileManager(self)
        self.backup_manager = BackupManager(self)
        self.group_manager = GroupManager(self)

        self._build_ui()
        self.file_table._file_manager = self.file_manager
        self.file_table.itemDoubleClicked.connect(self.file_manager._on_table_double_click)
        self.file_table.customContextMenuRequested.connect(self.file_manager._on_table_context_menu)

        self.conn_manager.refresh_connections()
        self.backup_manager.refresh()

        # Auto-test all server connections on startup
        QTimer.singleShot(1000, self.conn_manager.test_all_connections)

        self.scheduler = BackupScheduler(self)

        if sys.platform == "win32":
            self._setup_native_resize()

        if startup_mode:
            self.hide()

        QTimer.singleShot(500, self._setup_tray)

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(QApplication.instance())

        # 生成薄荷绿托盘图标
        import os, sys
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "icon.ico")
        else:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            icon.addFile(icon_path, QSize(64, 64))
            self._tray.setIcon(icon)
        else:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor(0, 0, 0, 0))
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(COLORS['mint']))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
            painter.setPen(QPen(QColor("white"), 4))
            font = painter.font()
            font.setPixelSize(32)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "Y")
            painter.end()
            self._tray.setIcon(QIcon(pixmap))
        self._tray.setToolTip("拾云 - SFTP 备份工具")

        tray_menu = QMenu()
        show_action = tray_menu.addAction("显示主窗口")
        show_action.triggered.connect(self._tray_show)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("退出")
        quit_action.triggered.connect(self._tray_quit)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()
        print(f"[Tray] tray icon created, visible={self._tray.isVisible()}")

        # Check for upcoming backups and show dialog
        from core.config import has_upcoming_backup
        if self._mgr.get("startup_backup_reminder", True) and has_upcoming_backup(hours=12):
            self._tray.showMessage(
                "拾云 - 备份提醒", "未来 12 小时内有备份任务即将执行，请保持电脑开机",
                QSystemTrayIcon.Information, 5000
            )

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._tray_show()

    def _tray_show(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _tray_quit(self):
        self._real_quit()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(3, 3, 3, 3)
        root_layout.setSpacing(0)

        self.title_bar = TitleBar()
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.maximize_clicked.connect(self._toggle_maximize)
        self.title_bar.close_clicked.connect(self.close)
        root_layout.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(280)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 12, 16, 12)
        sidebar_layout.setSpacing(8)

        sidebar_title = QLabel("拾云")
        sidebar_title.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {COLORS['mint']}; cursor: pointer;")
        sidebar_title.mousePressEvent = lambda _: self.content_stack.setCurrentIndex(0)
        sidebar_layout.addWidget(sidebar_title)

        subtitle = QLabel("SFTP 管理器 & 备份工具")
        subtitle.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']};")
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(4)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索连接…")
        sidebar_layout.addWidget(self.search_input)

        new_btn = QPushButton("+ 新建连接")
        new_btn.setObjectName("newConnBtn")
        new_btn.setFixedHeight(36)
        new_btn.clicked.connect(lambda: self.conn_manager.on_add_connection())
        sidebar_layout.addWidget(new_btn)

        conn_scroll = QScrollArea()
        conn_scroll.setWidgetResizable(True)
        conn_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conn_scroll.setFrameShape(QFrame.NoFrame)
        self.conn_container = QWidget()
        self.conn_list_layout = QVBoxLayout(self.conn_container)
        self.conn_list_layout.setAlignment(Qt.AlignTop)
        self.conn_list_layout.setContentsMargins(4, 8, 4, 8)
        self.conn_list_layout.setSpacing(6)
        conn_scroll.setWidget(self.conn_container)
        sidebar_layout.addWidget(conn_scroll, 1)

        self.search_input.textChanged.connect(lambda q: self.conn_manager.on_search(q))

        # === Backup Templates Section ===
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        sidebar_layout.addWidget(divider)

        backup_header = QHBoxLayout()
        backup_title = QLabel("备份模板")
        backup_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {COLORS['text']};")
        backup_header.addWidget(backup_title)
        backup_header.addStretch()

        new_backup_btn = QPushButton("+")
        new_backup_btn.setObjectName("newConnBtn")
        new_backup_btn.setFixedSize(28, 28)
        new_backup_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; color: {COLORS['text']}; border-radius: 4px; font-weight: bold; font-size: 14px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; }}"
        )
        new_backup_btn.clicked.connect(self.backup_manager.on_add)
        backup_header.addWidget(new_backup_btn)

        sidebar_layout.addLayout(backup_header)

        # 开机自启开关
        from PySide6.QtWidgets import QCheckBox
        self.autostart_check = QCheckBox("开机自启")
        self.autostart_check.setChecked(self._mgr.get("auto_start", False))
        self.autostart_check.setStyleSheet(f"font-size: 11px; color: {COLORS['text_sec']}; margin-bottom: 4px;")
        self.autostart_check.toggled.connect(lambda checked: self._mgr.set("auto_start", checked))
        sidebar_layout.addWidget(self.autostart_check)

        backup_scroll = QScrollArea()
        backup_scroll.setWidgetResizable(True)
        backup_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        backup_scroll.setFrameShape(QFrame.NoFrame)
        self.backup_container = QWidget()
        self.backup_list_layout = QVBoxLayout(self.backup_container)
        self.backup_list_layout.setAlignment(Qt.AlignTop)
        self.backup_list_layout.setContentsMargins(4, 8, 4, 8)
        self.backup_list_layout.setSpacing(6)
        backup_scroll.setWidget(self.backup_container)
        sidebar_layout.addWidget(backup_scroll, 1)

        # === 备份组 ===
        divider2 = QFrame()
        divider2.setFrameShape(QFrame.HLine)
        divider2.setStyleSheet(f"color: {COLORS['border']};")
        sidebar_layout.addWidget(divider2)

        group_header = QHBoxLayout()
        group_title = QLabel("备份组")
        group_title.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {COLORS['text_sec']};"
        )
        group_header.addWidget(group_title)
        group_header.addStretch()

        add_group_btn = QPushButton("+ 新建备份组")
        add_group_btn.setFixedHeight(28)
        add_group_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
            f"color: {COLORS['text_hint']}; border-radius: 4px; font-size: 11px; font-weight: bold; }}"
            f"QPushButton:hover {{ border-color: {COLORS['mint']}; color: {COLORS['mint']}; }}"
        )
        add_group_btn.clicked.connect(self.group_manager.on_add)
        group_header.addWidget(add_group_btn)
        sidebar_layout.addLayout(group_header)

        group_scroll = QScrollArea()
        group_scroll.setWidgetResizable(True)
        group_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        group_scroll.setFrameShape(QFrame.NoFrame)
        self.group_container = QWidget()
        self.group_list_layout = QVBoxLayout(self.group_container)
        self.group_list_layout.setAlignment(Qt.AlignTop)
        self.group_list_layout.setContentsMargins(4, 8, 4, 8)
        self.group_list_layout.setSpacing(6)
        group_scroll.setWidget(self.group_container)
        sidebar_layout.addWidget(group_scroll, 1)

        self.group_manager.refresh()

        log_btn = QPushButton("📋 日志")
        log_btn.setFixedHeight(32)
        log_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
            f"color: {COLORS['text_sec']}; border-radius: 6px; padding: 6px 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; color: {COLORS['text']}; }}"
        )
        log_btn.clicked.connect(self._on_show_logs)
        sidebar_layout.addWidget(log_btn)

        # Settings button
        settings_btn = QPushButton("⚙ 设置")
        settings_btn.setFixedHeight(32)
        settings_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
            f"color: {COLORS['text_sec']}; border-radius: 6px; padding: 6px 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; color: {COLORS['text']}; }}"
        )
        settings_btn.clicked.connect(self._on_show_settings)
        sidebar_layout.addWidget(settings_btn)

        body_layout.addWidget(sidebar)

        # Content
        self.content_stack = QStackedWidget()
        self._build_welcome_page()
        self._build_file_browser()
        from ui.settings_page import SettingsPage
        self.settings_page = SettingsPage()
        self.content_stack.addWidget(self.settings_page)  # index=2
        body_layout.addWidget(self.content_stack, 1)

        root_layout.addWidget(body, 1)

    def _build_welcome_page(self):
        page = QWidget()
        page.setStyleSheet(f"background-color: {COLORS['bg']};")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(16)

        icon_widget = WelcomeIcon()
        icon_widget.setFixedSize(120, 120)
        layout.addWidget(icon_widget, 0, Qt.AlignCenter)

        welcome_title = QLabel("欢迎使用拾云")
        welcome_title.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {COLORS['mint']};")
        layout.addWidget(welcome_title, 0, Qt.AlignCenter)

        welcome_sub = QLabel("选择或创建一个服务器连接开始使用")
        welcome_sub.setStyleSheet(f"font-size: 13px; color: {COLORS['text_sec']};")
        layout.addWidget(welcome_sub, 0, Qt.AlignCenter)

        tip = QLabel("  提示: 点击左侧「+ 新建连接」添加你的第一个 SFTP 服务器")
        tip.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_hint']}; "
            f"background-color: {COLORS['mint_light']}; "
            f"border-radius: 8px; padding: 10px 16px;"
        )
        tip.setWordWrap(True)
        tip.setMaximumWidth(420)
        layout.addWidget(tip, 0, Qt.AlignCenter)

        self.content_stack.addWidget(page)

    def _build_file_browser(self):
        page = QWidget()
        page.setStyleSheet(f"background-color: {COLORS['bg']};")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 16, 20, 8)

        self.path_label = QLineEdit("/")
        self.path_label.setStyleSheet(
            f"QLineEdit {{ font-size: 14px; font-weight: bold; color: {COLORS['mint']}; "
            f"background: transparent; border: 1px solid transparent; border-radius: 4px; "
            f"padding: 2px 6px; }}"
            f"QLineEdit:focus {{ border: 1px solid {COLORS['mint']}; background: {COLORS['bg']}; }}"
        )
        self.path_label.returnPressed.connect(self._on_path_submit)
        top_layout.addWidget(self.path_label, 1)
        top_layout.addStretch()

        upload_btn = QPushButton("上传")
        upload_btn.setObjectName("uploadBtn")
        upload_btn.setFixedHeight(30)
        upload_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['mint']}; color: white; border: none; "
            f"border-radius: 6px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['mint_dark']}; }}"
        )
        upload_btn.clicked.connect(lambda: self.file_manager._on_upload())
        top_layout.addWidget(upload_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("refreshBtn")
        refresh_btn.setFixedHeight(30)
        refresh_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['border']}; background: transparent; "
            f"color: {COLORS['text']}; border-radius: 6px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['card_hover']}; }}"
        )
        refresh_btn.clicked.connect(lambda: self.file_manager.refresh_files())
        top_layout.addWidget(refresh_btn)

        disconnect_btn = QPushButton("断开")
        disconnect_btn.setObjectName("disconnectBtn")
        disconnect_btn.setFixedHeight(30)
        disconnect_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid {COLORS['danger']}; background: transparent; "
            f"color: {COLORS['danger']}; border-radius: 6px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['danger_bg']}; }}"
        )
        disconnect_btn.clicked.connect(lambda: self.conn_manager.on_disconnect())
        top_layout.addWidget(disconnect_btn)

        self.save_back_btn = QPushButton("保存回服务器")
        self.save_back_btn.setFixedHeight(30)
        self.save_back_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['mint']}; color: white; border: none; "
            f"border-radius: 6px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['mint_dark']}; }}"
        )
        self.save_back_btn.clicked.connect(lambda: self.file_manager.save_back_to_server())
        self.save_back_btn.hide()
        top_layout.addWidget(self.save_back_btn)

        layout.addWidget(top_bar)

        class _FileTableFocusDelegate(QStyledItemDelegate):
            def paint(self, painter, option, index):
                super().paint(painter, option, index)
                if option.state & QStyle.State_HasFocus:
                    painter.save()
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.setPen(QPen(QColor(COLORS['mint']), 1, Qt.DashLine))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(option.rect.adjusted(1, 1, -2, -2))
                    painter.restore()

        self.file_table = FileExplorerTable()
        self.file_table.setColumnCount(3)
        self.file_table.setHorizontalHeaderLabels(["名称", "大小", "修改日期"])
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.setShowGrid(False)
        self.file_table.setAlternatingRowColors(False)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.setColumnWidth(1, 100)
        self.file_table.setColumnWidth(2, 140)
        self.file_table.verticalHeader().setDefaultSectionSize(34)
        self.file_table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.file_table.setItemDelegate(_FileTableFocusDelegate(self.file_table))

        header = self.file_table.horizontalHeader()
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

        self.file_table.setStyleSheet(f"""
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

        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)

        layout.addWidget(self.file_table, 1)

        bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(16, 4, 16, 4)
        bottom_layout.setSpacing(8)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']};")
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()

        layout.addWidget(bottom_bar)

        self.content_stack.addWidget(page)

    # === Settings Sync ===

    def _on_settings_changed(self, key, value):
        if key == "startup_backup_reminder":
            if value and hasattr(self, '_tray'):
                from core.config import has_upcoming_backup
                if has_upcoming_backup(hours=12):
                    self._tray.showMessage(
                        "拾云 - 备份提醒", "未来 12 小时内有备份任务即将执行，请保持电脑开机",
                        QSystemTrayIcon.Information, 5000
                    )
        elif key == "auto_start":
            if hasattr(self, 'autostart_check'):
                self.autostart_check.blockSignals(True)
                self.autostart_check.setChecked(value)
                self.autostart_check.blockSignals(False)
            if hasattr(self, 'settings_page'):
                self.settings_page._auto_start_sub.setVisible(value)

    def _on_show_logs(self):
        dialog = LogDialog(self)
        dialog.exec()

    def _on_show_settings(self):
        self.content_stack.setCurrentIndex(2)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def closeEvent(self, event):
        if self._mgr.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
        else:
            event.accept()
            self._real_quit()

    def _real_quit(self):
        """真正退出应用，清理资源"""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        if self.sftp.connected:
            self.sftp.disconnect()
        if hasattr(self, '_tray'):
            self._tray.hide()
        QApplication.quit()

    def _on_path_submit(self):
        path = self.path_label.text().strip()
        if not path:
            path = "/"
        if not self.sftp.connected:
            self.path_label.setText(self.file_manager.current_remote_path)
            return
        try:
            self.sftp.stat(path)
            self.file_manager.refresh_files(path)
        except Exception:
            self.path_label.setText(self.file_manager.current_remote_path)
            show_message(self, "路径错误", f"路径不存在或无法访问:\n{path}", "warning")

    # === Native window resize (Windows API) ===

    def _setup_native_resize(self):
        hwnd = int(self.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
        style |= WS_THICKFRAME
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE:
                return True, 0
            elif msg.message == WM_NCHITTEST:
                result = ctypes.windll.user32.DefWindowProcW(
                    msg.hWnd, msg.message, msg.wParam, msg.lParam)
                if result == HTCLIENT:
                    pos = QCursor.pos()
                    gx, gy = pos.x(), pos.y()
                    w, h = self.width(), self.height()
                    wx, wy = self.x(), self.y()
                    border = ctypes.windll.user32.GetSystemMetrics(32)

                    if gx < wx + border and gy < wy + border:
                        return True, HTTOPLEFT
                    elif gx > wx + w - border and gy < wy + border:
                        return True, HTTOPRIGHT
                    elif gx < wx + border and gy > wy + h - border:
                        return True, HTBOTTOMLEFT
                    elif gx > wx + w - border and gy > wy + h - border:
                        return True, HTBOTTOMRIGHT
                    elif gx < wx + border:
                        return True, HTLEFT
                    elif gx > wx + w - border:
                        return True, HTRIGHT
                    elif gy < wy + border:
                        return True, HTTOP
                    elif gy > wy + h - border:
                        return True, HTBOTTOM
                return True, result
        return super().nativeEvent(eventType, message)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor(COLORS['mint']), 3))
        painter.setBrush(QColor(COLORS['bg']))
        painter.drawRect(1, 1, self.width() - 2, self.height() - 2)
        painter.end()
