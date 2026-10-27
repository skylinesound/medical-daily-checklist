"""Medical Daily Checklist v5.2 — a private, offline daily health log.

Runs on Python 3.9+ with the standard Tkinter/Tcl/Tk packages. Records stay
in the local user's application-data directory as SQLite; no networking.
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
import tkinter as tk
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from medical_report import PERIODS, period_dates, generate_report_pdf

APP_TITLE = "Medical Daily Checklist"
# Make recorded/confirmed entries clear at a glance. Pending messages stay understated.
CONFIRMED_STATUS_FONT = ("Segoe UI", 14, "bold")
PENDING_STATUS_FONT = ("Segoe UI", 10, "normal")
KIND_LABELS = {
    "medication": "Medication",
    "insulin": "Insulin",
    "blood_pressure": "Blood pressure",
    "blood_glucose": "Blood glucose",
}
THEMES = {
    "light": {
        "bg": "#f1f5f9", "card": "#ffffff", "ink": "#172033", "muted": "#536273",
        "blue": "#155eaa", "blue_hover": "#104d8e", "green": "#147d64",
        "border": "#d9e2ec", "field": "#ffffff", "secondary": "#e8eef5",
        "secondary_hover": "#d7e0ec", "disabled": "#dbece5", "disabled_ink": "#456b5b",
        "stripe": "#f7fafc", "selected": "#d6e9fb", "danger": "#a52837",
    },
    "dark": {
        "bg": "#0e1726", "card": "#1d2a3b", "ink": "#f1f5f9", "muted": "#c0cddd",
        "blue": "#2865c7", "blue_hover": "#377bda", "green": "#6be0bd",
        "border": "#3b4b60", "field": "#101b2b", "secondary": "#34455b",
        "secondary_hover": "#41566e", "disabled": "#26483f", "disabled_ink": "#95c9b6",
        "stripe": "#223147", "selected": "#325984", "danger": "#ff9aa5",
    },
}


def local_now():
    return datetime.now().astimezone()


def storage_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "MedicalChores"  # Unchanged deliberately: preserves the existing database.
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "MedicalChores"  # Unchanged deliberately: preserves the existing database.


def load_theme(path: Path) -> str:
    try:
        name = json.loads(path.read_text(encoding="utf-8")).get("theme", "light")
        return name if name in THEMES else "light"
    except (OSError, ValueError, AttributeError, TypeError):
        return "light"


def save_theme(path: Path, theme: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"theme": theme}, indent=2), encoding="utf-8")
    temp.replace(path)



# Window layouts live alongside the old database and theme settings. This
# separate file prevents the theme preference from overwriting window size.
def load_window_layout(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = ("width", "height", "x", "y")
        if not isinstance(data, dict) or not all(
            type(data.get(k)) is int for k in fields
        ):
            return None
        if not (850 <= data["width"] <= 16000 and 700 <= data["height"] <= 16000
                and -100000 <= data["x"] <= 100000
                and -100000 <= data["y"] <= 100000):
            return None
        return {**{k: data[k] for k in fields},
                "maximized": data.get("maximized") is True}
    except (OSError, ValueError, TypeError):
        return None


def save_window_layout(path: Path, layout):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(layout, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def layout_geometry(layout):
    # Tk requires -X for negative screen positions, e.g. left-hand monitor.
    return (f'{layout["width"]}x{layout["height"]}'
            f'{layout["x"]:+d}{layout["y"]:+d}')


def fit_layout_to_displays(layout, work_areas):
    """Make an old layout visible after a monitor is removed or repositioned.

    Areas are (left, top, right, bottom). Keep the user's saved dimensions
    where possible, while leaving at least the whole title bar visible.
    """
    if not work_areas:
        return dict(layout)
    x, y, w, h = (layout[k] for k in ("x", "y", "width", "height"))
    def overlap(rect):
        l, t, r, b = rect
        return max(0, min(x+w, r)-max(x, l)) * max(0, min(y+h, b)-max(y, t))
    best = max(work_areas, key=overlap)
    if overlap(best) < 80 * 35:
        # On changed monitor arrangements, prefer the main display.
        best = work_areas[0]
    l, t, r, b = best
    # Never allow the window to become bigger than the current screen.
    w = min(w, max(850, r-l))
    h = min(h, max(700, b-t))
    x = min(max(x, l), max(l, r-w))
    y = min(max(y, t), max(t, b-h))
    return {**layout, "width": w, "height": h, "x": x, "y": y}


def display_work_areas(root):
    """All Windows monitors, using taskbar-adjusted work rectangles.

    Linux fallback uses the available Tk screen bounds; this remains usable
    even when launched without pywin32 or any third-party packages.
    """
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD),
                            ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT),
                            ("dwFlags", wintypes.DWORD)]
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE,
                                     wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                     wintypes.LPARAM)
            user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
            user32.GetMonitorInfoW.restype = wintypes.BOOL
            user32.EnumDisplayMonitors.argtypes = [
                wintypes.HDC, ctypes.POINTER(wintypes.RECT), proc, wintypes.LPARAM]
            user32.EnumDisplayMonitors.restype = wintypes.BOOL
            areas = []
            def callback(monitor, hdc, rect, data):
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(info)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    r = info.rcWork
                    area = (r.left, r.top, r.right, r.bottom)
                    areas.append((info.dwFlags & 1, area))
                return True
            fn = proc(callback)
            if user32.EnumDisplayMonitors(None, None, fn, 0) and areas:
                return [a for _, a in sorted(areas, reverse=True)]
        except (OSError, AttributeError, TypeError, ValueError):
            pass
    return [(0, 0, root.winfo_screenwidth(), root.winfo_screenheight())]

class Records:
    def __init__(self, filename: Path):
        filename.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(filename))
        self.connection.row_factory = sqlite3.Row
        with self.connection:
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_day TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN
                        ('medication', 'insulin', 'blood_pressure', 'blood_glucose')),
                    sys_mmHg INTEGER,
                    dia_mmHg INTEGER,
                    pulse_bpm INTEGER,
                    glucose_mmol_l TEXT,
                    bp_session TEXT CHECK(bp_session IN ('AM', 'PM') OR bp_session IS NULL)
                )
            """)
            # Version 1 had no BP session field. Add one without modifying any
            # existing events. Old BP readings stay visible as "Unassigned (v1)".
            columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(events)")}
            if "bp_session" not in columns:
                self.connection.execute("""
                    ALTER TABLE events ADD COLUMN bp_session TEXT
                    CHECK(bp_session IN ('AM', 'PM') OR bp_session IS NULL)
                """)
            self.connection.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS unique_daily_tick
                ON events(local_day, kind)
                WHERE kind IN ('medication', 'insulin')
            """)
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS events_by_day ON events(local_day, id)
            """)

    def add(self, kind: str, **fields):
        if kind not in KIND_LABELS:
            raise ValueError("Unknown record type")
        if kind == "blood_pressure" and fields.get("bp_session") not in ("AM", "PM"):
            raise ValueError("Choose AM or PM for a new blood-pressure reading")
        now = local_now()
        columns = ["local_day", "recorded_at", "kind", *fields.keys()]
        values = [now.date().isoformat(), now.isoformat(timespec="seconds"), kind, *fields.values()]
        marks = ", ".join("?" for _ in columns)
        with self.connection:
            self.connection.execute(
                f"INSERT INTO events ({', '.join(columns)}) VALUES ({marks})", values
            )

    def today(self, day: str):
        result = {}
        rows = self.connection.execute(
            "SELECT * FROM events WHERE local_day = ? ORDER BY id", (day,)
        ).fetchall()
        for row in rows:
            kind = row["kind"]
            if kind == "blood_pressure":
                session = row["bp_session"]
                key = f"blood_pressure_{session.lower()}" if session in ("AM", "PM") else "legacy_blood_pressure"
                result[key] = row
            else:
                result[kind] = row
        return result

    def history(self, limit=None):
        sql = "SELECT * FROM events ORDER BY id DESC"
        return (self.connection.execute(sql + " LIMIT ?", (limit,)).fetchall()
                if limit is not None else self.connection.execute(sql).fetchall())

    def events_between(self, start: str, end: str):
        """Read-only snapshot for a selected reporting interval."""
        return self.connection.execute(
            "SELECT * FROM events WHERE local_day BETWEEN ? AND ? "
            "ORDER BY local_day, recorded_at, id", (start, end)
        ).fetchall()

    def count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def clear_history(self) -> int:
        """Delete all logged events in a transaction; do not touch settings or schema."""
        with self.connection:
            cursor = self.connection.execute("DELETE FROM events")
        return cursor.rowcount

    def undo_tick(self, kind: str, day: str):
        if kind not in ("medication", "insulin"):
            raise ValueError("Only daily ticks can be undone")
        with self.connection:
            self.connection.execute(
                "DELETE FROM events WHERE kind = ? AND local_day = ?", (kind, day)
            )

    def close(self):
        self.connection.close()


def pretty_time(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).strftime("%d/%m/%Y  %H:%M:%S")


def pretty_clock(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).strftime("%H:%M:%S")


def chore_name(row) -> str:
    if row["kind"] == "blood_pressure":
        session = row["bp_session"]
        return f"Blood pressure {session}" if session in ("AM", "PM") else "Blood pressure (v1)"
    return KIND_LABELS[row["kind"]]


def result_of(row) -> str:
    kind = row["kind"]
    if kind in ("medication", "insulin"):
        return "Confirmed done"
    if kind == "blood_pressure":
        return f"SYS {row['sys_mmHg']}  /  DIA {row['dia_mmHg']}  /  PULSE {row['pulse_bpm']}"
    return f"{row['glucose_mmol_l']} mmol/L"


def try_single_instance() -> bool:
    """Windows: avoid duplicate resident copies and restore an open window."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, "Local\\MedicalChoresMorning_v1")
        if not handle:
            return True
        globals()["_APP_MUTEX"] = handle
        if ctypes.get_last_error() == 183:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
            user32.FindWindowW.restype = wintypes.HWND
            for title in (APP_TITLE, "Medical Chores - Daily Checklist",
                          "Medical Chores - Morning Checklist"):
                hwnd = user32.FindWindowW(None, title)
                if hwnd:
                    user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
                    break
            return False
    except (OSError, AttributeError):
        pass
    return True


class MedicalChores(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(850, 700)
        # Reuse the original app-data directory; existing records and dark mode
        # remain untouched when upgrading. Window layout has its own JSON file.
        self.layout_path = storage_dir() / "window_state.json"
        self._layout_write_job = None
        self._last_normal_layout = None
        saved_layout = load_window_layout(self.layout_path)
        if saved_layout is not None:
            prepared = fit_layout_to_displays(saved_layout, display_work_areas(self))
            if os.name == "nt" and (prepared["x"] < 0 or prepared["y"] < 0):
                # Tk interprets negative geometry offsets as right/bottom-edge
                # distances, NOT Windows virtual-desktop coordinates. Use the
                # native API for monitors to the left/above the main display.
                self.geometry(f'{prepared["width"]}x{prepared["height"]}+0+0')
                self.after(120, lambda plan=prepared: self._move_to_virtual_coords(plan))
            else:
                self.geometry(layout_geometry(prepared))
            self._last_normal_layout = {k: prepared[k] for k in ("width", "height", "x", "y")}
        else:
            self.geometry("990x785")
        self.protocol("WM_DELETE_WINDOW", self.to_taskbar)
        self.data_dir = storage_dir()
        self.records = Records(self.data_dir / "medical_chores.sqlite3")
        self.settings_file = self.data_dir / "settings.json"
        self.theme_name = load_theme(self.settings_file)
        self.day = local_now().date().isoformat()
        self.latest = {}
        self._build()
        self.refresh()
        self.bind("<Configure>", self._on_configure, add="+")
        # Avoid recording the toolkit's initial geometry negotiation as if it
        # were the user's chosen layout.
        self.after(700, self._begin_layout_tracking)
        self.after(30_000, self.check_day)
        if saved_layout is not None and saved_layout.get("maximized"):
            # Zoom after Tk has mapped the window so the pre-zoom size is kept.
            self.after(250, self._restore_maximized)

    @property
    def c(self):
        return THEMES[self.theme_name]

    def _label(self, parent, text, *, size=11, bold=False, color=None, **kwargs):
        return tk.Label(
            parent, text=text, font=("Segoe UI", size, "bold" if bold else "normal"),
            fg=color or self.c["ink"], bg=parent.cget("bg"), **kwargs
        )

    def _button(self, parent, text, command, *, primary=True, width=15):
        c = self.c
        return tk.Button(
            parent, text=text, command=command, font=("Segoe UI", 10, "bold"),
            fg="#ffffff" if primary else c["ink"],
            bg=c["blue"] if primary else c["secondary"],
            activebackground=c["blue_hover"] if primary else c["secondary_hover"],
            activeforeground="#ffffff" if primary else c["ink"],
            disabledforeground=c["disabled_ink"],
            borderwidth=0, highlightthickness=0, relief="flat",
            cursor="hand2", padx=10, pady=7, width=width
        )

    def _card(self, parent, row, col, title, intro, *, col_span=1):
        c = self.c
        outer = tk.Frame(parent, bg=c["card"], highlightbackground=c["border"], highlightthickness=1)
        outer.grid(row=row, column=col, columnspan=col_span, sticky="nsew", padx=7, pady=6)
        interior = tk.Frame(outer, bg=c["card"])
        interior.pack(fill="both", expand=True, padx=15, pady=10)
        self._label(interior, title, size=13, bold=True).pack(anchor="w")
        self._label(interior, intro, size=10, color=c["muted"]).pack(anchor="w", pady=(1, 8))
        return interior

    def _entry(self, parent, width):
        c = self.c
        return tk.Entry(
            parent, width=width, font=("Segoe UI", 13), justify="center",
            bg=c["field"], fg=c["ink"], insertbackground=c["ink"],
            selectbackground=c["selected"], selectforeground=c["ink"],
            bd=1, relief="solid", highlightthickness=1,
            highlightcolor=c["blue"], highlightbackground=c["border"]
        )

    def _build(self):
        for widget in self.winfo_children():
            widget.destroy()
        c = self.c
        self.configure(bg=c["bg"])
        self.card_info = {}
        self.card_buttons = {}
        self.bp_entries = {}

        header = tk.Frame(self, bg=c["bg"])
        header.pack(fill="x", padx=19, pady=(13, 3))
        left_header = tk.Frame(header, bg=c["bg"])
        left_header.pack(side="left", anchor="w")
        self._label(left_header, "Medical Daily Checklist", size=21, bold=True).pack(anchor="w")
        self.date_label = self._label(left_header, "", color=c["muted"], size=10)
        self.date_label.pack(anchor="w", pady=(1, 0))
        theme_text = "☀  Light mode" if self.theme_name == "dark" else "☾  Dark mode"
        self._button(header, theme_text, self.toggle_theme, primary=False, width=15).pack(
            side="right", padx=(12, 0), anchor="n")
        self.count_label = self._label(header, "", size=11, bold=True, color=c["green"])
        self.count_label.pack(side="right", anchor="n", pady=11)

        tasks = tk.Frame(self, bg=c["bg"])
        tasks.pack(fill="x", padx=12, pady=(5, 0))
        tasks.columnconfigure(tuple(range(6)), weight=1, uniform="six")

        meds = self._card(tasks, 0, 0, "1   Medication", "All medicines together", col_span=2)
        self.card_info["medication"] = self._label(meds, "Not yet confirmed", color=c["muted"], size=10)
        self.card_info["medication"].pack(anchor="w", pady=(0, 7))
        actions = tk.Frame(meds, bg=c["card"])
        actions.pack(fill="x", anchor="w")
        self.card_buttons["medication"] = self._button(
            actions, "Mark taken", lambda: self.mark_tick("medication"), width=14)
        self.card_buttons["medication"].pack(side="left")
        self._undo_button(actions, "medication")

        insulin = self._card(tasks, 0, 2, "2   Insulin", "Confirm after injecting", col_span=2)
        self.card_info["insulin"] = self._label(insulin, "Not yet confirmed", color=c["muted"], size=10)
        self.card_info["insulin"].pack(anchor="w", pady=(0, 7))
        actions = tk.Frame(insulin, bg=c["card"])
        actions.pack(fill="x", anchor="w")
        self.card_buttons["insulin"] = self._button(
            actions, "Mark injected", lambda: self.mark_tick("insulin"), width=14)
        self.card_buttons["insulin"].pack(side="left")
        self._undo_button(actions, "insulin")

        glucose = self._card(tasks, 0, 4, "3   Blood glucose", "Reading in mmol/L", col_span=2)
        glucose_content = tk.Frame(glucose, bg=c["card"])
        glucose_content.pack(fill="x", pady=(0, 6))
        entry_group = tk.Frame(glucose_content, bg=c["card"])
        entry_group.pack(side="left", padx=(0, 9))
        self._label(entry_group, "mmol/L", size=9, bold=True, color=c["muted"]).pack(anchor="w")
        self.glucose_entry = self._entry(entry_group, 8)
        self.glucose_entry.pack(anchor="w", pady=(3, 0), ipady=4)
        self.glucose_entry.bind("<Return>", lambda event: self.record_glucose())
        self._button(glucose_content, "Record", self.record_glucose, width=8).pack(
            side="left", anchor="s", pady=(18, 0))
        self.card_info["blood_glucose"] = self._label(
            glucose, "No reading today", size=10, color=c["muted"])
        self.card_info["blood_glucose"].pack(anchor="w", pady=(1, 0))

        self._bp_card(tasks, 1, 0, "AM", "4   Blood pressure — AM", "Morning reading")
        self._bp_card(tasks, 1, 3, "PM", "5   Blood pressure — PM", "Evening reading")

        history_header = tk.Frame(self, bg=c["bg"])
        history_header.pack(fill="x", padx=20, pady=(9, 4))
        self._label(history_header, "Recorded history", size=13, bold=True).pack(side="left")
        self._button(history_header, "Export CSV", self.export_csv, primary=False, width=11).pack(side="right")
        self._button(history_header, "Reports...", self.open_reports, primary=False,
                     width=10).pack(side="right", padx=(0, 8))
        clear_button = self._button(
            history_header, "Clear history", self.clear_history, primary=False, width=13)
        clear_button.configure(fg=c["danger"], activeforeground=c["danger"])
        clear_button.pack(side="right", padx=(0, 8))
        self._label(history_header, "Most recent first", size=10, color=c["muted"]).pack(
            side="right", padx=12)

        history = tk.Frame(self, bg=c["card"], highlightbackground=c["border"], highlightthickness=1)
        history.pack(fill="both", expand=True, padx=19, pady=(1, 6))
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Medical.Treeview", background=c["card"], foreground=c["ink"],
                        fieldbackground=c["card"], bordercolor=c["border"],
                        rowheight=26, font=("Segoe UI", 10))
        style.configure("Medical.Treeview.Heading", background=c["secondary"], foreground=c["ink"],
                        bordercolor=c["border"], font=("Segoe UI", 10, "bold"))
        style.map("Medical.Treeview", background=[("selected", c["selected"])],
                  foreground=[("selected", c["ink"])])
        style.map("Medical.Treeview.Heading", background=[("active", c["secondary_hover"])])
        columns = ("When", "Task", "Result")
        self.table = ttk.Treeview(history, columns=columns, show="headings", height=5,
                                  style="Medical.Treeview")
        for title, width, stretch in (("When", 175, False), ("Task", 175, False), ("Result", 400, True)):
            self.table.heading(title, text=title)
            self.table.column(title, width=width, minwidth=100, stretch=stretch, anchor="w")
        self.table.tag_configure("odd", background=c["stripe"], foreground=c["ink"])
        self.table.tag_configure("even", background=c["card"], foreground=c["ink"])
        scrollbar = ttk.Scrollbar(history, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.table.pack(fill="both", expand=True, padx=(5, 0), pady=5)

        footer = tk.Frame(self, bg=c["bg"])
        footer.pack(fill="x", padx=19, pady=(0, 12))
        self._label(footer, "Saved locally as you go · Close = minimise to taskbar",
                    color=c["muted"], size=10).pack(side="left", anchor="center")
        self._button(footer, "Exit app", self.exit_app, primary=False, width=9).pack(side="right")
        self._button(footer, "To taskbar", self.to_taskbar, primary=False, width=11).pack(
            side="right", padx=(0, 7))

    def _bp_card(self, parent, row, col, session, title, intro):
        c = self.c
        bp = self._card(parent, row, col, title, intro, col_span=3)
        fields = tk.Frame(bp, bg=c["card"])
        fields.pack(fill="x", pady=(0, 8))
        entries = []
        for name, unit in (("SYS", "mmHg"), ("DIA", "mmHg"), ("PULSE", "bpm")):
            section = tk.Frame(fields, bg=c["card"])
            section.pack(side="left", padx=(0, 13))
            self._label(section, f"{name} ({unit})", size=9, bold=True,
                        color=c["muted"]).pack(anchor="w")
            entry = self._entry(section, 7)
            entry.pack(anchor="w", pady=(3, 0), ipady=4)
            entry.bind("<Return>", lambda event, slot=session: self.record_bp(slot))
            entries.append(entry)
        self.bp_entries[session] = tuple(entries)
        actions = tk.Frame(bp, bg=c["card"])
        actions.pack(fill="x")
        self._button(actions, f"Record {session} BP", lambda slot=session: self.record_bp(slot),
                     width=15).pack(side="left")
        self.card_info[f"blood_pressure_{session.lower()}"] = self._label(
            bp, "No reading today", size=10, color=c["muted"])
        self.card_info[f"blood_pressure_{session.lower()}"].pack(anchor="w", pady=(8, 0))

    def _undo_button(self, parent, kind):
        c = self.c
        button = tk.Button(
            parent, text="Undo mistake", command=lambda: self.undo_tick(kind),
            font=("Segoe UI", 9), fg=c["blue"] if self.theme_name == "light" else "#9bc7ff",
            bg=c["card"], activeforeground=c["ink"], activebackground=c["secondary"],
            borderwidth=0, cursor="hand2", padx=10, relief="flat")
        button.pack(side="left")
        self.card_buttons[kind + "_undo"] = button

    def toggle_theme(self):
        # Keep text currently being typed when changing the appearance.
        draft_bp = {session: [entry.get() for entry in fields]
                    for session, fields in self.bp_entries.items()}
        draft_glucose = self.glucose_entry.get()
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        try:
            save_theme(self.settings_file, self.theme_name)
        except OSError as exc:
            messagebox.showwarning("Theme not saved", f"Appearance changed, but could not save preference:\n{exc}", parent=self)
        self._build()
        for session, values in draft_bp.items():
            for entry, value in zip(self.bp_entries[session], values):
                entry.insert(0, value)
        self.glucose_entry.insert(0, draft_glucose)
        self.refresh()

    def check_day(self):
        actual_day = local_now().date().isoformat()
        if self.day != actual_day:
            self.day = actual_day
            self.refresh()
        self.after(30_000, self.check_day)

    def refresh(self):
        c = self.c
        self.latest = self.records.today(self.day)
        self.date_label.config(text=datetime.fromisoformat(self.day).strftime("%A %d %B %Y"))
        keys = ("medication", "insulin", "blood_pressure_am", "blood_pressure_pm", "blood_glucose")
        count = sum(key in self.latest for key in keys)
        self.count_label.config(text=f"{count} of 5 recorded today")
        for kind in ("medication", "insulin"):
            event = self.latest.get(kind)
            if event:
                self.card_info[kind].config(
                    text=f"✓  Confirmed at {pretty_clock(event['recorded_at'])}",
                    fg=c["green"], font=CONFIRMED_STATUS_FONT)
                self.card_buttons[kind].config(
                    state="disabled", bg=c["disabled"], fg=c["disabled_ink"])
                self.card_buttons[kind + "_undo"].config(state="normal")
            else:
                self.card_info[kind].config(
                    text="Not yet confirmed", fg=c["muted"], font=PENDING_STATUS_FONT)
                self.card_buttons[kind].config(state="normal", bg=c["blue"], fg="#ffffff")
                self.card_buttons[kind + "_undo"].config(state="disabled")
        for session in ("AM", "PM"):
            key = f"blood_pressure_{session.lower()}"
            bp = self.latest.get(key)
            if bp:
                self.card_info[key].config(
                    text=(f"✓  {bp['sys_mmHg']}/{bp['dia_mmHg']}, pulse {bp['pulse_bpm']}"
                          f" at {pretty_clock(bp['recorded_at'])}"),
                    fg=c["green"], font=CONFIRMED_STATUS_FONT)
            else:
                self.card_info[key].config(
                    text="No reading today", fg=c["muted"], font=PENDING_STATUS_FONT)
        glucose = self.latest.get("blood_glucose")
        if glucose:
            self.card_info["blood_glucose"].config(
                text=f"✓  {glucose['glucose_mmol_l']} mmol/L at {pretty_clock(glucose['recorded_at'])}",
                fg=c["green"], font=CONFIRMED_STATUS_FONT)
        else:
            self.card_info["blood_glucose"].config(
                text="No reading today", fg=c["muted"], font=PENDING_STATUS_FONT)
        self.table.delete(*self.table.get_children())
        for i, row in enumerate(self.records.history(limit=100)):
            self.table.insert("", "end", tags=("odd" if i % 2 else "even",), values=(
                pretty_time(row["recorded_at"]), chore_name(row), result_of(row)))

    def mark_tick(self, kind):
        self._sync_day()
        if kind in self.latest:
            return
        try:
            self.records.add(kind)
        except sqlite3.IntegrityError:
            pass
        except sqlite3.Error as exc:
            messagebox.showerror("Unable to save", f"Could not save your confirmation:\n{exc}", parent=self)
        self.refresh()

    def _sync_day(self):
        actual_day = local_now().date().isoformat()
        if self.day != actual_day:
            self.day = actual_day
            self.refresh()

    def undo_tick(self, kind):
        self._sync_day()
        if kind not in self.latest:
            return
        if not messagebox.askyesno(
            "Undo confirmation?",
            f"Remove today's {KIND_LABELS[kind].lower()} confirmation?\n\n"
            "Use this only if the button was pressed by mistake.", parent=self):
            return
        try:
            self.records.undo_tick(kind, self.day)
        except sqlite3.Error as exc:
            messagebox.showerror("Unable to undo", f"Could not undo this confirmation:\n{exc}", parent=self)
        self.refresh()

    def record_bp(self, session):
        self._sync_day()
        fields = tuple(entry.get().strip() for entry in self.bp_entries[session])
        try:
            if any(not val.isascii() or not val.isdecimal() for val in fields):
                raise ValueError("Whole numbers only")
            sys_val, dia_val, pulse_val = map(int, fields)
            if not (1 <= sys_val <= 350 and 1 <= dia_val <= 250 and 1 <= pulse_val <= 300):
                raise ValueError("Outside entry range")
            if sys_val <= dia_val:
                raise ValueError("SYS must be greater than DIA")
        except ValueError:
            messagebox.showwarning(
                "Check blood pressure entries",
                "Enter SYS, DIA and PULSE as positive whole numbers.\n"
                "SYS must be greater than DIA. Check values against your monitor.", parent=self)
            return
        try:
            self.records.add("blood_pressure", bp_session=session, sys_mmHg=sys_val,
                             dia_mmHg=dia_val, pulse_bpm=pulse_val)
        except (sqlite3.Error, ValueError) as exc:
            messagebox.showerror("Unable to save", f"Could not save your blood pressure:\n{exc}", parent=self)
            return
        for entry in self.bp_entries[session]:
            entry.delete(0, "end")
        self.refresh()

    def record_glucose(self):
        self._sync_day()
        entered = self.glucose_entry.get().strip().replace(",", ".")
        try:
            value = Decimal(entered)
            if not value.is_finite() or not Decimal("0.1") <= value <= Decimal("99.9"):
                raise ValueError("Outside entry range")
            if abs(value.as_tuple().exponent) > 2:
                raise ValueError("Too many decimal places")
        except (InvalidOperation, ValueError):
            messagebox.showwarning("Check blood glucose entry",
                                   "Enter a numeric blood glucose reading in mmol/L, e.g. 6.4.", parent=self)
            return
        try:
            self.records.add("blood_glucose", glucose_mmol_l=format(value, "f"))
        except sqlite3.Error as exc:
            messagebox.showerror("Unable to save", f"Could not save your blood glucose:\n{exc}", parent=self)
            return
        self.glucose_entry.delete(0, "end")
        self.refresh()

    def clear_history(self):
        """Clear the entire active log only after an explicit, default-No warning."""
        try:
            total = self.records.count()
        except sqlite3.Error as exc:
            messagebox.showerror("Unable to check history", f"Could not check saved records:\n{exc}", parent=self)
            return
        if total == 0:
            messagebox.showinfo("History is empty", "There are no saved records to clear.", parent=self)
            return
        confirmation = messagebox.askyesno(
            "Clear ALL recorded history?",
            f"Do you really want to clear history?\n\n"
            f"This will delete ALL {total} saved entries from the application, "
            "including today's medication and insulin confirmations, "
            "blood-pressure readings and blood-glucose readings.\n\n"
            "Today's checklist will reset to incomplete. This cannot be undone "
            "inside the application. Any separate CSV exports or backups "
            "will NOT be deleted.\n\n"
            "Are you sure you want to continue?",
            icon="warning", default="no", parent=self)
        if not confirmation:
            return
        try:
            self.records.clear_history()
        except sqlite3.Error as exc:
            messagebox.showerror("Unable to clear history", f"Could not clear saved records:\n{exc}", parent=self)
            return
        self._sync_day()
        self.refresh()
        messagebox.showinfo("History cleared", "The recorded history has been cleared.\nToday's checklist is now empty.", parent=self)

    def open_reports(self):
        """Offer a print-ready PDF for the clinician without altering the log."""
        c = self.c
        window = tk.Toplevel(self)
        window.title("Medical report - save or print")
        window.configure(bg=c["bg"])
        window.resizable(False, False)
        window.transient(self)
        window.grab_set()
        frame = tk.Frame(window, bg=c["bg"])
        frame.pack(fill="both", expand=True, padx=22, pady=18)
        self._label(frame, "Medical report", size=17, bold=True).pack(anchor="w")
        self._label(frame, "Select the interval ending today", size=10,
                    color=c["muted"]).pack(anchor="w", pady=(2, 10))
        selected = tk.StringVar(value="7 days")
        range_label = self._label(frame, "", size=10, bold=True)

        def update_range(*_):
            start, end = period_dates(selected.get())
            range_label.config(text=f"{start:%d %B %Y} to {end:%d %B %Y} (inclusive)")

        for name in PERIODS:
            tk.Radiobutton(frame, text=name, variable=selected, value=name,
                           command=update_range, font=("Segoe UI", 11),
                           bg=c["bg"], fg=c["ink"], selectcolor=c["field"],
                           activebackground=c["bg"], activeforeground=c["ink"],
                           anchor="w").pack(anchor="w", pady=2)
        range_label.pack(anchor="w", pady=(7, 12))
        update_range()
        self._label(frame, "Patient name (optional, for the report only)",
                    size=10, color=c["muted"]).pack(anchor="w")
        patient_input = tk.Entry(frame, width=42, font=("Segoe UI", 11),
                                 bg=c["field"], fg=c["ink"],
                                 insertbackground=c["ink"], relief="solid", bd=1)
        patient_input.pack(anchor="w", fill="x", pady=(4, 10), ipady=5)
        self._label(frame, "Landscape A4 PDF · all saved readings · blanks mean not recorded",
                    size=9, color=c["muted"]).pack(anchor="w", pady=(0, 14))

        def write_report(open_after=False):
            self._sync_day()
            choice = selected.get()
            start, end = period_dates(choice)
            default_name = (f"Medical-Daily-Checklist_{start:%Y-%m-%d}"
                            f"_to_{end:%Y-%m-%d}.pdf")
            destination = filedialog.asksaveasfilename(
                parent=window, title="Save your medical report",
                initialfile=default_name, defaultextension=".pdf",
                filetypes=[("PDF reports", "*.pdf")])
            if not destination:
                return
            try:
                rows = self.records.events_between(start.isoformat(), end.isoformat())
                _start, _end, pages = generate_report_pdf(
                    destination, choice, rows, today=end,
                    patient=patient_input.get())
            except (OSError, ValueError, sqlite3.Error) as exc:
                messagebox.showerror("Could not create report",
                                     f"The report could not be saved:\n{exc}", parent=window)
                return
            if open_after:
                try:
                    if os.name == "nt":
                        os.startfile(str(Path(destination).resolve()))
                    else:
                        import subprocess
                        subprocess.Popen(["xdg-open", destination], close_fds=True)
                except (OSError, AttributeError) as exc:
                    messagebox.showwarning("Report saved",
                        f"The PDF was saved, but could not be opened automatically:\n{destination}\n\n{exc}",
                        parent=window)
                    return
                messagebox.showinfo("Report ready to print",
                    f"Saved {pages} page(s) to:\n{destination}\n\n"
                    "In your PDF viewer, use Ctrl+P or the Print command.",
                    parent=window)
            else:
                messagebox.showinfo("Medical report saved",
                    f"Saved {pages} page(s) to:\n{destination}", parent=window)

        buttons = tk.Frame(frame, bg=c["bg"])
        buttons.pack(fill="x")
        self._button(buttons, "Save PDF", lambda: write_report(False),
                     width=11).pack(side="left")
        self._button(buttons, "Save + Print", lambda: write_report(True),
                     width=12, primary=False).pack(side="left", padx=9)
        self._button(buttons, "Cancel", window.destroy,
                     width=9, primary=False).pack(side="right")
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.update_idletasks()
        # Place near the parent, without changing the saved main-window geometry.
        x = self.winfo_rootx() + max(12, (self.winfo_width()-window.winfo_width())//2)
        y = self.winfo_rooty() + max(12, (self.winfo_height()-window.winfo_height())//2)
        window.geometry(f"+{x}+{y}")
        window.focus_set()

    def export_csv(self):
        destination = filedialog.asksaveasfilename(
            parent=self, title="Export full medical daily checklist history",
            initialfile=f"medical-daily-checklist-{self.day}.csv", defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")])
        if not destination:
            return
        try:
            with open(destination, "w", newline="", encoding="utf-8-sig") as file:
                writer = csv.writer(file)
                writer.writerow(["Recorded date", "Recorded time", "UTC offset", "Task",
                                 "BP period", "Details", "SYS (mmHg)", "DIA (mmHg)",
                                 "PULSE (bpm)", "Glucose (mmol/L)"])
                for row in reversed(self.records.history()):
                    stamp = datetime.fromisoformat(row["recorded_at"])
                    session = (row["bp_session"] or "Unassigned (v1)") if row["kind"] == "blood_pressure" else ""
                    writer.writerow([
                        stamp.strftime("%Y-%m-%d"), stamp.strftime("%H:%M:%S"),
                        stamp.strftime("%z"), chore_name(row), session, result_of(row),
                        row["sys_mmHg"] if row["sys_mmHg"] is not None else "",
                        row["dia_mmHg"] if row["dia_mmHg"] is not None else "",
                        row["pulse_bpm"] if row["pulse_bpm"] is not None else "",
                        row["glucose_mmol_l"] if row["glucose_mmol_l"] is not None else "",
                    ])
        except OSError as exc:
            messagebox.showerror("Export failed", f"Could not write your CSV file:\n{exc}", parent=self)
            return
        messagebox.showinfo("History exported", f"Saved your complete history to:\n{destination}", parent=self)

    def _move_to_virtual_coords(self, layout):
        if os.name != "nt":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND,
                                            ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int,
                                            wintypes.UINT]
            user32.SetWindowPos.restype = wintypes.BOOL
            outer_hwnd = user32.GetAncestor(self.winfo_id(), 2)  # GA_ROOT
            if outer_hwnd:
                # Move the frame, not Tk's embedded client HWND. The chosen
                # client size was set through Tk before this callback.
                # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
                user32.SetWindowPos(outer_hwnd, None, layout["x"], layout["y"],
                                     0, 0, 0x0001 | 0x0004 | 0x0010)
        except (OSError, AttributeError, tk.TclError):
            pass

    def _restore_maximized(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            # Tk implementations without zoomed state keep the restored layout.
            pass

    def _begin_layout_tracking(self):
        self._track_layout = True
        # Save the settled initial location as well, so an immediate resize
        # or shutdown is not lost before the first configure debounce.
        self._save_window_layout()

    def _on_configure(self, event):
        if event.widget is not self or not getattr(self, "_track_layout", False):
            return
        if self._layout_write_job is not None:
            self.after_cancel(self._layout_write_job)
        self._layout_write_job = self.after(650, self._save_window_layout)

    def _save_window_layout(self):
        self._layout_write_job = None
        try:
            state = self.state()
            if state not in ("normal", "zoomed"):
                # Never replace a good position with the iconified window.
                return
            if state == "normal":
                self.update_idletasks()
                layout = {
                    "width": self.winfo_width(), "height": self.winfo_height(),
                    "x": self.winfo_x(), "y": self.winfo_y(),
                }
                if layout["width"] < 850 or layout["height"] < 700:
                    return
                self._last_normal_layout = layout
            if not self._last_normal_layout:
                return
            save_window_layout(self.layout_path,
                               {**self._last_normal_layout, "maximized": state == "zoomed"})
        except (OSError, ValueError, tk.TclError) as exc:
            # Never interrupt the medical checklist for a non-critical setting.
            print(f"Could not save window position: {exc}", file=__import__("sys").stderr)

    def to_taskbar(self):
        if self._layout_write_job is not None:
            self.after_cancel(self._layout_write_job)
            self._layout_write_job = None
        self._save_window_layout()
        self.iconify()

    def exit_app(self):
        if messagebox.askyesno("Exit Medical Daily Checklist?",
                               "Exit the application? Your recorded data will remain saved.\n\n"
                               "It will run again when you next sign in to Windows.", parent=self):
            if self._layout_write_job is not None:
                self.after_cancel(self._layout_write_job)
                self._layout_write_job = None
            self._save_window_layout()
            self.records.close()
            self.destroy()


def main():
    if not try_single_instance():
        return
    app = MedicalChores()
    app.mainloop()


if __name__ == "__main__":
    main()
