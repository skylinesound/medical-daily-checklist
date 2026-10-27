MEDICAL DAILY CHECKLIST - VERSION 5.2
===================================
Offline Windows application: medication, insulin, glucose, AM/PM blood pressure.

NEW IN VERSION 5.2 - AVERAGE MEASUREMENTS ON PDF REPORTS
---------------------------------------------------------
Each report now includes an AVERAGE row underneath the daily measurements,
showing the reporting-period mean for:
 - AM blood pressure: SYS, DIA and pulse.
 - PM blood pressure: SYS, DIA and pulse.
 - Blood glucose (mmol/L).

Averages include all readings within the selected report period, including
multiple readings on one day. Zero, empty and invalid measurements do not
contribute to averages; if a column has no valid measurements its average
is left blank. Means display one decimal place.
Older BP entries without AM/PM labels remain in their separate historical
section and have their own AVERAGE row; they are never mixed into the AM/PM
means. If necessary, the averages are printed on a new page to prevent
overlapping the footer. The saved data are untouched.

NEW IN VERSION 5.1 - EASIER-TO-READ CONFIRMED FIELDS
----------------------------------------------------
Recorded / confirmed items now appear in 14-point bold Segoe UI text:
 - Medication and insulin confirmation times
 - Blood glucose reading and its recorded time
 - AM and PM blood pressure readings and their recorded times

The unrecorded status messages remain in their original smaller text.
No changes were made to your saved records, entry boxes, CSV exports,
or the calculation/recording logic in version 5.1.

NEW IN VERSION 5 - CLINICIAN REPORTS
------------------------------------
Click "Reports..." beside Export CSV in the application's Recorded History area.
Select: 7 days, 14 days, 1 month, or 3 months (ending today).
Optionally type a patient name; this is used ONLY for the PDF being produced
and is not saved in application settings.

"Save PDF" writes an A4 landscape report to a folder you choose.
"Save + Print" saves the PDF and opens it in your normal PDF viewer;
choose the viewer's Print command (usually Ctrl+P). It does not print
silently or select a printer without your approval.

The PDF contains:
 - One or more rows for every date in the selected period.
 - Medication and insulin tick marks with confirmation times.
 - Separate AM and PM BP groups, each with SYS, DIA, PULSE and recorded time.
 - Blood glucose readings in mmol/L with recorded times.
 - Every saved BP/glucose reading, even when multiple were made on a day.
 - Older readings with no AM/PM label in a separate clearly marked section.
 - Reporting-period averages under the measurement columns (new in v5.2).
 - Clear titles, units, reporting dates, generation timestamp and page numbers.
 - A note that blank cells mean "not recorded", not necessarily "not done".

The report itself uses a white page with restrained dark blue and teal headings
for clear printing, regardless of whether the application is in dark mode.

UPGRADE FROM VERSION 5.1 (OR EARLIER)
----------------------
1. In the running Medical Daily Checklist choose "Exit app".
   (The window X only minimises to the taskbar.)
2. Extract this entire ZIP to a folder.
3. Double-click INSTALL_WINDOWS.cmd.
4. The installer retains your exact existing data directory and autostart
   registry entry, and opens version 5.2 when installation finishes.
5. Use Reports... to save or print your first report.

The installed app includes medical_chores.pyw and medical_report.py, both
necessary. Do not remove medical_report.py from the installed App directory.

RECORDS AND SETTINGS - PRESERVED
--------------------------------
SQLite database:
  %LOCALAPPDATA%\MedicalChores\medical_chores.sqlite3
Dark mode:
  %LOCALAPPDATA%\MedicalChores\settings.json
Window position and size:
  %LOCALAPPDATA%\MedicalChores\window_state.json

The installer creates a separate one-time backup before upgrading:
  %LOCALAPPDATA%\MedicalChores\medical_chores.before-v5.sqlite3

The earlier backups and exported CSV/PDF files are not altered.
Windows startup and the program's title stay "Medical Daily Checklist".

ALL EARLIER FEATURES KEPT
-------------------------
- One daily medication tick, one daily insulin tick.
- AM and PM SYS/DIA/PULSE readings and glucose entries (mmol/L).
- Individual time stamps, local SQLite storage, and chronological history.
- CSV export and clear history with a default-No warning.
- Light/dark switch, saved size and position, multi-monitor support.
- Close to taskbar and automatic start at Windows sign-in.

REQUIREMENTS
------------
Windows 10/11, Python 3.9+ with Tkinter/Tcl/Tk. No pip install or external
PDF libraries; the PDF writer is part of the standard-library-only program.
No internet, subscriptions or cloud services are needed.

IMPORTANT
---------
This is a self-recorded checklist, not a medical device. Completion marks
are entered by you, not verified by a clinician. Blank cells in the report
mean that no entry was logged, and are not evidence a treatment was omitted.
Use the original blood-pressure monitor or glucose meter record if you need
independent confirmation of any measurement. Keep your exported PDFs private,
as they may contain personal health information.
