from __future__ import annotations

import os
import shutil
import string
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk
from config import APP_TITLE, DEFAULT_PATH, LANG_EN, LANG_JA, MAX_VISIBLE_ROWS, SORT_KEYS, TEXT
from scanner import DiskScanner, ScanItem


class ModernDiskAnalyzer(tk.Tk):
    def __init__(self):
        super().__init__()

        self.language = LANG_EN
        self.title(APP_TITLE)
        self.geometry("1280x820")
        self.minsize(1000, 620)
        self.path_var = tk.StringVar(value=DEFAULT_PATH)
        self.search_var = tk.StringVar()
        self.exclude_var = tk.StringVar()
        self.sort_var = tk.StringVar(value="size")
        self.quick_mode_var = tk.BooleanVar(value=True)
        self.auto_refresh_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value=self.t("status_ready"))
        self.queue: Queue = Queue()
        self.scanner: DiskScanner | None = None
        self.scan_thread: threading.Thread | None = None
        self.items: dict[str, dict] = {}
        self.drive_bars: dict[str, dict] = {}
        self.scanning_active = False
        self.auto_refresh_check_running = False
        self.last_scan_path: Path | None = None
        self.last_snapshot: dict[str, tuple[bool, int, int]] = {}
        self._apply_window_icon()
        self._configure_style()
        self._build_ui()
        self._poll_queue()
        self._auto_refresh_tick()

    def t(self, key: str) -> str:
        return TEXT[self.language].get(key, key)

    def _resource_path(self, relative_path: str) -> Path:
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return base_path / relative_path

    def _apply_window_icon(self):
        possible_icons = [
            self._resource_path("assets/disck_manager.ico"),
            self._resource_path("assets/disk_manager.ico"),
            self._resource_path("assets/icon.ico"),
            self._resource_path("disck_manager.ico"),
            self._resource_path("disk_manager.ico"),
            self._resource_path("icon.ico"),
        ]

        for icon_path in possible_icons:
            if icon_path.exists():
                try:
                    self.iconbitmap(str(icon_path))
                    return
                except Exception:
                    pass

    def _configure_style(self):
        self.configure(bg="#111827")
        style = ttk.Style(self)
        style.theme_use("clam")

        bg = "#111827"
        border = "#374151"
        text = "#e5e7eb"
        muted = "#9ca3af"

        button_bg = "#1f2937"
        button_hover = "#273244"
        button_pressed = "#374151"

        accent_bg = "#2563eb"
        accent_hover = "#2b6eea"
        accent_pressed = "#1d4ed8"

        style.configure("App.TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=bg, foreground="#f9fafb", font=("Segoe UI", 20, "bold"))
        style.configure("Hint.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))

        style.configure(
            "TButton",
            background=button_bg,
            foreground=text,
            bordercolor=border,
            relief="flat",
            font=("Segoe UI", 10),
            padding=(12, 8),
        )
        style.map(
            "TButton",
            background=[
                ("active", button_hover),
                ("pressed", button_pressed),
                ("disabled", "#1f2937"),
            ],
            foreground=[("disabled", "#6b7280")],
        )

        style.configure(
            "Accent.TButton",
            background=accent_bg,
            foreground="#ffffff",
            bordercolor=accent_bg,
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            padding=(12, 8),
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", accent_hover),
                ("pressed", accent_pressed),
                ("disabled", "#1e3a8a"),
            ],
            foreground=[("disabled", "#93c5fd")],
        )

        style.configure("TCheckbutton", background=bg, foreground=text, font=("Segoe UI", 10))
        style.map(
            "TCheckbutton",
            background=[("active", bg)],
            foreground=[("active", "#f9fafb")],
        )

        style.configure(
            "TEntry",
            fieldbackground="#f9fafb",
            foreground="#111827",
            bordercolor="#374151",
            padding=6,
        )

        style.configure(
            "TCombobox",
            fieldbackground="#f9fafb",
            foreground="#111827",
            arrowcolor="#111827",
            bordercolor="#374151",
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", "#f9fafb")],
            selectbackground=[("readonly", "#f9fafb")],
            selectforeground=[("readonly", "#111827")],
        )

        style.configure(
            "Treeview",
            background=bg,
            fieldbackground=bg,
            foreground=text,
            rowheight=30,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#374151",
            foreground="#f9fafb",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", "#1d4ed8")],
            foreground=[("selected", "#ffffff")],
        )
        style.map("Treeview.Heading", background=[("active", "#4b5563")])

        style.configure(
            "Horizontal.TProgressbar",
            background="#2563eb",
            troughcolor="#1f2937",
            bordercolor="#1f2937",
        )

    def _build_ui(self):
        self.header = ttk.Frame(self, style="App.TFrame", padding=(18, 14))
        self.header.pack(fill="x")
        self.title_label = ttk.Label(self.header, text=self.t("title"), style="Title.TLabel")
        self.title_label.pack(side="left")
        self.lang_button = ttk.Button(self.header, text=self.t("language"), command=self.toggle_language)
        self.lang_button.pack(side="right")
        controls = ttk.Frame(self, style="App.TFrame", padding=(18, 6))
        controls.pack(fill="x")
        self.path_label = ttk.Label(controls, text=self.t("path"))
        self.path_label.grid(row=0, column=0, sticky="w")
        self.path_entry = ttk.Entry(controls, textvariable=self.path_var)
        self.path_entry.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(4, 0))
        self.browse_button = ttk.Button(controls, text=self.t("browse"), command=self.browse_path)
        self.browse_button.grid(row=1, column=1, padx=4, pady=(4, 0))
        self.scan_button = ttk.Button(controls, text=self.t("scan"), command=self.start_scan, style="Accent.TButton")
        self.scan_button.grid(row=1, column=2, padx=4, pady=(4, 0))
        self.stop_button = ttk.Button(controls, text=self.t("stop"), command=self.stop_scan)
        self.stop_button.grid(row=1, column=3, padx=4, pady=(4, 0))

        controls.columnconfigure(0, weight=1)

        filters = ttk.Frame(self, style="App.TFrame", padding=(18, 10))
        filters.pack(fill="x")
        self.search_label = ttk.Label(filters, text=self.t("search"))
        self.search_label.grid(row=0, column=0, sticky="w")
        self.search_entry = ttk.Entry(filters, textvariable=self.search_var, width=30)
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=(0, 12), pady=(4, 0))
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh_table())
        self.exclude_label = ttk.Label(filters, text="Exclude path words")
        self.exclude_label.grid(row=0, column=1, sticky="w")
        self.exclude_entry = ttk.Entry(filters, textvariable=self.exclude_var, width=28)
        self.exclude_entry.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(4, 0))
        self.exclude_entry.bind("<KeyRelease>", lambda _e: self.refresh_table())
        self.sort_label = ttk.Label(filters, text=self.t("sort_by"))
        self.sort_label.grid(row=0, column=2, sticky="w")
        self.sort_box = ttk.Combobox(
            filters,
            textvariable=self.sort_var,
            values=SORT_KEYS,
            state="readonly",
            width=18,
        )
        self.sort_box.grid(row=1, column=2, sticky="w", pady=(4, 0))
        self.sort_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_table())
        self.quick_check = ttk.Checkbutton(filters, text=self.t("quick_mode"), variable=self.quick_mode_var)
        self.quick_check.grid(row=1, column=3, sticky="w", padx=18, pady=(4, 0))
        self.auto_refresh_check = ttk.Checkbutton(
            filters,
            text="Auto refresh",
            variable=self.auto_refresh_var,
        )
        self.auto_refresh_check.grid(row=1, column=4, sticky="w", padx=(0, 0), pady=(4, 0))
        self.hint_label = ttk.Label(filters, text=self.t("all_disk_hint"), style="Hint.TLabel")
        self.hint_label.grid(row=2, column=0, columnspan=5, sticky="w", pady=(8, 0))

        filters.columnconfigure(0, weight=1)
        filters.columnconfigure(1, weight=1)

        table_frame = ttk.Frame(self, style="App.TFrame", padding=(18, 8))
        table_frame.pack(fill="both", expand=True)

        columns = ("name", "type", "size", "modified", "category", "path")

        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self.open_selected_in_explorer)
        self.tree.bind("<Return>", self.open_selected_in_explorer)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self._apply_headers()
        self.tree.column("name", width=240)
        self.tree.column("type", width=110)
        self.tree.column("size", width=130)
        self.tree.column("modified", width=170)
        self.tree.column("category", width=170)
        self.tree.column("path", width=560)

        footer = ttk.Frame(self, style="App.TFrame", padding=(18, 10))
        footer.pack(fill="x")

        self.status_label = ttk.Label(
            footer,
            textvariable=self.status_var,
            style="Hint.TLabel",
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.progress = ttk.Progressbar(
            footer,
            mode="determinate",
            length=220,
            maximum=100,
            value=0,
            style="Horizontal.TProgressbar",
        )
        self.progress.pack(side="right")

        self.drive_frame = ttk.Frame(self, style="App.TFrame", padding=(18, 4))
        self.drive_frame.pack(fill="x")

        self._build_drive_usage_panel()

    def _apply_headers(self):
        self.tree.heading("name", text=self.t("name"))
        self.tree.heading("type", text=self.t("type"))
        self.tree.heading("size", text=self.t("size"))
        self.tree.heading("modified", text=self.t("modified"))
        self.tree.heading("category", text=self.t("category"))
        self.tree.heading("path", text=self.t("full_path"))

    def toggle_language(self):
        self.language = LANG_JA if self.language == LANG_EN else LANG_EN
        self.title(self.t("title"))
        self.title_label.configure(text=self.t("title"))
        self.lang_button.configure(text=self.t("language"))
        self.path_label.configure(text=self.t("path"))
        self.browse_button.configure(text=self.t("browse"))
        self.scan_button.configure(text=self.t("scan"))
        self.stop_button.configure(text=self.t("stop"))
        self.search_label.configure(text=self.t("search"))
        self.sort_label.configure(text=self.t("sort_by"))
        self.quick_check.configure(text=self.t("quick_mode"))
        self.hint_label.configure(text=self.t("all_disk_hint"))
        self.exclude_label.configure(text="除外するパスの単語" if self.language == LANG_JA else "Exclude path words")
        self.auto_refresh_check.configure(text="自動更新" if self.language == LANG_JA else "Auto refresh")
        self._apply_headers()
        self.refresh_table()
        self.update_drive_usage()

    def browse_path(self):
        selected = filedialog.askdirectory(title=self.t("select_folder"))
        if selected:
            self.path_var.set(selected)

    def start_scan(self):
        path = Path(self.path_var.get())

        if not path.exists():
            messagebox.showerror("Error", self.t("error_path"))
            return

        self._begin_scan(path, self.t("status_scanning"), clear_table=True)

    def _begin_scan(self, path: Path, status: str, clear_table: bool):
        self.stop_scan(clear_status=False)

        if clear_table:
            self.items.clear()
            self.tree.delete(*self.tree.get_children())

        self.last_scan_path = path
        self.status_var.set(status)
        self.scanning_active = True
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(12)
        self.scanner = DiskScanner(path, self.queue, quick_mode=self.quick_mode_var.get())
        self.scan_thread = threading.Thread(target=self.scanner.run, daemon=True)
        self.scan_thread.start()

    def stop_scan(self, clear_status: bool = True):
        if self.scanner:
            self.scanner.stop()
        self.scanning_active = False
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)

        if clear_status:
            self.status_var.set(self.t("status_stopped"))

    def get_available_drives(self) -> list[str]:
        drives = []

        for letter in string.ascii_uppercase:
            drive = f"{letter}:/"
            if Path(drive).exists():
                drives.append(drive)

        return drives

    def _build_drive_usage_panel(self):
        for widget in self.drive_frame.winfo_children():
            widget.destroy()

        self.drive_bars.clear()

        drives = self.get_available_drives()
        if not drives:
            return

        for index, drive in enumerate(drives):
            col = index % 2
            row_index = index // 2

            card = ttk.Frame(self.drive_frame, style="App.TFrame", padding=(0, 2))
            card.grid(row=row_index, column=col, sticky="ew", padx=(0, 12), pady=2)

            top = ttk.Frame(card, style="App.TFrame")
            top.pack(fill="x")

            label = ttk.Label(top, text=drive, width=5, style="Hint.TLabel")
            label.pack(side="left")

            info = ttk.Label(top, text="", style="Hint.TLabel")
            info.pack(side="right")

            canvas = tk.Canvas(card, height=12, bg="#1f2937", highlightthickness=0)
            canvas.pack(fill="x", pady=(3, 0))

            self.drive_bars[drive] = {
                "canvas": canvas,
                "info": info,
            }

        self.drive_frame.columnconfigure(0, weight=1)
        self.drive_frame.columnconfigure(1, weight=1)

        self.update_drive_usage()

    def update_drive_usage(self):
        current_drives = self.get_available_drives()

        if set(current_drives) != set(self.drive_bars.keys()):
            self._build_drive_usage_panel()
            return

        for drive in current_drives:
            try:
                usage = shutil.disk_usage(drive)
            except Exception:
                continue

            total = usage.total
            used = usage.used
            free = usage.free
            percent = used / total if total else 0

            canvas = self.drive_bars[drive]["canvas"]
            info = self.drive_bars[drive]["info"]

            canvas.delete("all")

            width = max(canvas.winfo_width(), 1)
            height = 12
            fill_width = int(width * percent)

            color = "#5392BC"
            if percent >= 0.9:
                color = "#ef4444"
            elif percent >= 0.75:
                color = "#f59e0b"

            canvas.create_rectangle(0, 0, width, height, fill="#1f2937", outline="")
            canvas.create_rectangle(0, 0, fill_width, height, fill=color, outline="")

            if self.language == LANG_JA:
               text = f"{percent * 100:.0f}% · 空き {self.format_size(free)} / 合計 {self.format_size(total)}"
            else:
               text = f"{percent * 100:.0f}% · {self.format_size(free)} free / {self.format_size(total)} total"

            info.configure(text=text)

        self.after(3000, self.update_drive_usage)

    def _create_folder_snapshot(self, root_path: Path) -> dict[str, tuple[bool, int, int]]:
        snapshot: dict[str, tuple[bool, int, int]] = {}

        try:
            if root_path.is_file():
                stat = root_path.stat()
                snapshot[str(root_path)] = (False, int(stat.st_size), int(stat.st_mtime_ns))
                return snapshot

            for current_root, dirs, files in os.walk(root_path):
                dirs[:] = [d for d in dirs if d.lower() not in {"system volume information", "$recycle.bin"}]

                current = Path(current_root)

                for dir_name in dirs:
                    folder_path = current / dir_name
                    try:
                        stat = folder_path.stat()
                        snapshot[str(folder_path)] = (True, 0, int(stat.st_mtime_ns))
                    except (OSError, PermissionError, FileNotFoundError):
                        pass

                for file_name in files:
                    file_path = current / file_name
                    try:
                        stat = file_path.stat()
                        snapshot[str(file_path)] = (False, int(stat.st_size), int(stat.st_mtime_ns))
                    except (OSError, PermissionError, FileNotFoundError):
                        pass

                if len(snapshot) > 200000:
                    break

        except (OSError, PermissionError, FileNotFoundError):
            pass

        return snapshot

    def _auto_refresh_tick(self):
        if (
            self.auto_refresh_var.get()
            and self.last_scan_path
            and self.last_scan_path.exists()
            and not self.scanning_active
            and not self.auto_refresh_check_running
        ):
            self.auto_refresh_check_running = True
            thread = threading.Thread(target=self._auto_refresh_worker, daemon=True)
            thread.start()

        self.after(6000, self._auto_refresh_tick)

    def _auto_refresh_worker(self):
        try:
            if not self.last_scan_path:
                return

            snapshot = self._create_folder_snapshot(self.last_scan_path)

            if not self.last_snapshot:
                self.last_snapshot = snapshot
                return

            if snapshot != self.last_snapshot:
                self.last_snapshot = snapshot
                self.after(0, self._refresh_after_folder_change)

        finally:
            self.auto_refresh_check_running = False

    def _refresh_after_folder_change(self):
        if not self.last_scan_path or self.scanning_active:
            return

        status = "Refreshing..." if self.language == LANG_EN else "更新中..."
        self._begin_scan(self.last_scan_path, status, clear_table=True)
        self.update_drive_usage()

    def open_selected_in_explorer(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        if not values or len(values) < 6:
            return

        path = values[5]
        self.open_path_in_explorer(path)

    def open_path_in_explorer(self, path: str):
        target = Path(path)

        try:
            if target.is_file():
                subprocess.run(["explorer", "/select,", str(target)], check=False)
            elif target.is_dir():
                subprocess.run(["explorer", str(target)], check=False)
            else:
                parent = target.parent
                if parent.exists():
                    subprocess.run(["explorer", str(parent)], check=False)
        except Exception as error:
            messagebox.showerror("Error", f"Could not open path:\n{path}\n\n{error}")

    def _poll_queue(self):
        changed = False

        try:
            while True:
                event, payload = self.queue.get_nowait()

                if event == "add":
                    self._add_item(payload)
                    changed = True

                elif event == "update_size":
                    item_id, size = payload
                    if item_id in self.items:
                        self.items[item_id]["size_raw"] = size
                        self.items[item_id]["size"] = self.format_size(size)
                        changed = True

                elif event == "done":
                    self.scanning_active = False
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=100)
                    self.status_var.set(f"{self.t('status_done')}: {len(self.items)}")
                    self.update_drive_usage()
                    changed = True

        except Empty:
            pass

        if changed:
            self.refresh_table()

        self.after(250, self._poll_queue)

    def _add_item(self, item: ScanItem):
        icon = "📁" if item.is_dir else "📄"
        type_key = "folder" if item.is_dir else "file"

        self.items[item.item_id] = {
            "id": item.item_id,
            "name_raw": item.name,
            "name": f"{icon} {item.name}",
            "type_key": type_key,
            "size_raw": item.size if item.size is not None else -1,
            "size": self.format_size(item.size) if item.size is not None else self.t("calculating"),
            "modified_raw": item.modified,
            "modified": datetime.fromtimestamp(item.modified).strftime("%Y-%m-%d %H:%M"),
            "category_key": item.category_key,
            "path": item.path,
        }

    def refresh_table(self):
        query = self.search_var.get().strip().lower()
        exclude_text = self.exclude_var.get().strip().lower()

        rows = list(self.items.values())

        if query:
            rows = [
                row for row in rows
                if query in row["name_raw"].lower()
                or query in row["path"].lower()
            ]

        if exclude_text:
            exclude_words = [
                word.strip()
                for word in exclude_text.replace(";", ",").split(",")
                if word.strip()
            ]

            rows = [
                row for row in rows
                if not any(word in row["path"].lower() for word in exclude_words)
            ]

        sort_key = self.sort_var.get()

        if sort_key == "size":
            rows.sort(key=lambda row: row["size_raw"], reverse=True)
        elif sort_key == "modified":
            rows.sort(key=lambda row: row["modified_raw"], reverse=True)
        elif sort_key == "name":
            rows.sort(key=lambda row: row["name_raw"].lower())
        elif sort_key == "type":
            rows.sort(key=lambda row: row["type_key"])
        elif sort_key == "category":
            rows.sort(key=lambda row: row["category_key"])

        self.tree.delete(*self.tree.get_children())

        for row in rows[:MAX_VISIBLE_ROWS]:
            self.tree.insert(
                "",
                "end",
                values=(
                    row["name"],
                    self.t(row["type_key"]),
                    row["size"] if row["size_raw"] != -1 else self.t("calculating"),
                    row["modified"],
                    self.t(row["category_key"]),
                    row["path"],
                ),
            )

    @staticmethod
    def format_size(size: int | None) -> str:
        if size is None or size < 0:
            return ""

        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        value = float(size)

        for unit in units:
            if value < 1024:
                return f"{value:.2f} {unit}"
            value /= 1024

        return f"{value:.2f} EB"