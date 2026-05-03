from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue

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


def safe_stat(path: Path):
    try:
        return path.stat()
    except (OSError, PermissionError, FileNotFoundError):
        return None


def safe_entry_stat(entry: os.DirEntry):
    """Fast stat for os.scandir entries."""
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
    path_obj = Path(path)
    return ScanItem(
        item_id=path,
        name=name,
        path=path,
        is_dir=is_dir,
        size=size,
        modified=modified,
        category_key=classify_key(path_obj),
    )


def get_folder_size(path: Path, stop_event: threading.Event | None = None) -> int:
    """
    Calculate folder size with one depth-first scandir pass.

    os.scandir is noticeably faster than repeatedly creating Path objects and
    calling Path.stat() for every file, especially on large folders.
    """
    total = 0
    stack: list[os.ScandirIterator] = []

    try:
        stack.append(os.scandir(path))
    except (OSError, PermissionError, FileNotFoundError):
        return 0

    try:
        while stack:
            if stop_event and stop_event.is_set():
                break

            iterator = stack[-1]
            try:
                entry = next(iterator)
            except StopIteration:
                iterator.close()
                stack.pop()
                continue
            except (OSError, PermissionError, FileNotFoundError):
                iterator.close()
                stack.pop()
                continue

            if safe_is_dir(entry):
                if should_skip_dir(entry.name):
                    continue
                try:
                    stack.append(os.scandir(entry.path))
                except (OSError, PermissionError, FileNotFoundError):
                    continue
            else:
                stat = safe_entry_stat(entry)
                if stat:
                    total += stat.st_size
    finally:
        for iterator in stack:
            iterator.close()

    return total


class DiskScanner:
    """
    High-volume scanner behavior:
    1. Files are emitted immediately with their real size.
    2. In quick mode, folders are emitted immediately with size=None.
    3. Folder sizes are calculated during the same scan pass and emitted later
       as update_size events.

    The important optimization is that every directory is scanned once. The old
    implementation started a separate os.walk() for each folder, so nested files
    could be counted many times on large directory trees.
    """

    def __init__(self, root_path: Path, output_queue: Queue, quick_mode: bool = True, folder_workers: int = 3):
        self.root_path = root_path
        self.output_queue = output_queue
        self.quick_mode = quick_mode
        # Kept for backwards compatibility with existing callers.
        self.folder_workers = max(1, folder_workers)
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        try:
            self._walk_once()
        finally:
            self.output_queue.put(("done", None))

    def _walk_once(self):
        root = str(self.root_path)

        try:
            root_iterator = os.scandir(root)
        except (OSError, PermissionError, FileNotFoundError):
            return

        stack: list[dict] = [
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

                entry_path = entry.path

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
                        child_iterator = os.scandir(entry_path)
                    except (OSError, PermissionError, FileNotFoundError):
                        if self.quick_mode:
                            self.output_queue.put(("update_size", (entry_path, 0)))
                        elif not self.quick_mode:
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
                frame["iterator"].close()
