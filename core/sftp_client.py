from __future__ import annotations

import paramiko
import os
import stat
import socket
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Any
import logging

logger = logging.getLogger("shiyun.sftp")


@dataclass
class FileInfo:
    name: str
    size: int
    mtime: float
    is_dir: bool
    permissions: str


@dataclass
class BackupFile:
    remote: str
    local: str
    status: str  # "new" | "updated" | "skipped"


class SFTPClient:
    def __init__(self):
        self._transport: paramiko.Transport | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._connected = False
        self._lock = threading.RLock()
        self._aborted = False
        # Connection pool for parallel downloads
        self._pool: list[paramiko.SFTPClient] = []
        self._pool_lock = threading.Lock()
        self._host: str = ""
        self._port: int = 22
        self._username: str = ""
        self._password: str = ""

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, host: str, port: int, username: str, password: str,
                timeout: int = 10) -> None:
        # Clean up any existing connection
        self._connected = False
        self._sftp = None
        self._transport = None
        self._aborted = False
        self._close_pool()
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._transport = paramiko.Transport((host, port))
        self._transport.connect(username=username, password=password)
        self._transport.set_keepalive(30)
        self._sftp = paramiko.SFTPClient.from_transport(self._transport)
        self._sftp.get_channel().settimeout(30)
        self._connected = True

    def abort(self) -> None:
        """Abort current operation. Closes socket to interrupt blocked writes,
        then cleans up SFTP and transport. Non-blocking where possible."""
        self._aborted = True
        self._connected = False
        self._close_pool()
        # Close socket first — interrupts any blocked write/read
        try:
            if self._transport and self._transport.sock:
                self._transport.sock.close()
        except Exception:
            pass
        # Close SFTP
        try:
            if self._sftp:
                self._sftp.close()
        except Exception:
            pass
        # Close transport
        try:
            if self._transport:
                self._transport.close()
        except Exception:
            pass
        # Clear references so UI operations see "not connected"
        self._sftp = None
        self._transport = None

    def disconnect(self) -> None:
        self._connected = False
        self._close_pool()
        try:
            if self._sftp:
                self._sftp.close()
        except Exception:
            pass
        self._sftp = None
        try:
            if self._transport:
                self._transport.close()
        except Exception:
            pass
        self._transport = None

    # === Connection Pool ===

    def _create_pool_conn(self) -> paramiko.SFTPClient:
        """Create a new independent SFTP connection for parallel downloads."""
        transport = paramiko.Transport((self._host, self._port))
        transport.connect(username=self._username, password=self._password)
        transport.set_keepalive(30)
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.get_channel().settimeout(30)
        return sftp

    def _acquire_pool(self) -> paramiko.SFTPClient:
        """Get an SFTP connection from the pool, or create a new one."""
        with self._pool_lock:
            if self._pool:
                return self._pool.pop()
        return self._create_pool_conn()

    def _release_pool(self, conn: paramiko.SFTPClient) -> None:
        """Return an SFTP connection to the pool."""
        if self._connected and not self._aborted:
            with self._pool_lock:
                self._pool.append(conn)
        else:
            try:
                conn.close()
            except Exception:
                pass

    def _close_pool(self) -> None:
        """Close all pooled connections."""
        with self._pool_lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()

    def list_dir(self, remote_path: str = ".") -> list[FileInfo]:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            entries = []
            for attr in self._sftp.listdir_attr(remote_path):
                name = attr.filename
                if name in (".", ".."):
                    continue
                is_dir = stat.S_ISDIR(attr.st_mode)
                size = attr.st_size or 0
                mtime = attr.st_mtime or 0
                permissions = attr.st_mode
                entries.append(FileInfo(
                    name=name, size=size, mtime=mtime,
                    is_dir=is_dir, permissions=oct(permissions)[-3:]
                ))
            entries.sort(key=lambda x: (not x.is_dir, x.name.lower()))
            return entries

    def download_file(self, remote_path: str, local_path: str,
                      progress_callback: Callable[[int, int], Any] | None = None,
                      timeout: int = 60,
                      on_error: Callable[[Exception, str], str] | None = None,
                      skip_all: list[bool] | None = None,
                      pool_sftp: paramiko.SFTPClient | None = None) -> None:
        """
        Download a file with resume support.
        pool_sftp: use this SFTP connection instead of self._sftp (for parallel downloads).
        """
        if skip_all is None:
            skip_all = [False]
        sftp = pool_sftp or self._sftp

        def _handle_error(err):
            if self._aborted:
                raise err
            if skip_all[0]:
                return "skip"
            if on_error:
                action = on_error(err, remote_path)
                if action == "skip_all":
                    skip_all[0] = True
                return action
            raise err

        while True:
            # Phase 1: validate, check sizes, prepare resume offset
            part_path = local_path + ".filepart"
            resume_offset = 0
            remote_size = 0

            with self._lock:
                if not self._connected or not sftp:
                    raise ConnectionError("未连接到服务器")
                local_path = os.path.abspath(local_path)
                local_dir = os.path.dirname(local_path)
                if local_dir:
                    os.makedirs(local_dir, exist_ok=True)

                try:
                    remote_size = sftp.stat(remote_path).st_size or 0
                    self._check_disk_space(local_dir or ".", remote_size)
                except OSError as e:
                    result = _handle_error(e)
                    if result == "retry":
                        continue
                    elif result == "abort":
                        raise e
                    return  # skip
                except Exception:
                    pass

                if os.path.exists(part_path):
                    local_partial = os.path.getsize(part_path)
                    if 0 < local_partial < remote_size:
                        resume_offset = local_partial
                    elif local_partial >= remote_size:
                        try:
                            os.replace(part_path, local_path)
                            return
                        except OSError:
                            pass

            # Phase 2: download with resume offset
            error = [None]
            _resume_offset = resume_offset
            _remote_size = remote_size
            _sftp = sftp

            def _do_download():
                def _progress(transferred, total):
                    if not self._connected:
                        raise ConnectionError("连接已断开")
                    if progress_callback:
                        progress_callback(transferred + _resume_offset, _remote_size)
                try:
                    if _resume_offset > 0:
                        with _sftp.open(remote_path, "rb") as rf:
                            rf.seek(_resume_offset)
                            with open(part_path, "ab") as lf:
                                while True:
                                    chunk = rf.read(1024 * 1024)
                                    if not chunk:
                                        break
                                    lf.write(chunk)
                                    if progress_callback:
                                        progress_callback(lf.tell(), _remote_size)
                    else:
                        _sftp.get(remote_path, part_path, callback=_progress)
                except Exception as e:
                    error[0] = e

            t = threading.Thread(target=_do_download, daemon=True)
            t.start()
            t.join(timeout)

            if t.is_alive():
                # Timeout — keep .filepart for resume next time
                # Close socket to interrupt blocked I/O (per-connection, not global)
                try:
                    if pool_sftp:
                        ch = pool_sftp.get_channel()
                        if ch and ch.transport and ch.transport.sock:
                            ch.transport.sock.settimeout(0.1)
                    elif self._transport and self._transport.sock:
                        self._transport.sock.settimeout(0.1)
                except Exception:
                    pass
                t.join(3)
                err = TimeoutError(f"下载超时({timeout}秒): {os.path.basename(remote_path)}")
                result = _handle_error(err)
                if result == "retry":
                    continue
                elif result == "abort":
                    try:
                        os.remove(part_path)
                    except OSError:
                        pass
                    raise err
                return  # skip

            if error[0]:
                # Failed — keep .filepart for resume
                result = _handle_error(error[0])
                if result == "retry":
                    continue
                elif result == "abort":
                    try:
                        os.remove(part_path)
                    except OSError:
                        pass
                    raise error[0]
                return  # skip

            # Phase 3: rename .filepart to final name
            try:
                os.replace(part_path, local_path)
            except OSError:
                try:
                    os.remove(part_path)
                except OSError:
                    pass
                file_locked = PermissionError(f"文件被占用，无法写入: {os.path.basename(local_path)}")
                result = _handle_error(file_locked)
                if result == "retry":
                    continue
                elif result == "abort":
                    raise file_locked
                return  # skip
            break  # Success

    def upload_file(self, local_path: str, remote_path: str,
                    progress_callback: Callable[[int, int], Any] | None = None,
                    timeout: int = 60,
                    on_error: Callable[[Exception, str], str] | None = None) -> None:
        """
        Upload a file with optional error callback.

        on_error: callable(error, file_path) -> str
            Returns "abort", "retry", "skip", or "skip_all".
        """
        skip_all = [False]

        def _handle_error(err):
            if self._aborted:
                raise err
            if on_error and not skip_all[0]:
                action = on_error(err, remote_path)
                if action == "skip_all":
                    skip_all[0] = True
                return action
            raise err

        while True:
            with self._lock:
                if not self._connected or not self._sftp:
                    raise ConnectionError("未连接到服务器")
                if not os.path.exists(local_path):
                    raise FileNotFoundError(f"本地文件不存在: {local_path}")
                local_size = os.path.getsize(local_path)

            error = [None]

            def _do_upload():
                def _progress(transferred, total):
                    if progress_callback:
                        progress_callback(transferred, local_size)
                try:
                    self._sftp.put(local_path, remote_path, callback=_progress)
                except Exception as e:
                    error[0] = e

            t = threading.Thread(target=_do_upload, daemon=True)
            t.start()
            t.join(timeout)
            if t.is_alive():
                err = TimeoutError(f"上传超时({timeout}秒): {os.path.basename(remote_path)}")
                result = _handle_error(err)
                if result == "retry":
                    continue
                elif result == "abort":
                    raise err
                return  # skip
            if error[0]:
                result = _handle_error(error[0])
                if result == "retry":
                    continue
                elif result == "abort":
                    raise error[0]
                return  # skip
            break  # Success

    def delete(self, remote_path: str) -> None:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            attr = self._sftp.stat(remote_path)
            if stat.S_ISLNK(attr.st_mode):
                self._sftp.remove(remote_path)
                return
            if stat.S_ISDIR(attr.st_mode):
                for item in self._sftp.listdir_attr(remote_path):
                    self.delete(os.path.join(remote_path, item.filename))
                self._sftp.rmdir(remote_path)
            else:
                self._sftp.remove(remote_path)

    def mkdir(self, remote_path: str) -> None:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            self._sftp.mkdir(remote_path)

    def rename(self, old_path: str, new_path: str) -> None:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            self._sftp.rename(old_path, new_path)

    def copy(self, remote_src: str, remote_dst: str) -> None:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            src_attr = self._sftp.stat(remote_src)
            if stat.S_ISDIR(src_attr.st_mode):
                self._sftp.mkdir(remote_dst)
                for item in self._sftp.listdir_attr(remote_src):
                    if item.filename in (".", ".."):
                        continue
                    src_item = f"{remote_src.rstrip('/')}/{item.filename}"
                    dst_item = f"{remote_dst.rstrip('/')}/{item.filename}"
                    self.copy(src_item, dst_item)
            else:
                self._sftp.get(remote_src, remote_dst)

    def read_file(self, remote_path: str) -> str:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            with self._sftp.open(remote_path, "r") as f:
                return f.read().decode("utf-8", errors="replace")

    def write_file(self, remote_path: str, content: str) -> None:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            with self._sftp.open(remote_path, "w") as f:
                f.write(content)

    def stat(self, remote_path: str) -> paramiko.SFTPAttributes:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            return self._sftp.stat(remote_path)

    @staticmethod
    def _check_disk_space(path: str, required_bytes: int) -> None:
        """Check if enough disk space is available. Raises OSError if not."""
        if required_bytes <= 0:
            return
        target = path if os.path.isdir(path) else os.path.dirname(path) or "."
        try:
            usage = os.statvfs(target)
            free = usage.f_bavail * usage.f_frsize
            if free < required_bytes:
                need_mb = required_bytes / (1024 * 1024)
                free_mb = free / (1024 * 1024)
                raise OSError(f"磁盘空间不足: 需要 {need_mb:.1f} MB，可用 {free_mb:.1f} MB")
        except AttributeError:
            # Windows doesn't have statvfs, use shutil
            import shutil
            total, used, free = shutil.disk_usage(target)
            if free < required_bytes:
                need_mb = required_bytes / (1024 * 1024)
                free_mb = free / (1024 * 1024)
                raise OSError(f"磁盘空间不足: 需要 {need_mb:.1f} MB，可用 {free_mb:.1f} MB")

    def count_files(self, remote_path: str) -> int:
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            count = 0
            for attr in self._sftp.listdir_attr(remote_path):
                name = attr.filename
                if name in (".", ".."):
                    continue
                full_path = f"{remote_path.rstrip('/')}/{name}"
                if stat.S_ISDIR(attr.st_mode):
                    count += self.count_files(full_path)
                else:
                    count += 1
            return count

    def download_dir(self, remote_path: str, local_path: str,
                     progress_callback: Callable[[int, int], Any] | None = None,
                     file_progress: Callable[[int, int], Any] | None = None,
                     on_error: Callable[[Exception, str], str] | None = None) -> list[str]:
        """
        Download a directory recursively with optional error callback.

        progress_callback: (done_count, total) — file completion (incremental per call)
        file_progress: (transferred, total) — current file byte progress
        on_error: callable(error, file_path) -> str
        """
        # Phase 1: validate and get file list (under lock)
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            if os.path.isfile(local_path):
                raise FileExistsError(f"无法创建目录，'{local_path}' 已是一个文件")
            os.makedirs(local_path, exist_ok=True)
            files = self.list_dir(remote_path)

        # Phase 2: download each file (lock released — allows concurrent progress)
        errors = []
        skip_all = [False]
        done_count = 0
        for f in files:
            remote_item = f"{remote_path.rstrip('/')}/{f.name}"
            local_item = os.path.join(local_path, f.name)
            try:
                if f.is_dir:
                    sub = self.download_dir(remote_item, local_item,
                                            progress_callback, file_progress, on_error)
                    errors.extend(sub)
                else:
                    def _file_error(err, path, _skip=skip_all):
                        if _skip[0]:
                            return "skip_all"
                        if on_error:
                            return on_error(err, path)
                        return "abort"
                    self.download_file(remote_item, local_item,
                                       progress_callback=file_progress,
                                       on_error=_file_error if on_error else None,
                                       skip_all=skip_all)
                    done_count += 1
                    if progress_callback:
                        progress_callback(done_count, 0)
            except Exception as e:
                if self._aborted:
                    raise
                if on_error and not skip_all[0]:
                    action = on_error(e, remote_item)
                    if action == "skip_all":
                        skip_all[0] = True
                    elif action == "skip":
                        pass
                    elif action == "retry":
                        pass
                    else:
                        errors.append(f"{f.name}: {e}")
                else:
                    errors.append(f"{f.name}: {e}")
        return errors

    def _collect_files_for_backup(self, remote_path: str, local_path: str,
                                  result: list[tuple[str, str]]) -> None:
        """Recursively collect files for backup into (remote, local) pairs."""
        with self._lock:
            if not self._connected or not self._sftp:
                return
            try:
                os.makedirs(local_path, exist_ok=True)
                for attr in self._sftp.listdir_attr(remote_path):
                    name = attr.filename
                    if name in (".", ".."):
                        continue
                    remote_item = f"{remote_path.rstrip('/')}/{name}"
                    local_item = os.path.join(local_path, name)
                    if stat.S_ISDIR(attr.st_mode):
                        self._collect_files_for_backup(remote_item, local_item, result)
                    else:
                        result.append((remote_item, local_item))
            except Exception as e:
                logger.warning(f"收集备份文件失败 {remote_path}: {e}")

    def _collect_files_for_backup_incremental(self, remote_path: str, local_path: str,
                                               result: list[BackupFile]) -> None:
        """Recursively collect files with mtime-based classification for incremental backup."""
        MTIME_TOLERANCE = 2.0  # seconds — filesystem timestamp granularity (FAT32, etc.)
        with self._lock:
            if not self._connected or not self._sftp:
                return
            try:
                os.makedirs(local_path, exist_ok=True)
                for attr in self._sftp.listdir_attr(remote_path):
                    name = attr.filename
                    if name in (".", ".."):
                        continue
                    remote_item = f"{remote_path.rstrip('/')}/{name}"
                    local_item = os.path.join(local_path, name)
                    if stat.S_ISDIR(attr.st_mode):
                        self._collect_files_for_backup_incremental(remote_item, local_item, result)
                    else:
                        remote_mtime = attr.st_mtime or 0
                        if not os.path.exists(local_item):
                            result.append(BackupFile(remote_item, local_item, "new"))
                        else:
                            local_mtime = os.path.getmtime(local_item)
                            if remote_mtime > local_mtime + MTIME_TOLERANCE:
                                result.append(BackupFile(remote_item, local_item, "updated"))
                            else:
                                result.append(BackupFile(remote_item, local_item, "skipped"))
            except Exception as e:
                logger.warning(f"收集增量备份文件失败 {remote_path}: {e}")

    def download_parallel(self, files: list[tuple[str, str]],
                          progress_callback: Callable[[int, int], Any] | None = None,
                          file_progress: Callable[[str, int, int], Any] | None = None,
                          on_error: Callable[[Exception, str], str] | None = None,
                          max_workers: int = 3) -> list[str]:
        """
        Download files in parallel with limited concurrency.
        files: [(remote_path, local_path), ...]
        Immediately interrupts all downloads on first error.
        """
        if not files:
            return []

        errors: list[str] = []
        done_count = [0]
        total = len(files)
        stop_event = threading.Event()
        error_lock = threading.Lock()

        def _download_one(remote: str, local: str) -> None:
            if stop_event.is_set() or self._aborted:
                return
            conn = self._acquire_pool()
            try:
                def _file_progress(transferred: int, total_bytes: int) -> None:
                    if file_progress and not stop_event.is_set():
                        file_progress(os.path.basename(remote), transferred, total_bytes)

                def _on_file_error(err: Exception, path: str) -> str:
                    with error_lock:
                        if stop_event.is_set():
                            return "abort"
                    if on_error:
                        action = on_error(err, path)
                        if action == "skip_all":
                            stop_event.set()
                        elif action == "skip":
                            stop_event.set()
                            return "skip"
                        elif action == "abort":
                            stop_event.set()
                            return "abort"
                        return action
                    stop_event.set()
                    return "abort"

                self.download_file(
                    remote, local,
                    progress_callback=_file_progress,
                    on_error=_on_file_error,
                    pool_sftp=conn,
                )
                with error_lock:
                    done_count[0] += 1
                    if progress_callback:
                        progress_callback(done_count[0], total)
            except Exception as e:
                with error_lock:
                    if not stop_event.is_set():
                        stop_event.set()
                        errors.append(f"{os.path.basename(remote)}: {e}")
            finally:
                self._release_pool(conn)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_download_one, remote, local): (remote, local)
                for remote, local in files
            }
            try:
                for future in as_completed(futures):
                    if stop_event.is_set():
                        break
                    future.result()
            except Exception:
                stop_event.set()

        return errors

    def upload_parallel(self, files: list[tuple[str, str]],
                        progress_callback: Callable[[int, int], Any] | None = None,
                        file_progress: Callable[[str, int, int], Any] | None = None,
                        on_error: Callable[[Exception, str], str] | None = None,
                        max_workers: int = 3) -> list[str]:
        """Upload files in parallel. files: [(local_path, remote_path), ...]"""
        if not files:
            return []

        errors: list[str] = []
        done_count = [0]
        total = len(files)
        stop_event = threading.Event()
        error_lock = threading.Lock()

        def _upload_one(local: str, remote: str) -> None:
            if stop_event.is_set() or self._aborted:
                return
            conn = self._acquire_pool()
            try:
                def _file_progress(transferred: int, total_bytes: int) -> None:
                    if file_progress and not stop_event.is_set():
                        file_progress(os.path.basename(local), transferred, total_bytes)

                def _on_file_error(err: Exception, path: str) -> str:
                    with error_lock:
                        if stop_event.is_set():
                            return "abort"
                    if on_error:
                        action = on_error(err, path)
                        if action in ("skip_all", "abort"):
                            stop_event.set()
                        return action
                    stop_event.set()
                    return "abort"

                sftp = conn
                sftp.put(local, remote)
                with error_lock:
                    done_count[0] += 1
                    if progress_callback:
                        progress_callback(done_count[0], total)
            except Exception as e:
                with error_lock:
                    if not stop_event.is_set():
                        stop_event.set()
                        errors.append(f"{os.path.basename(local)}: {e}")
            finally:
                self._release_pool(conn)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_upload_one, local, remote): (local, remote)
                for local, remote in files
            }
            try:
                for future in as_completed(futures):
                    if stop_event.is_set():
                        break
                    future.result()
            except Exception:
                stop_event.set()

        return errors

    def mkdir_remote(self, remote_path: str) -> None:
        """Recursively create remote directories (like mkdir -p)."""
        with self._lock:
            if not self._connected or not self._sftp:
                raise ConnectionError("未连接到服务器")
            parts = [p for p in remote_path.replace("\\", "/").split("/") if p]
            current = ""
            for part in parts:
                current += "/" + part
                try:
                    self._sftp.stat(current)
                except FileNotFoundError:
                    self._sftp.mkdir(current)

    def verify_download(self, remote_path: str, local_path: str) -> list[str]:
        """Verify downloaded files match remote by size. Returns list of mismatched file paths."""
        mismatches = []
        with self._lock:
            if not self._connected or not self._sftp:
                return []
            try:
                attr = self._sftp.stat(remote_path)
                if stat.S_ISDIR(attr.st_mode):
                    if not os.path.isdir(local_path):
                        mismatches.append(f"{remote_path}: local dir missing")
                        return mismatches
                    for item in self._sftp.listdir_attr(remote_path):
                        name = item.filename
                        if name in (".", ".."):
                            continue
                        remote_item = f"{remote_path.rstrip('/')}/{name}"
                        local_item = os.path.join(local_path, name)
                        sub = self.verify_download(remote_item, local_item)
                        mismatches.extend(sub)
                else:
                    if not os.path.isfile(local_path):
                        # Skip files that don't exist locally — download errors already cover this
                        pass
                    elif (attr.st_size or 0) != os.path.getsize(local_path):
                        remote_size = attr.st_size or 0
                        local_size = os.path.getsize(local_path)
                        mismatches.append(
                            f"{remote_path}: size mismatch (remote={remote_size}, local={local_size})"
                        )
            except Exception as e:
                mismatches.append(f"{remote_path}: verify error: {e}")
        return mismatches
