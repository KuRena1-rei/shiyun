import json
import shutil
from pathlib import Path


CONFIG_DIR = Path.home() / ".shiyun"
CONFIG_FILE = CONFIG_DIR / "connections.json"
BACKUP_FILE = CONFIG_DIR / "backups.json"
BACKUP_LOG_FILE = CONFIG_DIR / "backup_logs.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
BACKUP_GROUPS_FILE = CONFIG_DIR / "backup_groups.json"

DEFAULT_SETTINGS = {
    "prevent_shutdown": True,
    "startup_backup_reminder": True,
    "minimize_to_tray": True,
    "auto_start_mode": "minimize",  # "minimize" or "normal"
}


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_connections() -> list[dict]:
    _ensure_config_dir()
    if not CONFIG_FILE.exists():
        return []
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        backup = CONFIG_FILE.with_suffix(".json.bak")
        shutil.copy2(CONFIG_FILE, backup)
        return []

    from core.crypto import decrypt_password, is_encrypted, migrate_password
    migrated = False
    for conn in data:
        pwd = conn.get("password", "")
        if pwd and not is_encrypted(pwd):
            conn["password"] = migrate_password(pwd)
            migrated = True
        elif pwd:
            conn["password"] = decrypt_password(pwd)
    if migrated:
        save_connections(data)
    return data


def save_connections(connections: list[dict]):
    _ensure_config_dir()
    from core.crypto import encrypt_password, is_encrypted
    out = []
    for conn in connections:
        c = dict(conn)
        pwd = c.get("password", "")
        if pwd and not is_encrypted(pwd):
            c["password"] = encrypt_password(pwd)
        out.append(c)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def add_connection(conn: dict) -> dict:
    connections = load_connections()
    conn["id"] = max((c.get("id", 0) for c in connections), default=0) + 1
    connections.append(conn)
    save_connections(connections)
    return conn


def update_connection(conn_id: int, conn: dict):
    connections = load_connections()
    for i, c in enumerate(connections):
        if c.get("id") == conn_id:
            conn["id"] = conn_id
            connections[i] = conn
            break
    save_connections(connections)


def delete_connection(conn_id: int) -> None:
    connections = load_connections()
    connections = [c for c in connections if c.get("id") != conn_id]
    save_connections(connections)


# === Backup Templates ===

def load_backups() -> list[dict]:
    _ensure_config_dir()
    if not BACKUP_FILE.exists():
        return []
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for b in data:
            if "remote_path" in b and "remote_paths" not in b:
                b["remote_paths"] = [b.pop("remote_path")]
            elif "remote_path" in b:
                del b["remote_path"]
            b.setdefault("schedule_enabled", False)
            b.setdefault("schedule_time", "01:00")
            b.setdefault("auto_shutdown", False)
        return data
    except (json.JSONDecodeError, ValueError):
        backup = BACKUP_FILE.with_suffix(".json.bak")
        shutil.copy2(BACKUP_FILE, backup)
        return []


def save_backups(backups: list[dict]) -> None:
    _ensure_config_dir()
    with open(BACKUP_FILE, "w", encoding="utf-8") as f:
        json.dump(backups, f, ensure_ascii=False, indent=2)


def add_backup(backup: dict) -> dict:
    backups = load_backups()
    backup["id"] = max((b.get("id", 0) for b in backups), default=0) + 1
    backups.append(backup)
    save_backups(backups)
    return backup


def update_backup(backup_id: int, backup: dict):
    backups = load_backups()
    for i, b in enumerate(backups):
        if b.get("id") == backup_id:
            b.update(backup)
            b["id"] = backup_id
            backups[i] = b
            break
    save_backups(backups)


def delete_backup(backup_id: int) -> None:
    backups = load_backups()
    backups = [b for b in backups if b.get("id") != backup_id]
    save_backups(backups)


# === Backup Groups ===

def load_backup_groups() -> list[dict]:
    _ensure_config_dir()
    if not BACKUP_GROUPS_FILE.exists():
        return []
    try:
        with open(BACKUP_GROUPS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for g in data:
            g.setdefault("schedule_enabled", False)
            g.setdefault("schedule_time", "01:00")
            g.setdefault("auto_shutdown", False)
            g.setdefault("incremental", False)
            g.setdefault("backup_ids", [])
        return data
    except (json.JSONDecodeError, ValueError):
        backup = BACKUP_GROUPS_FILE.with_suffix(".json.bak")
        shutil.copy2(BACKUP_GROUPS_FILE, backup)
        return []


def save_backup_groups(groups: list[dict]) -> None:
    _ensure_config_dir()
    with open(BACKUP_GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False, indent=2)


def add_backup_group(group: dict) -> dict:
    groups = load_backup_groups()
    group["id"] = max((g.get("id", 0) for g in groups), default=0) + 1
    groups.append(group)
    save_backup_groups(groups)
    return group


def update_backup_group(group_id: int, group: dict):
    groups = load_backup_groups()
    for i, g in enumerate(groups):
        if g.get("id") == group_id:
            g.update(group)
            g["id"] = group_id
            groups[i] = g
            break
    save_backup_groups(groups)


def delete_backup_group(group_id: int) -> None:
    groups = load_backup_groups()
    groups = [g for g in groups if g.get("id") != group_id]
    save_backup_groups(groups)


def get_backup_group_for_backup(backup_id: int) -> dict | None:
    """Find which group (if any) a backup template belongs to."""
    groups = load_backup_groups()
    for g in groups:
        if backup_id in g.get("backup_ids", []):
            return g
    return None


# === Backup Logs ===

def load_backup_logs() -> list[dict]:
    _ensure_config_dir()
    if not BACKUP_LOG_FILE.exists():
        return []
    try:
        with open(BACKUP_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        backup = BACKUP_LOG_FILE.with_suffix(".json.bak")
        shutil.copy2(BACKUP_LOG_FILE, backup)
        return []


def save_backup_logs(logs: list[dict]) -> None:
    _ensure_config_dir()
    with open(BACKUP_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def add_backup_log(log: dict) -> dict:
    logs = load_backup_logs()
    log["id"] = max((l.get("id", 0) for l in logs), default=0) + 1
    logs.append(log)
    save_backup_logs(logs)
    return log


def clear_backup_logs() -> None:
    save_backup_logs([])


# === Auto Start (Windows) ===

import sys


def _auto_start_key() -> str:
    """Windows 注册表 Run 键路径"""
    return r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_auto_start_enabled() -> bool:
    """检查开机自启是否已启用"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _auto_start_key(), 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, "ShiYun")
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def set_auto_start(enable: bool, mode: str = "minimize") -> None:
    """设置开机自启。mode: 'minimize'（最小化到托盘）或 'normal'（打开主窗口）"""
    if sys.platform != "win32":
        return
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _auto_start_key(), 0, winreg.KEY_SET_VALUE)
    try:
        if enable:
            import os
            exe = sys.executable
            if exe.endswith("python.exe"):
                script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "main.py")
                flag = " --startup" if mode == "minimize" else ""
                value = f'"{exe}" "{script}"{flag}'
            else:
                flag = " --startup" if mode == "minimize" else ""
                value = f'"{exe}"{flag}'
            winreg.SetValueEx(key, "ShiYun", 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, "ShiYun")
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def has_backup_today() -> bool:
    """检查今天是否有需要执行的备份"""
    from datetime import datetime
    backups = load_backups()
    now = datetime.now()
    today_weekday = now.weekday()  # 0=周一..6=周日
    today_str = now.strftime("%Y-%m-%d")

    for b in backups:
        if not b.get("schedule_enabled"):
            continue

        # 有 next_run 且在未来 → 今天还有备份要做
        next_run_str = b.get("next_run")
        if next_run_str:
            try:
                from datetime import datetime as dt
                next_run = dt.fromisoformat(next_run_str)
                if next_run.date() == now.date():
                    return True
                # next_run 在今天之后 → 今天可能还需要做（如果 scheduler 漏了）
                if next_run.date() > now.date():
                    continue
            except (ValueError, TypeError):
                pass

        # 没有 next_run 但 schedule_enabled=true → 检查 schedule_rule
        rule = b.get("schedule_rule")
        if not rule:
            # 旧格式：只检查 schedule_time
            schedule_time = b.get("schedule_time", "01:00")
            if now.strftime("%H:%M") <= schedule_time:
                return True
            continue

        freq = rule.get("freq", "daily")
        time_str = rule.get("time", "01:00")

        if freq == "daily":
            if now.strftime("%H:%M") <= time_str:
                return True
        elif freq == "interval":
            start_date_str = rule.get("start_date", "")
            if start_date_str:
                from datetime import date
                start_date = date.fromisoformat(start_date_str)
                days_diff = (now.date() - start_date).days
                interval = rule.get("interval", 1)
                if days_diff >= 0 and days_diff % interval == 0:
                    if now.strftime("%H:%M") <= time_str:
                        return True
        elif freq == "weekly":
            weekdays = rule.get("weekdays", [])
            if today_weekday in weekdays:
                if now.strftime("%H:%M") <= time_str:
                    return True
        elif freq == "monthly":
            month_day = rule.get("month_day", 1)
            if now.day == month_day:
                if now.strftime("%H:%M") <= time_str:
                    return True

    return False


def has_upcoming_backup(hours: int = 12) -> bool:
    """Check if any backup is scheduled within the next N hours."""
    from datetime import datetime, timedelta
    backups = load_backups()
    now = datetime.now()
    deadline = now + timedelta(hours=hours)

    for b in backups:
        if not b.get("schedule_enabled"):
            continue

        # Primary: check next_run (ISO format)
        next_run_str = b.get("next_run")
        if next_run_str:
            try:
                next_run = datetime.fromisoformat(next_run_str)
                if now <= next_run <= deadline:
                    return True
            except (ValueError, TypeError):
                pass

        # Fallback: check schedule_rule for old data without next_run
        rule = b.get("schedule_rule")
        if rule:
            freq = rule.get("freq", "daily")
            time_str = rule.get("time", "01:00")
            h, m = time_str.split(":")
            target_time = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)

            if freq == "daily":
                if now <= target_time <= deadline:
                    return True
                tomorrow_time = target_time + timedelta(days=1)
                if now <= tomorrow_time <= deadline:
                    return True
            elif freq == "interval":
                start_date_str = rule.get("start_date", "")
                if start_date_str:
                    from datetime import date
                    start_date = date.fromisoformat(start_date_str)
                    days_diff = (now.date() - start_date).days
                    interval = rule.get("interval", 1)
                    if days_diff >= 0 and days_diff % interval == 0:
                        if now <= target_time <= deadline:
                            return True
            elif freq == "weekly":
                weekdays = rule.get("weekdays", [])
                today_weekday = now.weekday()
                if today_weekday in weekdays:
                    if now <= target_time <= deadline:
                        return True
            elif freq == "monthly":
                month_day = rule.get("month_day", 1)
                if now.day == month_day:
                    if now <= target_time <= deadline:
                        return True
        else:
            schedule_time = b.get("schedule_time", "01:00")
            h, m = schedule_time.split(":")
            target_time = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
            if now <= target_time <= deadline:
                return True

    return False


# === Settings ===

def load_settings() -> dict:
    from core.settings_manager import SettingsManager
    return SettingsManager.instance()._data


def save_settings(data: dict) -> None:
    from core.settings_manager import SettingsManager
    mgr = SettingsManager.instance()
    mgr._data.update(data)
    mgr._save()
