"""Install Medical Daily Checklist for the current Windows account. No admin rights needed."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import winreg

APP_NAME = "MedicalChoresMorning"
SOURCE = Path(__file__).resolve().parent / "medical_chores.pyw"
REPORT_SOURCE = Path(__file__).resolve().parent / "medical_report.py"


def ps_quote(value: str) -> str:
    """PowerShell single-quoted literal."""
    return "'" + value.replace("'", "''") + "'"


def make_start_menu_shortcut(python_exe: Path, program: Path):
    """Best-effort per-user shortcut. Startup itself does not depend on this."""
    powershell = shutil.which("powershell.exe")
    appdata = os.environ.get("APPDATA")
    if not powershell or not appdata:
        print("Start-menu shortcut skipped (PowerShell/AppData unavailable).")
        return
    start_menu = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    start_menu.mkdir(parents=True, exist_ok=True)
    shortcut = start_menu / "Medical Daily Checklist.lnk"
    ps_script = (
        "$shell = New-Object -ComObject WScript.Shell; "
        f"$link = $shell.CreateShortcut({ps_quote(str(shortcut))}); "
        f"$link.TargetPath = {ps_quote(str(python_exe))}; "
        f"$link.Arguments = {ps_quote(subprocess.list2cmdline([str(program)]))}; "
        f"$link.WorkingDirectory = {ps_quote(str(program.parent))}; "
        "$link.Description = 'Open Medical Daily Checklist'; "
        "$link.Save()"
    )
    try:
        subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", ps_script],
                       check=True, capture_output=True, text=True)
        print("Start menu: Medical Daily Checklist")
        # The old shortcut was installed by the previous versions. Its target
        # is the same program path, so retire it when our new shortcut works.
        old_shortcut = start_menu / "Medical Chores.lnk"
        try:
            old_shortcut.unlink(missing_ok=True)
        except OSError:
            print("Old Start-menu shortcut remains (may be removed manually).")
    except (OSError, subprocess.CalledProcessError):
        print("Start-menu shortcut could not be created; automatic startup still works.")


def install():
    try:
        import tkinter  # noqa - required for the GUI
    except ImportError:
        raise RuntimeError("This Python installation doesn't include Tkinter. Install Python with Tcl/Tk support.")
    dest = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MedicalChores" / "App"
    dest.mkdir(parents=True, exist_ok=True)
    # Keep a one-time database backup before overwriting the installed app.
    # Existing app records and settings remain in their original location.
    existing_db = dest.parent / "medical_chores.sqlite3"
    backup_db = dest.parent / "medical_chores.before-v5.sqlite3"
    if existing_db.is_file() and not backup_db.exists():
        try:
            with sqlite3.connect(str(existing_db)) as source_db:
                with sqlite3.connect(str(backup_db)) as backup:
                    source_db.backup(backup)
            print("Existing records backed up to:", backup_db)
        except (OSError, sqlite3.Error) as exc:
            # Do not silently proceed with a migration if the backup failed.
            try:
                backup_db.unlink(missing_ok=True)
            except OSError:
                pass
            raise RuntimeError(f"Could not back up existing records: {exc}") from exc
    program = dest / "medical_chores.pyw"
    shutil.copy2(SOURCE, program)
    shutil.copy2(REPORT_SOURCE, dest / "medical_report.py")

    # pythonw.exe starts the app without a black console window.
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    runner = pythonw if pythonw.is_file() else Path(sys.executable)
    if not pythonw.is_file():
        print("Note: pythonw.exe not found; Windows may show a console on launch.")

    # HKCU Run executes on this account's sign-in, not system-wide. No VBS needed.
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
          r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                          subprocess.list2cmdline([str(runner), str(program)]))
    make_start_menu_shortcut(runner, program)
    print("Medical Daily Checklist v5.2 installed successfully.")
    print("Starts automatically at Windows sign-in (for this account only).")
    print("Program:", program)
    print("Saved records:", dest.parent / "medical_chores.sqlite3")
    print("Opening Medical Daily Checklist now...")
    subprocess.Popen([str(runner), str(program)], close_fds=True)


if __name__ == "__main__":
    if os.name != "nt":
        print("This installer is for Windows. On Linux run: python3 medical_chores.pyw")
        sys.exit(1)
    try:
        install()
    except Exception as exc:
        print("Installation could not complete:", exc)
        sys.exit(1)
