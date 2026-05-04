from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Any

from classifier import classify_key
from config import SKIP_DIR_NAMES


@dataclass
class ScanItem:
    item_id: str
    name: str
    path: str
    is_dir: bool
    size: int | None
    modified: float
    category_key: str


def should_skip_dir(name: str) -> bool:
    return name.lower() in SKIP_DIR_NAMES


def safe_entry_stat(entry: os.DirEntry):
    try:
        return entry.stat(follow_symlinks=False)
    except (OSError, PermissionError, FileNotFoundError):
        return None


def safe_is_dir(entry: os.DirEntry) -> bool:
    try:
        return entry.is_dir(follow_symlinks=False)
    except (OSError, PermissionError, FileNotFoundError):
        return False


def make_item(path: str, name: str, is_dir: bool, size: int | None, modified: float) -> ScanItem:
    return ScanItem(
        item_id=path,
        name=name,
        path=path,
        is_dir=is_dir,
        size=size,
        modified=modified,
        category_key=classify_key(path, is_dir=is_dir),
    )


def _scanner_binary_candidates() -> list[Path]:
    base = Path(__file__).resolve().parent
    exe_name = "scanner_rs.exe" if sys.platform.startswith("win") else "scanner_rs"
    return [
        base / exe_name,
        base / "rust_scanner" / "target" / "release" / exe_name,
        base / "rust_scanner" / "target" / "debug" / exe_name,
    ]


def find_rust_scanner() -> Path | None:
    for candidate in _scanner_binary_candidates():
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


class DiskScanner:
    """
    Python adapter for the Rust scanner.

    GUI compatibility is preserved:
    - output_queue receives ("add", ScanItem)
    - output_queue receives ("update_size", (item_id, size))
    - output_queue receives ("done", None)

    If the Rust binary is missing, the class falls back to the built-in Python
    scanner so the app still works during development.
    """

    def __init__(self, root_path: Path, output_queue: Queue, quick_mode: bool = True, folder_workers: int = 3):
        self.root_path = root_path
        self.output_queue = output_queue
        self.quick_mode = quick_mode
        self.folder_workers = max(1, folder_workers)
        self.stop_event = threading.Event()
        self.process: subprocess.Popen[str] | None = None

    def stop(self):
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass

    def run(self):
        try:
            binary = find_rust_scanner()
            use_rust = os.environ.get("DISK_MANAGER_USE_RUST", "1") != "0"
            if binary and use_rust:
                self._run_rust(binary)
            else:
                self._walk_once_python_fallback()
        finally:
            self.output_queue.put(("done", None))

    def _run_rust(self, binary: Path):
        command = [
            str(binary),
            "--root",
            str(self.root_path),
            "--quick" if self.quick_mode else "--full",
            "--skip",
            ";".join(sorted(SKIP_DIR_NAMES)),
        ]

        startupinfo = None
        creationflags = 0
        if sys.platform.startswith("win"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        assert self.process.stdout is not None
        for line in self.process.stdout:
            if self.stop_event.is_set():
                break
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            self._handle_rust_event(payload)

        if self.stop_event.is_set():
            self.stop()

    def _handle_rust_event(self, payload: dict[str, Any]):
        event = payload.get("event")
        if event == "add":
            path = str(payload.get("path", ""))
            name = str(payload.get("name", Path(path).name))
            is_dir = bool(payload.get("is_dir", False))
            size = payload.get("size")
            modified = float(payload.get("modified") or 0.0)
            if not path:
                return
            self.output_queue.put(("add", make_item(path, name, is_dir, size, modified)))
        elif event == "update_size":
            path = str(payload.get("path", ""))
            size = int(payload.get("size") or 0)
            if path:
                self.output_queue.put(("update_size", (path, size)))
        elif event == "done":
            return

    def _walk_once_python_fallback(self):
        root = str(self.root_path)
        try:
            root_iterator = os.scandir(root)
        except (OSError, PermissionError, FileNotFoundError):
            return

        stack: list[dict[str, Any]] = [
            {
                "path": root,
                "name": self.root_path.name,
                "iterator": root_iterator,
                "total": 0,
                "stat": None,
                "emit_folder": False,
            }
        ]

        try:
            while stack:
                if self.stop_event.is_set():
                    break

                frame = stack[-1]
                iterator = frame["iterator"]

                try:
                    entry = next(iterator)
                except StopIteration:
                    iterator.close()
                    stack.pop()

                    folder_size = frame["total"]
                    if frame["emit_folder"]:
                        if self.quick_mode:
                            self.output_queue.put(("update_size", (frame["path"], folder_size)))
                        else:
                            stat = frame["stat"]
                            self.output_queue.put(
                                (
                                    "add",
                                    make_item(
                                        path=frame["path"],
                                        name=frame["name"],
                                        is_dir=True,
                                        size=folder_size,
                                        modified=stat.st_mtime,
                                    ),
                                )
                            )

                    if stack:
                        stack[-1]["total"] += folder_size
                    continue
                except (OSError, PermissionError, FileNotFoundError):
                    iterator.close()
                    stack.pop()
                    continue

                entry_path = entry.path.replace("\\", "/")

                if safe_is_dir(entry):
                    if should_skip_dir(entry.name):
                        continue

                    stat = safe_entry_stat(entry)
                    if not stat:
                        continue

                    if self.quick_mode:
                        self.output_queue.put(
                            (
                                "add",
                                make_item(
                                    path=entry_path,
                                    name=entry.name,
                                    is_dir=True,
                                    size=None,
                                    modified=stat.st_mtime,
                                ),
                            )
                        )

                    try:
                        child_iterator = os.scandir(entry.path)
                    except (OSError, PermissionError, FileNotFoundError):
                        if self.quick_mode:
                            self.output_queue.put(("update_size", (entry_path, 0)))
                        else:
                            self.output_queue.put(
                                (
                                    "add",
                                    make_item(
                                        path=entry_path,
                                        name=entry.name,
                                        is_dir=True,
                                        size=0,
                                        modified=stat.st_mtime,
                                    ),
                                )
                            )
                        continue

                    stack.append(
                        {
                            "path": entry_path,
                            "name": entry.name,
                            "iterator": child_iterator,
                            "total": 0,
                            "stat": stat,
                            "emit_folder": True,
                        }
                    )
                else:
                    stat = safe_entry_stat(entry)
                    if not stat:
                        continue

                    size = stat.st_size
                    frame["total"] += size
                    self.output_queue.put(
                        (
                            "add",
                            make_item(
                                path=entry_path,
                                name=entry.name,
                                is_dir=False,
                                size=size,
                                modified=stat.st_mtime,
                            ),
                        )
                    )
        finally:
            for frame in stack:
                try:
                    frame["iterator"].close()
                except Exception:
                    pass
