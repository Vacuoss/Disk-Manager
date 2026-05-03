from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Iterable

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


def get_folder_size(path: Path, stop_event: threading.Event | None = None) -> int:
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            if stop_event and stop_event.is_set():
                break

            dirs[:] = [d for d in dirs if not should_skip_dir(d)]

            for file_name in files:
                if stop_event and stop_event.is_set():
                    break

                file_path = Path(root) / file_name
                stat = safe_stat(file_path)
                if stat:
                    total += stat.st_size
    except (OSError, PermissionError, FileNotFoundError):
        pass
    return total


class DiskScanner:
    """
    Fast mode behavior:
    1. File rows are emitted immediately with real size.
    2. Folder rows are emitted immediately with size=None.
    3. Folder sizes are calculated later by worker threads and emitted as updates.
    """

    def __init__(self, root_path: Path, output_queue: Queue, quick_mode: bool = True, folder_workers: int = 3):
        self.root_path = root_path
        self.output_queue = output_queue
        self.quick_mode = quick_mode
        self.folder_workers = max(1, folder_workers)
        self.stop_event = threading.Event()
        self.folder_queue: Queue[tuple[str, Path]] = Queue()

    def stop(self):
        self.stop_event.set()

    def run(self):
        workers = []
        if self.quick_mode:
            for _ in range(self.folder_workers):
                t = threading.Thread(target=self._folder_size_worker, daemon=True)
                t.start()
                workers.append(t)

        try:
            self._walk()
        finally:
            self.folder_queue.join()
            self.output_queue.put(("done", None))

    def _walk(self):
        for current_root, dirs, files in os.walk(self.root_path):
            if self.stop_event.is_set():
                break

            dirs[:] = [d for d in dirs if not should_skip_dir(d)]
            current = Path(current_root)

            for file_name in files:
                if self.stop_event.is_set():
                    break
                file_path = current / file_name
                stat = safe_stat(file_path)
                if not stat:
                    continue

                item = ScanItem(
                    item_id=str(file_path),
                    name=file_path.name,
                    path=str(file_path),
                    is_dir=False,
                    size=stat.st_size,
                    modified=stat.st_mtime,
                    category_key=classify_key(file_path),
                )
                self.output_queue.put(("add", item))

            for dir_name in dirs:
                if self.stop_event.is_set():
                    break

                folder_path = current / dir_name
                stat = safe_stat(folder_path)
                if not stat:
                    continue

                if self.quick_mode:
                    item = ScanItem(
                        item_id=str(folder_path),
                        name=folder_path.name,
                        path=str(folder_path),
                        is_dir=True,
                        size=None,
                        modified=stat.st_mtime,
                        category_key=classify_key(folder_path),
                    )
                    self.output_queue.put(("add", item))
                    self.folder_queue.put((str(folder_path), folder_path))
                else:
                    size = get_folder_size(folder_path, self.stop_event)
                    item = ScanItem(
                        item_id=str(folder_path),
                        name=folder_path.name,
                        path=str(folder_path),
                        is_dir=True,
                        size=size,
                        modified=stat.st_mtime,
                        category_key=classify_key(folder_path),
                    )
                    self.output_queue.put(("add", item))

    def _folder_size_worker(self):
        while not self.stop_event.is_set():
            try:
                item_id, folder_path = self.folder_queue.get(timeout=0.4)
            except Exception:
                continue

            try:
                size = get_folder_size(folder_path, self.stop_event)
                self.output_queue.put(("update_size", (item_id, size)))
            finally:
                self.folder_queue.task_done()
