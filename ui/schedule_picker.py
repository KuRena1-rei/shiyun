from datetime import datetime, timedelta
from croniter import croniter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSpinBox, QCheckBox, QTimeEdit,
    QDateEdit, QRadioButton, QButtonGroup, QFrame
)
from PySide6.QtCore import Qt, QTime, QDate, Signal
from ui.style import COLORS

WEEKDAY_NAMES = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _label_style(font_size: int = 12, color_key: str = 'text_sec') -> str:
    return f"font-size: {font_size}px; color: {COLORS[color_key]};"


def _radio_style(font_size: int = 12) -> str:
    return f"font-size: {font_size}px; color: {COLORS['text']};"


class SchedulePicker(QWidget):
    schedule_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._updating = False
        self._build_ui()
        self._connect_signals()
        self._update_all()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        freq_lbl = QLabel("频率")
        freq_lbl.setStyleSheet(_label_style())
        row1.addWidget(freq_lbl)

        self.freq_combo = QComboBox()
        self.freq_combo.addItems(["每天", "每隔N天", "每周", "每月"])
        self.freq_combo.setFixedHeight(32)
        self.freq_combo.setFixedWidth(120)
        row1.addWidget(self.freq_combo)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 365)
        self.interval_spin.setValue(3)
        self.interval_spin.setFixedHeight(32)
        self.interval_spin.setFixedWidth(60)
        self.interval_label = QLabel("天")
        self.interval_label.setStyleSheet(_label_style())
        row1.addWidget(self.interval_spin)
        row1.addWidget(self.interval_label)

        row1.addStretch()
        layout.addLayout(row1)

        self.weekday_widget = QWidget()
        weekday_layout = QHBoxLayout(self.weekday_widget)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        weekday_layout.setSpacing(4)
        self.weekday_checks = []
        for i, name in enumerate(WEEKDAY_NAMES):
            cb = QCheckBox(name)
            cb.setStyleSheet(_label_style(11, 'text'))
            cb.setChecked(i < 5)
            self.weekday_checks.append(cb)
            weekday_layout.addWidget(cb)
        weekday_layout.addStretch()
        self.weekday_widget.setVisible(False)
        layout.addWidget(self.weekday_widget)

        self.month_day_widget = QWidget()
        month_layout = QHBoxLayout(self.month_day_widget)
        month_layout.setContentsMargins(0, 0, 0, 0)
        month_layout.setSpacing(6)
        month_day_lbl = QLabel("每月第")
        month_day_lbl.setStyleSheet(_label_style())
        self.month_day_spin = QSpinBox()
        self.month_day_spin.setRange(1, 28)
        self.month_day_spin.setValue(1)
        self.month_day_spin.setFixedHeight(32)
        self.month_day_spin.setFixedWidth(50)
        month_day_end = QLabel("天")
        month_day_end.setStyleSheet(_label_style())
        month_layout.addWidget(month_day_lbl)
        month_layout.addWidget(self.month_day_spin)
        month_layout.addWidget(month_day_end)
        month_layout.addStretch()
        self.month_day_widget.setVisible(False)
        layout.addWidget(self.month_day_widget)

        row2 = QHBoxLayout()
        row2.setSpacing(8)

        time_lbl = QLabel("时间")
        time_lbl.setStyleSheet(_label_style())
        row2.addWidget(time_lbl)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime(1, 0))
        self.time_edit.setFixedHeight(32)
        self.time_edit.setFixedWidth(80)
        row2.addWidget(self.time_edit)

        row2.addSpacing(16)

        start_lbl = QLabel("起始日期")
        start_lbl.setStyleSheet(_label_style())
        row2.addWidget(start_lbl)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate())
        self.start_date.setFixedHeight(32)
        self.start_date.setFixedWidth(120)
        row2.addWidget(self.start_date)

        row2.addStretch()
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.setSpacing(8)

        end_lbl = QLabel("结束")
        end_lbl.setStyleSheet(_label_style())
        row3.addWidget(end_lbl)

        self.end_group = QButtonGroup(self)
        self.end_never = QRadioButton("永不")
        self.end_never.setChecked(True)
        self.end_never.setStyleSheet(_radio_style())
        self.end_group.addButton(self.end_never, 0)
        row3.addWidget(self.end_never)

        self.end_count_radio = QRadioButton("执行")
        self.end_count_radio.setStyleSheet(_radio_style())
        self.end_group.addButton(self.end_count_radio, 1)
        row3.addWidget(self.end_count_radio)

        self.end_count_spin = QSpinBox()
        self.end_count_spin.setRange(1, 9999)
        self.end_count_spin.setValue(10)
        self.end_count_spin.setFixedHeight(28)
        self.end_count_spin.setFixedWidth(60)
        self.end_count_spin.setEnabled(False)
        row3.addWidget(self.end_count_spin)

        count_suffix = QLabel("次后")
        count_suffix.setStyleSheet(_label_style())
        row3.addWidget(count_suffix)

        self.end_date_radio = QRadioButton("于")
        self.end_date_radio.setStyleSheet(_radio_style())
        self.end_group.addButton(self.end_date_radio, 2)
        row3.addWidget(self.end_date_radio)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(QDate.currentDate().addMonths(1))
        self.end_date_edit.setFixedHeight(28)
        self.end_date_edit.setFixedWidth(120)
        self.end_date_edit.setEnabled(False)
        row3.addWidget(self.end_date_edit)

        row3.addStretch()
        layout.addLayout(row3)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background-color: {COLORS['border']}; max-height: 1px;")
        layout.addWidget(sep)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['mint']}; font-weight: bold;"
        )
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        preview_lbl = QLabel("下次执行:")
        preview_lbl.setStyleSheet(_label_style(11) + " margin-top: 4px;")
        layout.addWidget(preview_lbl)

        self.preview_label = QLabel()
        self.preview_label.setStyleSheet(_label_style(11, 'text_hint'))
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

    def _connect_signals(self) -> None:
        self.freq_combo.currentIndexChanged.connect(self._update_all)
        self.interval_spin.valueChanged.connect(self._update_all)
        self.time_edit.timeChanged.connect(self._update_all)
        self.start_date.dateChanged.connect(self._update_all)
        self.end_group.buttonClicked.connect(self._update_all)
        self.end_count_spin.valueChanged.connect(self._update_all)
        self.end_date_edit.dateChanged.connect(self._update_all)
        for cb in self.weekday_checks:
            cb.stateChanged.connect(self._update_all)
        self.month_day_spin.valueChanged.connect(self._update_all)

    def _update_all(self) -> None:
        if self._updating:
            return
        self._updating = True

        freq_idx = self.freq_combo.currentIndex()
        self.interval_spin.setVisible(freq_idx == 1)
        self.interval_label.setVisible(freq_idx == 1)
        self.weekday_widget.setVisible(freq_idx == 2)
        self.month_day_widget.setVisible(freq_idx == 3)

        self.end_count_spin.setEnabled(self.end_count_radio.isChecked())
        self.end_date_edit.setEnabled(self.end_date_radio.isChecked())

        self._update_summary()
        self._update_preview()
        self.schedule_changed.emit()
        self._updating = False

    def _get_cron_expr(self) -> str:
        freq_idx = self.freq_combo.currentIndex()
        hour = self.time_edit.time().hour()
        minute = self.time_edit.time().minute()

        if freq_idx == 0:
            return f"{minute} {hour} * * *"
        elif freq_idx == 1:
            interval = self.interval_spin.value()
            return f"{minute} {hour} */{interval} * *"
        elif freq_idx == 2:
            # weekday 索引 0=周一..6=周日，cron 需要 0=周日..6=周六
            selected = []
            for i, cb in enumerate(self.weekday_checks):
                if cb.isChecked():
                    selected.append(str((i + 1) % 7))
            if not selected:
                selected = ["1"]
            return f"{minute} {hour} * * {','.join(selected)}"
        elif freq_idx == 3:
            day = self.month_day_spin.value()
            return f"{minute} {hour} {day} * *"
        return f"{minute} {hour} * * *"

    def _update_summary(self) -> None:
        freq_idx = self.freq_combo.currentIndex()
        time_str = self.time_edit.time().toString("HH:mm")
        start = self.start_date.date().toString("yyyy-MM-dd")

        if freq_idx == 0:
            desc = f"每天 {time_str}"
        elif freq_idx == 1:
            n = self.interval_spin.value()
            desc = f"每 {n} 天 {time_str}"
        elif freq_idx == 2:
            days = [WEEKDAY_NAMES[i] for i, cb in enumerate(self.weekday_checks) if cb.isChecked()]
            if not days:
                days = ["周一"]
            desc = f"每{'+'.join(days)} {time_str}"
        elif freq_idx == 3:
            day = self.month_day_spin.value()
            desc = f"每月 {day} 日 {time_str}"
        else:
            desc = f"每天 {time_str}"

        end_desc = ""
        if self.end_count_radio.isChecked():
            end_desc = f"，共 {self.end_count_spin.value()} 次"
        elif self.end_date_radio.isChecked():
            end_desc = f"，至 {self.end_date_edit.date().toString('yyyy-MM-dd')}"

        self.summary_label.setText(f"{desc}，从 {start} 开始{end_desc}")

    def _update_preview(self) -> None:
        cron_expr = self._get_cron_expr()
        try:
            cron = croniter(cron_expr, datetime.now())
            lines = []
            for _ in range(5):
                dt = cron.get_next(datetime)
                lines.append(dt.strftime("%m-%d %H:%M"))
            self.preview_label.setText("  |  ".join(lines))
        except Exception:
            self.preview_label.setText("（无效的调度规则）")

    def get_schedule(self) -> dict:
        freq_idx = self.freq_combo.currentIndex()
        freq_map = {0: "daily", 1: "interval", 2: "weekly", 3: "monthly"}
        weekdays = [i for i, cb in enumerate(self.weekday_checks) if cb.isChecked()]

        end_type = "never"
        end_count = 0
        end_date = ""
        if self.end_count_radio.isChecked():
            end_type = "count"
            end_count = self.end_count_spin.value()
        elif self.end_date_radio.isChecked():
            end_type = "date"
            end_date = self.end_date_edit.date().toString("yyyy-MM-dd")

        rule = {
            "freq": freq_map[freq_idx],
            "interval": self.interval_spin.value(),
            "time": self.time_edit.time().toString("HH:mm"),
            "start_date": self.start_date.date().toString("yyyy-MM-dd"),
            "end_type": end_type,
            "end_count": end_count,
            "end_date": end_date,
            "weekdays": weekdays,
            "month_day": self.month_day_spin.value(),
        }

        cron_expr = self._get_cron_expr()
        start_dt = datetime.combine(
            self.start_date.date().toPython(),
            self.time_edit.time().toPython()
        )
        # 如果 start_date 是今天，用当前时间作为锚点
        # 这样 croniter 会正确计算：时间未过→今天触发，已过→明天触发
        now = datetime.now()
        if start_dt.date() == now.date():
            anchor = now
        else:
            anchor = start_dt
        cron = croniter(cron_expr, anchor)
        next_run = cron.get_next(datetime)

        if end_type == "date" and end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=self.time_edit.time().hour(),
                minute=self.time_edit.time().minute()
            )
            if next_run > end_dt:
                next_run = None
        elif end_type == "count":
            pass

        return {
            "schedule_enabled": True,
            "schedule_rule": rule,
            "next_run": next_run.isoformat() if next_run else None,
            "schedule_time": self.time_edit.time().toString("HH:mm"),
        }

    def set_schedule(self, data: dict) -> None:
        self._updating = True
        rule = data.get("schedule_rule", {})
        freq = rule.get("freq", "daily")
        freq_map = {"daily": 0, "interval": 1, "weekly": 2, "monthly": 3}
        self.freq_combo.setCurrentIndex(freq_map.get(freq, 0))

        self.interval_spin.setValue(rule.get("interval", 3))

        for i, cb in enumerate(self.weekday_checks):
            cb.setChecked(i in rule.get("weekdays", [0, 1, 2, 3, 4]))

        self.month_day_spin.setValue(rule.get("month_day", 1))

        time_str = rule.get("time", data.get("schedule_time", "01:00"))
        h, m = time_str.split(":")
        self.time_edit.setTime(QTime(int(h), int(m)))

        start = rule.get("start_date", "")
        if start:
            self.start_date.setDate(QDate.fromString(start, "yyyy-MM-dd"))

        end_type = rule.get("end_type", "never")
        if end_type == "count":
            self.end_count_radio.setChecked(True)
            self.end_count_spin.setValue(rule.get("end_count", 10))
        elif end_type == "date":
            self.end_date_radio.setChecked(True)
            ed = rule.get("end_date", "")
            if ed:
                self.end_date_edit.setDate(QDate.fromString(ed, "yyyy-MM-dd"))
        else:
            self.end_never.setChecked(True)

        self._updating = False
        self._update_all()

    def get_summary_text(self) -> str:
        freq_idx = self.freq_combo.currentIndex()
        time_str = self.time_edit.time().toString("HH:mm")

        if freq_idx == 0:
            return f"每天 {time_str}"
        elif freq_idx == 1:
            return f"每{self.interval_spin.value()}天 {time_str}"
        elif freq_idx == 2:
            days = [WEEKDAY_NAMES[i] for i, cb in enumerate(self.weekday_checks) if cb.isChecked()]
            return f"每{'+'.join(days) if days else '周一'} {time_str}"
        elif freq_idx == 3:
            return f"每月{self.month_day_spin.value()}日 {time_str}"
        return f"每天 {time_str}"
