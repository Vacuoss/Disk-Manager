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
    BG = "#0b1220"
    PANEL = "#101a2c"
    PANEL_2 = "#132033"
    PANEL_3 = "#17243a"
    BORDER = "#26364f"
    BORDER_2 = "#334762"
    TEXT = "#edf4ff"
    MUTED = "#8fa2bd"
    MUTED_2 = "#64748b"
    BLUE = "#2f80ed"
    BLUE_2 = "#4f9cff"
    BLUE_3 = "#1f5fbf"
    ENTRY = "#0f1828"

    def __init__(self):
        super().__init__()
        if sys.platform.startswith("win"):
            try:
                self.withdraw()
            except Exception:
                pass

        self.language = LANG_EN
        self.title(APP_TITLE)
        self.geometry("1280x820")
        self.minsize(1080, 720)
        self.path_var = tk.StringVar(value=DEFAULT_PATH)
        self.search_var = tk.StringVar()
        self.exclude_var = tk.StringVar()
        self.sort_var = tk.StringVar(value="size")
        self.quick_mode_var = tk.BooleanVar(value=True)
        self.auto_refresh_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value=self.t("status_ready"))
        self.count_var = tk.StringVar(value="0 items")
        self.queue: Queue = Queue()
        self.scanner: DiskScanner | None = None
        self.scan_thread: threading.Thread | None = None
        self.items: dict[str, dict] = {}
        self.drive_bars: dict[str, dict] = {}
        self.scanning_active = False
        self.auto_refresh_check_running = False
        self.last_scan_path: Path | None = None
        self.last_snapshot: dict[str, tuple[bool, int, int]] = {}
        self._window_images: list[tk.PhotoImage] = []
        self._scan_anim_pos = 0
        self._scan_anim_job = None
        self._is_maximized = False

        self._apply_window_icon()
        self._configure_style()
        self._build_ui()
        self._scrub_focus_artifacts()
        self.after(25, self._scrub_focus_artifacts)
        self.after(1, self._force_dark_window_frame)
        self.after(60, self._show_window_after_dark_titlebar)
        self.after(250, self._force_dark_window_frame)
        self.after(900, self._force_dark_window_frame)
        self._poll_queue()
        self._auto_refresh_tick()

    def t(self, key: str) -> str:
        return TEXT[self.language].get(key, key)

    def ui_text(self, en: str, ja: str) -> str:
        return ja if self.language == LANG_JA else en

    def _resource_path(self, relative_path: str) -> Path:
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        return base_path / relative_path

    def _apply_window_icon(self):
        ico_candidates = [
            self._resource_path("assets/disk_manager.ico"),
            self._resource_path("disk_manager.ico"),
            self._resource_path("assets/disck_manager.ico"),
            self._resource_path("disck_manager.ico"),
            self._resource_path("assets/icon.ico"),
            self._resource_path("icon.ico"),
        ]
        png_candidates = [
            self._resource_path("assets/disk_manager.png"),
            self._resource_path("disk_manager.png"),
            self._resource_path("assets/disck_manager.png"),
            self._resource_path("disck_manager.png"),
            self._resource_path("assets/icon.png"),
            self._resource_path("icon.png"),
        ]

        for icon_path in ico_candidates:
            if icon_path.exists():
                try:
                    self.iconbitmap(str(icon_path))
                    break
                except Exception:
                    pass

        for png_path in png_candidates:
            if png_path.exists():
                try:
                    image = tk.PhotoImage(file=str(png_path))
                    self._window_images.append(image)
                    self.iconphoto(True, image)
                    return
                except Exception:
                    pass


    def _enable_dark_window_frame(self):
        """Best-effort dark title bar on Windows. Falls back safely elsewhere."""
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            enabled = ctypes.c_int(1)
            for attr in (20, 19):
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(enabled), ctypes.sizeof(enabled))
                except Exception:
                    pass

            caption = ctypes.c_int(0x0020120B)
            border = ctypes.c_int(0x00364F26)
            text = ctypes.c_int(0x00FFF4ED)
            for attr, value in ((35, caption), (34, border), (36, text)):
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))
                except Exception:
                    pass
            try:
                ctypes.windll.user32.SetWindowPos(
                    hwnd,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020,
                )
                ctypes.windll.user32.RedrawWindow(hwnd, None, None, 0x0400 | 0x0100 | 0x0001)
            except Exception:
                pass

            try:
                ctypes.windll.dwmapi.DwmFlush()
            except Exception:
                pass
        except Exception:
            pass

    def _force_dark_window_frame(self):
        """Apply and repaint the native Windows title bar without removing the original helper."""
        self._enable_dark_window_frame()

    def _show_window_after_dark_titlebar(self):
        """Show the window only after the title bar has had a chance to become dark."""
        self._force_dark_window_frame()
        try:
            if self.state() == "withdrawn":
                self.deiconify()
        except Exception:
            pass
        self.after(80, self._force_dark_window_frame)

    def _scrub_focus_artifacts(self):
        """Remove tiny dotted/focus artifacts that appear on some Windows DPI/theme combinations."""
        def clean(widget):
            for option, value in (
                ("highlightthickness", 0),
                ("highlightbackground", self.BG),
                ("highlightcolor", self.BG),
                ("bd", 0),
                ("borderwidth", 0),
                ("relief", "flat"),
                ("takefocus", 0),
            ):
                try:
                    widget.configure(**{option: value})
                except Exception:
                    pass
            try:
                widget.configure(insertbackground=self.TEXT)
            except Exception:
                pass
            for child in widget.winfo_children():
                clean(child)
        clean(self)

    def _install_borderless_ttk_layouts(self, style: ttk.Style):
        """Remove ttk focus elements instead of only recoloring them."""
        try:
            button_layout = [
                ("Button.border", {
                    "sticky": "nswe",
                    "border": 0,
                    "children": [
                        ("Button.padding", {
                            "sticky": "nswe",
                            "children": [("Button.label", {"sticky": "nswe"})],
                        })
                    ],
                })
            ]
            style.layout("TButton", button_layout)
            style.layout("Accent.TButton", button_layout)
        except Exception:
            pass

        try:
            check_layout = [
                ("Checkbutton.padding", {
                    "sticky": "nswe",
                    "children": [
                        ("Checkbutton.indicator", {"side": "left", "sticky": ""}),
                        ("Checkbutton.label", {"side": "left", "sticky": "w"}),
                    ],
                })
            ]
            style.layout("TCheckbutton", check_layout)
        except Exception:
            pass

        try:
            style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
            style.layout("Clean.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        except Exception:
            pass

        try:
            style.layout("Vertical.TScrollbar", [
                ("Vertical.Scrollbar.trough", {
                    "sticky": "ns",
                    "border": 0,
                    "children": [("Vertical.Scrollbar.thumb", {"expand": 1, "sticky": "nswe"})],
                })
            ])
        except Exception:
            pass

    def _toggle_maximize(self):
        if not sys.platform.startswith("win"):
            return
        if self._is_maximized:
            self.state("normal")
            self._is_maximized = False
        else:
            self.state("zoomed")
            self._is_maximized = True

    def _configure_style(self):
        self.configure(bg=self.BG)
        style = ttk.Style(self)
        style.theme_use("clam")
        self._install_borderless_ttk_layouts(style)
        self.option_add("*takeFocus", 0)
        self.option_add("*HighlightThickness", 0)
        self.option_add("*highlightThickness", 0)
        self.option_add("*highlightColor", self.BG)
        self.option_add("*highlightBackground", self.BG)
        self.option_add("*Button.highlightThickness", 0)
        self.option_add("*Button.highlightBackground", self.BG)
        self.option_add("*Button.highlightColor", self.BG)
        self.option_add("*Frame.highlightThickness", 0)
        self.option_add("*Canvas.highlightThickness", 0)
        self.option_add("*Button.takeFocus", 0)
        self.option_add("*TButton.takeFocus", 0)
        self.option_add("*TCheckbutton.takeFocus", 0)
        self.option_add("*Treeview.takeFocus", 0)
        self.option_add("*Entry.highlightThickness", 0)
        self.option_add("*Checkbutton.highlightThickness", 0)
        self.option_add("*Canvas.borderWidth", 0)
        self.option_add("*Frame.borderWidth", 0)
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("App.TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("Card.TFrame", background=self.PANEL_2)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT, font=("Segoe UI Variable Display", 24, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10))
        style.configure("Hint.TLabel", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=self.BG, foreground="#cbd8ea", font=("Segoe UI", 9, "bold"))
        style.configure("CardTitle.TLabel", background=self.PANEL_2, foreground=self.TEXT, font=("Segoe UI", 11, "bold"))
        style.configure("CardMuted.TLabel", background=self.PANEL_2, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure(
            "TButton",
            background=self.PANEL_3,
            foreground=self.TEXT,
            bordercolor=self.BORDER,
            lightcolor=self.PANEL_3,
            darkcolor=self.PANEL_3,
            relief="flat",
            focuscolor=self.PANEL_3,
            focusthickness=0,
            font=("Segoe UI", 10),
            padding=(16, 10),
        )
        style.map("TButton", background=[("active", "#1d2e49"), ("pressed", "#233754")], foreground=[("disabled", self.MUTED_2)])

        style.configure(
            "Accent.TButton",
            background=self.BLUE,
            foreground="#ffffff",
            bordercolor=self.BLUE,
            lightcolor=self.BLUE,
            darkcolor=self.BLUE,
            relief="flat",
            focuscolor=self.BLUE,
            focusthickness=0,
            font=("Segoe UI", 10, "bold"),
            padding=(18, 10),
        )
        style.map("Accent.TButton", background=[("active", self.BLUE_2), ("pressed", self.BLUE_3)], foreground=[("disabled", "#9ec7ff")])

        style.configure(
            "TEntry",
            fieldbackground=self.ENTRY,
            foreground=self.TEXT,
            insertcolor=self.TEXT,
            bordercolor=self.BORDER,
            lightcolor=self.BORDER,
            darkcolor=self.BORDER,
            relief="flat",
            padding=9,
        )
        style.map("TEntry", fieldbackground=[("focus", "#132039")], bordercolor=[("focus", self.BLUE)])

        style.configure(
            "TCombobox",
            fieldbackground=self.ENTRY,
            background=self.ENTRY,
            foreground=self.TEXT,
            arrowcolor=self.TEXT,
            bordercolor=self.BORDER,
            lightcolor=self.BORDER,
            darkcolor=self.BORDER,
            relief="flat",
            padding=9,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", self.ENTRY), ("focus", "#132039")],
            selectbackground=[("readonly", self.ENTRY)],
            selectforeground=[("readonly", self.TEXT)],
            bordercolor=[("focus", self.BLUE)],
        )

        style.configure("TCheckbutton", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10), indicatorcolor=self.ENTRY, focuscolor=self.BG, focusthickness=0)
        style.map("TCheckbutton", background=[("active", self.BG)], foreground=[("active", self.TEXT)], indicatorcolor=[("selected", self.BLUE), ("active", self.PANEL_3)])

        style.configure(
            "Treeview",
            background=self.PANEL,
            fieldbackground=self.PANEL,
            foreground=self.TEXT,
            bordercolor=self.PANEL,
            lightcolor=self.PANEL,
            darkcolor=self.PANEL,
            borderwidth=0,
            highlightthickness=0,
            relief="flat",
            rowheight=26,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=self.PANEL_3,
            foreground=self.TEXT,
            relief="flat",
            bordercolor=self.PANEL_3,
            borderwidth=0,
            font=("Segoe UI", 10, "bold"),
            padding=(5, 5),
        )
        style.map("Treeview", background=[("selected", self.BLUE_3)], foreground=[("selected", "#ffffff")])
        style.map("Treeview.Heading", background=[("active", "#203350")])
        style.configure("Clean.Treeview", borderwidth=0, highlightthickness=0, relief="flat")

        style.configure(
            "Vertical.TScrollbar",
            background=self.PANEL_3,
            troughcolor=self.BG,
            bordercolor=self.BG,
            arrowcolor=self.MUTED,
            lightcolor=self.PANEL_3,
            darkcolor=self.PANEL_3,
            relief="flat",
            width=12,
            arrowsize=0,
        )
        style.map("Vertical.TScrollbar", background=[("active", self.BORDER_2), ("pressed", self.BLUE_3)])

        try:
            style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"expand": 1, "sticky": "nswe"})]})])
        except Exception:
            pass

        style.configure("Horizontal.TProgressbar", background=self.BLUE, troughcolor=self.PANEL_3, bordercolor=self.PANEL_3, lightcolor=self.BLUE, darkcolor=self.BLUE)

    def _make_card(self, parent, pad=14):
        outer = tk.Frame(parent, bg=self.PANEL_2, bd=0, highlightthickness=0, relief="flat")
        inner = tk.Frame(outer, bg=self.PANEL_2, bd=0, padx=pad, pady=pad, highlightthickness=0, relief="flat")
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _make_text_entry(self, parent, variable: tk.StringVar) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=variable,
            bg=self.ENTRY,
            fg=self.TEXT,
            insertbackground=self.TEXT,
            selectbackground=self.BLUE_3,
            selectforeground="#ffffff",
            disabledbackground=self.ENTRY,
            disabledforeground=self.MUTED_2,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=self.BORDER,
            highlightcolor=self.BLUE,
            font=("Segoe UI", 10),
        )

    def _build_ui(self):
        self.main_frame = tk.Frame(self, bg=self.BG, bd=0, highlightthickness=0)
        self.main_frame.pack(fill="both", expand=True, padx=16, pady=12)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(4, weight=1)

        header = tk.Frame(self.main_frame, bg=self.BG, bd=0, highlightthickness=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        left_header = tk.Frame(header, bg=self.BG, bd=0, highlightthickness=0)
        left_header.grid(row=0, column=0, sticky="ew")
        self.title_label = ttk.Label(left_header, text=self.t("title"), style="Title.TLabel")
        self.title_label.pack(anchor="w")
        self.subtitle_label = ttk.Label(
            left_header,
            text=self.ui_text("Disk usage analyzer", "ディスク使用量アナライザー"),
            style="Subtitle.TLabel",
        )
        self.subtitle_label.pack(anchor="w", pady=(2, 0))
        self.lang_button = ttk.Button(header, text=self.t("language"), command=self.toggle_language, takefocus=False)
        self.lang_button.grid(row=0, column=1, sticky="e", padx=(12, 0))

        hero_outer, hero = self._make_card(self.main_frame, pad=12)
        hero_outer.grid(row=1, column=0, sticky="ew", pady=(12, 10))
        hero.grid_columnconfigure(0, weight=1)
        self.path_label = ttk.Label(hero, text=self.t("path"), background=self.PANEL_2, foreground=self.MUTED)
        self.path_label.grid(row=0, column=0, sticky="w", columnspan=4)
        self.path_entry = self._make_text_entry(hero, self.path_var)
        self.path_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(6, 0), ipady=8)
        self.browse_button = ttk.Button(hero, text=self.t("browse"), command=self.browse_path, takefocus=False)
        self.browse_button.grid(row=1, column=1, padx=(0, 8), pady=(6, 0))
        self.scan_button = ttk.Button(hero, text=self.t("scan"), command=self.start_scan, style="Accent.TButton", takefocus=False)
        self.scan_button.grid(row=1, column=2, padx=(0, 8), pady=(6, 0))
        self.stop_button = ttk.Button(hero, text=self.t("stop"), command=self.stop_scan, takefocus=False)
        self.stop_button.grid(row=1, column=3, pady=(6, 0))

        filters = tk.Frame(self.main_frame, bg=self.BG, bd=0, highlightthickness=0)
        filters.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        filters.grid_columnconfigure(0, weight=2)
        filters.grid_columnconfigure(1, weight=2)
        filters.grid_columnconfigure(2, weight=1)
        self.search_label = ttk.Label(filters, text=self.t("search"), style="Hint.TLabel")
        self.search_label.grid(row=0, column=0, sticky="w")
        self.exclude_label = ttk.Label(filters, text=self.ui_text("Exclude path words", "除外するパスの単語"), style="Hint.TLabel")
        self.exclude_label.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.sort_label = ttk.Label(filters, text=self.t("sort_by"), style="Hint.TLabel")
        self.sort_label.grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.search_entry = self._make_text_entry(filters, self.search_var)
        self.search_entry.grid(row=1, column=0, sticky="ew", pady=(5, 0), ipady=8)
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh_table())
        self.exclude_entry = self._make_text_entry(filters, self.exclude_var)
        self.exclude_entry.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(5, 0), ipady=8)
        self.exclude_entry.bind("<KeyRelease>", lambda _e: self.refresh_table())
        self.sort_box = tk.Button(
            filters,
            text=self.t(self.sort_var.get()),
            command=self._open_sort_menu,
            bg=self.ENTRY,
            fg=self.TEXT,
            activebackground="#132039",
            activeforeground=self.TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            highlightbackground=self.BG,
            highlightcolor=self.BG,
            padx=12,
            pady=8,
            anchor="w",
            font=("Segoe UI", 10),
            cursor="hand2",
            takefocus=False,
        )
        self.sort_box.grid(row=1, column=2, sticky="ew", padx=(10, 0), pady=(5, 0))
        self.quick_check = ttk.Checkbutton(filters, text=self.t("quick_mode"), variable=self.quick_mode_var, takefocus=False)
        self.quick_check.grid(row=1, column=3, sticky="w", padx=(14, 0), pady=(5, 0))
        self.auto_refresh_check = ttk.Checkbutton(filters, text=self.ui_text("Auto refresh", "自動更新"), variable=self.auto_refresh_var, takefocus=False)
        self.auto_refresh_check.grid(row=1, column=4, sticky="w", padx=(10, 0), pady=(5, 0))
        self.hint_label = ttk.Label(filters, text=self.t("all_disk_hint"), style="Hint.TLabel")
        self.hint_label.grid(row=2, column=0, columnspan=5, sticky="w", pady=(7, 0))

        drives_header = tk.Frame(self.main_frame, bg=self.BG, bd=0, highlightthickness=0)
        drives_header.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        self.drives_title = ttk.Label(drives_header, text=self.ui_text("Drives", "ドライブ"), style="Hint.TLabel")
        self.drives_title.pack(side="left")
        self.count_label = ttk.Label(drives_header, textvariable=self.count_var, style="Hint.TLabel")
        self.count_label.pack(side="right")

        body = tk.Frame(self.main_frame, bg=self.BG, bd=0, highlightthickness=0)
        body.grid(row=4, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        self.drive_frame = tk.Frame(body, bg=self.BG, bd=0, highlightthickness=0)
        self.drive_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._build_drive_usage_panel()

        table_outer, table_card = self._make_card(body, pad=0)
        table_outer.grid(row=1, column=0, sticky="nsew")
        table_card.grid_columnconfigure(0, weight=1)
        table_card.grid_rowconfigure(0, weight=1)
        columns = ("name", "type", "size", "modified", "category", "path")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse", style="Clean.Treeview", takefocus=False)
        scrollbar = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview, style="Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self.open_selected_in_explorer)
        self.tree.bind("<Return>", self.open_selected_in_explorer)
        self._apply_headers()
        self.tree.column("name", width=270, minwidth=170, anchor="w")
        self.tree.column("type", width=90, minwidth=70, anchor="w", stretch=False)
        self.tree.column("size", width=112, minwidth=88, anchor="e", stretch=False)
        self.tree.column("modified", width=128, minwidth=118, anchor="center", stretch=False)
        self.tree.column("category", width=145, minwidth=110, anchor="w", stretch=False)
        self.tree.column("path", width=520, minwidth=240, anchor="w")
        self.tree.tag_configure("odd", background="#0f1929")
        self.tree.tag_configure("even", background="#111d30")

        footer = tk.Frame(self.main_frame, bg=self.BG, bd=0, highlightthickness=0)
        footer.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, textvariable=self.status_var, style="Status.TLabel", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.progress = tk.Canvas(footer, width=260, height=14, bg=self.PANEL_3, highlightthickness=0, bd=0, relief="flat")
        self.progress.grid(row=0, column=1, sticky="e")
        self._draw_scan_progress(0)
        self.bind("<Configure>", self._on_window_resize)

    def _on_window_resize(self, _event=None):
        # Reflow drive cards when the window becomes narrow/wide and keep the footer visible.
        if not hasattr(self, "drive_frame"):
            return
        width = self.winfo_width()
        columns = 3 if width >= 1120 else 2
        current_columns = getattr(self, "_drive_columns", None)
        if current_columns != columns and self.drive_bars:
            self._drive_columns = columns
            for index, (drive, widgets) in enumerate(self.drive_bars.items()):
                parent = widgets["canvas"].master
                parent.grid_configure(row=index // columns, column=index % columns)
            for col in range(4):
                self.drive_frame.columnconfigure(col, weight=1 if col < columns else 0)
        if hasattr(self, "progress"):
            self._draw_scan_progress(100 if not self.scanning_active else None)

    def _open_sort_menu(self):
        if hasattr(self, "_sort_popup") and self._sort_popup.winfo_exists():
            self._sort_popup.destroy()
            return
        popup = tk.Toplevel(self)
        self._sort_popup = popup
        popup.overrideredirect(True)
        popup.configure(bg=self.ENTRY)
        x = self.sort_box.winfo_rootx()
        y = self.sort_box.winfo_rooty() + self.sort_box.winfo_height() + 3
        w = min(max(self.sort_box.winfo_width(), 96), 124)
        row_height = 24
        popup.geometry(f"{w}x{len(SORT_KEYS) * row_height}+{x}+{y}")
        for key in SORT_KEYS:
            selected = key == self.sort_var.get()
            btn = tk.Button(
                popup,
                text=self.t(key),
                command=lambda value=key: self._set_sort_key(value),
                bg=self.BLUE_3 if selected else self.ENTRY,
                fg="#ffffff" if selected else self.TEXT,
                activebackground=self.BLUE,
                activeforeground="#ffffff",
                relief="flat",
                bd=0,
                highlightthickness=0,
                highlightbackground=self.ENTRY,
                highlightcolor=self.ENTRY,
                padx=9,
                pady=2,
                anchor="w",
                font=("Segoe UI", 9),
                takefocus=False,
            )
            btn.pack(fill="x", padx=0, pady=0)
        popup.bind("<FocusOut>", lambda _e: popup.destroy())
        popup.focus_force()
        self.after(1, self._scrub_focus_artifacts)

    def _set_sort_key(self, value: str):
        self.sort_var.set(value)
        self.sort_box.configure(text=self.t(value))
        if hasattr(self, "_sort_popup") and self._sort_popup.winfo_exists():
            self._sort_popup.destroy()
        self.refresh_table()

    def _mix_hex(self, left: str, right: str, amount: float) -> str:
        amount = max(0.0, min(1.0, amount))
        l = left.lstrip("#")
        r = right.lstrip("#")
        values = []
        for i in (0, 2, 4):
            a = int(l[i:i + 2], 16)
            b = int(r[i:i + 2], 16)
            values.append(round(a + (b - a) * amount))
        return "#" + "".join(f"{value:02x}" for value in values)

    def _drive_bar_color(self, percent: float) -> str:
        # Disk usage color by fill percentage:
        # < 70% = blue, 70–85% = yellow, 85–100% = red
        if percent >= 0.85:
            return "#ef4444"   # red
        elif percent >= 0.70:
            return "#facc15"   # yellow
        else:
            return "#3b82f6"   # blue

    def _draw_scan_progress(self, value: float | None = None):
        if not hasattr(self, "progress"):
            return
        self.progress.delete("all")
        width = max(self.progress.winfo_width(), 240)
        height = max(self.progress.winfo_height(), 12)
        self.progress.create_rectangle(0, 0, width, height, fill=self.PANEL_3, outline="")
        if self.scanning_active:
            segment = max(46, width // 4)
            x = self._scan_anim_pos % (width + segment) - segment
            self.progress.create_rectangle(x, 0, x + segment, height, fill=self.BLUE, outline="")
            self.progress.create_rectangle(x + segment - 18, 0, x + segment, height, fill=self.BLUE_2, outline="")
        else:
            fill_width = int(width * max(0, min(100, value or 0)) / 100)
            self.progress.create_rectangle(0, 0, fill_width, height, fill=self.BLUE, outline="")

    def _start_scan_animation(self):
        self._scan_anim_pos = 0
        self._animate_scan_progress()

    def _animate_scan_progress(self):
        if not self.scanning_active:
            self._draw_scan_progress(0)
            self._scan_anim_job = None
            return
        self._scan_anim_pos += 12
        self._draw_scan_progress(None)
        self._scan_anim_job = self.after(45, self._animate_scan_progress)

    def _stop_scan_animation(self, value: float = 0):
        if self._scan_anim_job:
            try:
                self.after_cancel(self._scan_anim_job)
            except Exception:
                pass
            self._scan_anim_job = None
        self._draw_scan_progress(value)

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
        self.subtitle_label.configure(text=self.ui_text("Modern disk usage analyzer", "モダンなディスク使用量アナライザー"))
        self.lang_button.configure(text=self.t("language"))
        self.path_label.configure(text=self.t("path"))
        self.browse_button.configure(text=self.t("browse"))
        self.scan_button.configure(text=self.t("scan"))
        self.stop_button.configure(text=self.t("stop"))
        self.search_label.configure(text=self.t("search"))
        self.exclude_label.configure(text=self.ui_text("Exclude path words", "除外するパスの単語"))
        self.sort_label.configure(text=self.t("sort_by"))
        self.sort_box.configure(text=self.t(self.sort_var.get()))
        self.quick_check.configure(text=self.t("quick_mode"))
        self.auto_refresh_check.configure(text=self.ui_text("Auto refresh", "自動更新"))
        self.hint_label.configure(text=self.t("all_disk_hint"))
        self.drives_title.configure(text=self.ui_text("Drives", "ドライブ"))
        self._apply_headers()
        self.refresh_table()
        self.update_drive_usage()

    def browse_path(self):
        selected = filedialog.askdirectory(title=self.t("select_folder"), initialdir=self.path_var.get() if Path(self.path_var.get()).exists() else DEFAULT_PATH)
        if selected:
            normalized = selected.replace("\\", "/")
            self.path_var.set(normalized)
            self.path_entry.icursor("end")
            self.path_entry.xview_moveto(1)

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
            self.count_var.set(self.ui_text("0 items", "0 件"))
        self.last_scan_path = path
        self.status_var.set(status)
        self.scanning_active = True
        self._start_scan_animation()
        self.scanner = DiskScanner(path, self.queue, quick_mode=self.quick_mode_var.get())
        self.scan_thread = threading.Thread(target=self.scanner.run, daemon=True)
        self.scan_thread.start()

    def stop_scan(self, clear_status: bool = True):
        if self.scanner:
            self.scanner.stop()
        self.scanning_active = False
        self._stop_scan_animation(0)
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

        columns = 3 if self.winfo_width() >= 1120 else 2
        for index, drive in enumerate(drives):
            card = tk.Frame(self.drive_frame, bg=self.PANEL_2, bd=0, highlightthickness=0, padx=10, pady=9)
            card.grid(row=index // columns, column=index % columns, sticky="ew", padx=(0, 8), pady=(0, 8))
            top = tk.Frame(card, bg=self.PANEL_2, bd=0, highlightthickness=0)
            top.pack(fill="x")
            label = ttk.Label(top, text=drive, style="CardTitle.TLabel")
            label.pack(side="left")
            info = ttk.Label(top, text="", style="CardMuted.TLabel")
            info.pack(side="right")
            detail = ttk.Label(card, text="", style="CardMuted.TLabel")
            detail.pack(anchor="w", pady=(5, 5))
            canvas = tk.Canvas(card, height=8, bg=self.PANEL_3, highlightthickness=0, bd=0, relief="flat")
            canvas.pack(fill="x")
            self.drive_bars[drive] = {"canvas": canvas, "info": info, "detail": detail}

        for col in range(4):
            self.drive_frame.columnconfigure(col, weight=1 if col < columns else 0)
        self.after(80, self.update_drive_usage)

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
            total, used, free = usage.total, usage.used, usage.free
            percent = used / total if total else 0
            canvas = self.drive_bars[drive]["canvas"]
            info = self.drive_bars[drive]["info"]
            detail = self.drive_bars[drive]["detail"]
            canvas.delete("all")
            width = max(canvas.winfo_width(), 1)
            height = 9
            fill_width = int(width * percent)
            canvas.create_rectangle(0, 0, width, height, fill=self.PANEL_3, outline="")
            canvas.create_rectangle(0, 0, fill_width, height, fill=self._drive_bar_color(percent), outline="")
            if fill_width > 3:
                canvas.create_rectangle(max(0, fill_width - 2), 0, fill_width, height, fill=self._mix_hex(self._drive_bar_color(percent), "#ffffff", 0.22), outline="")
            info.configure(text=f"{percent * 100:.0f}%")
            if self.language == LANG_JA:
                detail.configure(text=f"使用済み {self.format_size(used)} / 合計 {self.format_size(total)} · 空き {self.format_size(free)}")
            else:
                detail.configure(text=f"Used {self.format_size(used)} / {self.format_size(total)} · Free {self.format_size(free)}")
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
        if self.auto_refresh_var.get() and self.last_scan_path and self.last_scan_path.exists() and not self.scanning_active and not self.auto_refresh_check_running:
            self.auto_refresh_check_running = True
            threading.Thread(target=self._auto_refresh_worker, daemon=True).start()
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
        self._begin_scan(self.last_scan_path, self.ui_text("Refreshing...", "更新中..."), clear_table=True)
        self.update_drive_usage()

    def open_selected_in_explorer(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        if values and len(values) >= 6:
            self.open_path_in_explorer(values[5])

    def open_path_in_explorer(self, path: str):
        target = Path(path)
        try:
            if sys.platform.startswith("win"):
                if target.is_file():
                    subprocess.run(["explorer", "/select,", str(target)], check=False)
                elif target.is_dir():
                    subprocess.run(["explorer", str(target)], check=False)
                elif target.parent.exists():
                    subprocess.run(["explorer", str(target.parent)], check=False)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(target if target.exists() else target.parent)], check=False)
            else:
                subprocess.run(["xdg-open", str(target if target.exists() else target.parent)], check=False)
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
                    self._stop_scan_animation(100)
                    self.status_var.set(f"{self.t('status_done')}: {len(self.items)}")
                    self.update_drive_usage()
                    changed = True
        except Empty:
            pass
        if changed:
            self.refresh_table()
        self.after(250, self._poll_queue)

    def _display_icon_for_item(self, item: ScanItem) -> str:
        if item.is_dir:
            return "📁"
        suffix = Path(item.path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".psd", ".ai"}:
            return "🖼️"
        if suffix in {".mp4", ".mkv", ".avi", ".mov", ".webm", ".wmv", ".flv", ".m4v"}:
            return "🎬"
        if suffix in {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma"}:
            return "🎵"
        if suffix in {".zip", ".rar", ".7z", ".tar", ".gz", ".iso"}:
            return "🗜️"
        if suffix in {".exe", ".msi", ".msix", ".bat", ".cmd"}:
            return "⚙️"
        if suffix in {".pdf", ".doc", ".docx", ".txt", ".md", ".xls", ".xlsx", ".ppt", ".pptx"}:
            return "📄"
        return "📄"

    def _add_item(self, item: ScanItem):
        icon = self._display_icon_for_item(item)
        type_key = "folder" if item.is_dir else "file"
        self.items[item.item_id] = {
            "id": item.item_id,
            "name_raw": item.name,
            "name": f"{icon}  {item.name}",
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
            rows = [row for row in rows if query in row["name_raw"].lower() or query in row["path"].lower()]
        if exclude_text:
            exclude_words = [word.strip() for word in exclude_text.replace(";", ",").split(",") if word.strip()]
            rows = [row for row in rows if not any(word in row["path"].lower() for word in exclude_words)]
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
        for index, row in enumerate(rows[:MAX_VISIBLE_ROWS]):
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
                tags=("even" if index % 2 == 0 else "odd",),
            )
        word = self.ui_text("items", "件")
        self.count_var.set(f"{len(rows)} {word}")

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