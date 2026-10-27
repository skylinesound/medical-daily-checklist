# Medical Daily Checklist

**Offline daily health record and reminder application for Windows.**

Version **5.2** records medication and insulin confirmations, morning/evening blood pressure and pulse, and blood glucose measurements, with timestamps. It also produces clinician-friendly, printable A4 PDF summaries showing reporting-period averages that ignore zero and missing readings.

## Features

- Tick off medication and insulin confirmations.
- Record morning and evening blood pressure (systolic, diastolic and pulse).
- Record blood glucose in mmol/L.
- Local time-stamped history, CSV export and printable PDF reports.
- 7-day, 14-day, 1-month and 3-month reports with period averages.
- Light/dark modes, larger bold confirmations, remembered window position.
- All data stored locally in SQLite; no accounts, network connection or subscriptions.

## Download and install (Windows)

For non-programmers, **download the package from the GitHub Releases page** (when the maintainer has uploaded the first release), rather than using the green 'Code' download menu.

Requirements: **Windows 10 or 11; Python 3.9 or newer with Tkinter/Tcl/Tk**. This package is not yet a standalone Windows executable.

1. Download the latest Windows ZIP from **Releases** and extract it.
2. Close any running Medical Daily Checklist using **Exit app** (the X minimises it).
3. Double-click `INSTALL_WINDOWS.cmd`.
4. The program installs for your Windows user without administrator rights and opens after installation.

**Important:** The current installer also adds the application to **Windows sign-in startup** automatically (for your account only). This is intentional for the daily reminder workflow and should be made optional in a future release.

### Existing users

The installation process leaves existing saved records and settings in place. For full upgrade instructions, see [README.txt](README.txt).

## Data and privacy

Medical Daily Checklist does **not** upload entries to any server. Data are saved locally at:

`%LOCALAPPDATA%\MedicalChores\medical_chores.sqlite3`

Settings and saved window layout are stored in the same directory. PDF and CSV exports are stored in the location you choose.

**Health information is sensitive:** the SQLite database and exported reports are **not encrypted by this application**. Protect your Windows account and drive, make secure backups and keep exported reports private. Do not upload your real database, screenshots containing real readings, or clinician reports to a public GitHub repository.

## Running from source

The application uses the **Python standard library only**, with Tkinter for its UI. On a machine with Tkinter installed, start with:

```shell
python medical_chores.pyw
```

On Windows you can also double-click `medical_chores.pyw` if `.pyw` is associated with Python. `medical_report.py` must be in the same directory as `medical_chores.pyw`.

## Scope and medical disclaimer

This is a personal record-keeping and reminder tool, **not a medical device**, a diagnostic system or a substitute for professional medical advice. It does not confirm that medicines were actually taken or that readings are clinically correct. The averages are arithmetic summaries, not a medical assessment; discuss interpretation with a healthcare professional. A blank field means *no entry recorded*, not necessarily *a treatment missed*.

## Feedback and contributions

Open a GitHub **Issue** for a bug report, usability improvement or feature request. **Do not post personal health measurements** in Issues, screenshots or logs. Use fictitious data for examples.

## Licence

A licence must be selected **before publication** if you want people to be able to modify and redistribute this project. The MIT licence is one simple option; the maintainer can add it through GitHub's repository setup or `Add file > Create new file > LICENSE`. The choice belongs to the project owner.
