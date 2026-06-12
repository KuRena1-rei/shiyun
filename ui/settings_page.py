from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QRadioButton, QButtonGroup, QComboBox
)
from PySide6.QtCore import Qt
from ui.style import COLORS
from core.config import is_auto_start_enabled, set_auto_start
from core.settings_manager import SettingsManager
from ui.widgets import ToggleSwitch


class SettingsPage(QWidget):
    """Settings page with feature toggles."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {COLORS['bg']};")
        self._switches: dict[str, ToggleSwitch] = {}
        self._mgr: SettingsManager = SettingsManager.instance()
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 24, 32, 24)
        root.setSpacing(0)

        title = QLabel("设置")
        title.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {COLORS['mint']}; margin-bottom: 16px;"
        )
        root.addWidget(title)

        # === 开机自启 ===
        auto_start_card = self._create_setting_row(
            "auto_start", "开机自启",
            "开机时自动运行拾云（这是备份功能正常运行的关键开关，关闭后定时备份将无法自动执行）"
        )
        root.addWidget(auto_start_card)
        root.addSpacing(4)

        # 自启子选项：最小化到托盘 / 打开主窗口
        self._auto_start_sub = QWidget()
        self._auto_start_sub.setObjectName("connCard")
        self._auto_start_sub.setStyleSheet(
            f"QWidget#connCard {{ border: 1px solid {COLORS['border']}; border-radius: 10px; "
            f"margin-left: 16px; }}"
        )
        sub_layout = QVBoxLayout(self._auto_start_sub)
        sub_layout.setContentsMargins(16, 10, 16, 10)
        sub_layout.setSpacing(6)

        sub_hint = QLabel("自启时的行为")
        sub_hint.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {COLORS['text_sec']};")
        sub_layout.addWidget(sub_hint)

        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(16)

        self._radio_minimize = QRadioButton("最小化到托盘（推荐）")
        self._radio_normal = QRadioButton("打开主窗口")

        radio_style = f"font-size: 12px; color: {COLORS['text']};"
        self._radio_minimize.setStyleSheet(radio_style)
        self._radio_normal.setStyleSheet(radio_style)

        self._radio_group = QButtonGroup(self)
        self._radio_group.addButton(self._radio_minimize, 0)
        self._radio_group.addButton(self._radio_normal, 1)

        radio_layout.addWidget(self._radio_minimize)
        radio_layout.addWidget(self._radio_normal)
        radio_layout.addStretch()
        sub_layout.addLayout(radio_layout)

        self._auto_start_sub.setVisible(False)
        root.addWidget(self._auto_start_sub)
        root.addSpacing(8)

        # === 其他设置 ===
        other_settings = [
            (
                "prevent_shutdown",
                "阻止关机",
                "备份任务执行期间，阻止系统关机以保护数据安全",
            ),
            (
                "startup_backup_reminder",
                "启动时备份提醒",
                "启动软件时检查是否有即将执行的备份任务，并通过系统通知提醒（需在系统设置中开启拾云的通知权限）",
            ),
            (
                "minimize_to_tray",
                "关闭时最小化到托盘",
                "点击关闭按钮时隐藏到系统托盘而非退出程序",
            ),
        ]

        for key, name, desc in other_settings:
            row = self._create_setting_row(key, name, desc)
            root.addWidget(row)
            root.addSpacing(12)

        # === 下载设置 ===
        dl_card = QWidget()
        dl_card.setObjectName("connCard")
        dl_card.setStyleSheet(
            f"QWidget#connCard {{ border: 1px solid {COLORS['border']}; border-radius: 10px; }}"
        )
        dl_layout = QHBoxLayout(dl_card)
        dl_layout.setContentsMargins(16, 12, 16, 12)
        dl_layout.setSpacing(12)

        dl_text = QVBoxLayout()
        dl_text.setSpacing(2)
        dl_name = QLabel("并行下载数")
        dl_name.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLORS['text']};")
        dl_text.addWidget(dl_name)
        dl_desc = QLabel("同时下载的文件数量，越大速度越快但可能给服务器带来压力")
        dl_desc.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']};")
        dl_desc.setWordWrap(True)
        dl_text.addWidget(dl_desc)
        dl_layout.addLayout(dl_text, 1)

        self._concurrency_combo = QComboBox()
        self._concurrency_combo.setFixedWidth(60)
        self._concurrency_combo.addItems([str(i) for i in range(1, 6)])
        self._concurrency_combo.setStyleSheet(
            f"QComboBox {{ border: 1px solid {COLORS['border']}; border-radius: 4px; "
            f"padding: 4px 8px; font-size: 13px; color: {COLORS['text']}; "
            f"background: {COLORS['bg']}; }}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{ background: {COLORS['bg']}; color: {COLORS['text']}; "
            f"selection-background-color: {COLORS['mint_light']}; }}"
        )
        self._concurrency_combo.currentTextChanged.connect(self._on_concurrency_changed)
        dl_layout.addWidget(self._concurrency_combo, 0, Qt.AlignVCenter)

        root.addWidget(dl_card)
        root.addSpacing(12)

        root.addStretch()

    def _create_setting_row(self, key: str, name: str, description: str) -> QWidget:
        row = QWidget()
        row.setObjectName("connCard")
        row.setStyleSheet(
            f"QWidget#connCard {{ border: 1px solid {COLORS['border']}; border-radius: 10px; }}"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLORS['text']};")
        text_col.addWidget(name_label)

        desc_label = QLabel(description)
        desc_label.setStyleSheet(f"font-size: 11px; color: {COLORS['text_hint']};")
        desc_label.setWordWrap(True)
        text_col.addWidget(desc_label)

        layout.addLayout(text_col, 1)

        switch = ToggleSwitch()
        switch.toggled.connect(lambda checked, k=key: self._on_toggled(k, checked))
        self._switches[key] = switch
        layout.addWidget(switch, 0, Qt.AlignVCenter)

        return row

    def _load_values(self) -> None:
        for key, switch in self._switches.items():
            switch.setChecked(self._mgr.get(key, True))

        mode = self._mgr.get("auto_start_mode", "minimize")
        if mode == "normal":
            self._radio_normal.setChecked(True)
        else:
            self._radio_minimize.setChecked(True)

        self._radio_minimize.toggled.connect(self._on_auto_start_mode_changed)
        self._auto_start_sub.setVisible(self._mgr.get("auto_start", False))

        concurrency = self._mgr.get("download_concurrency", 3)
        self._concurrency_combo.setCurrentText(str(concurrency))

    def _on_toggled(self, key: str, checked: bool) -> None:
        if key == "auto_start":
            self._auto_start_sub.setVisible(checked)
        self._mgr.set(key, checked)

    def _on_auto_start_mode_changed(self) -> None:
        if not self._mgr.get("auto_start", False):
            return
        mode = "normal" if self._radio_normal.isChecked() else "minimize"
        self._mgr.set("auto_start_mode", mode)
        set_auto_start(True, mode)

    def _on_concurrency_changed(self, value: str) -> None:
        self._mgr.set("download_concurrency", int(value))
