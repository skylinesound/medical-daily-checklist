"""Offline A4 landscape PDF reports for Medical Daily Checklist.

No additional packages: a small, fixed-layout PDF writer uses PDF's built-in
Helvetica fonts. Every stored reading inside the period is included, with
extra same-day readings on additional lines. The underlying log is read only.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

PAGE_W, PAGE_H = 842.0, 595.0  # A4 landscape, PDF points
MARGIN = 28.0
COLS = (92, 78, 78, 52, 52, 49, 56, 52, 52, 49, 56, 120)
assert sum(COLS) == PAGE_W - 2 * MARGIN
NAVY = (0.10, 0.17, 0.28)
TEAL = (0.02, 0.43, 0.42)
GREY = (0.37, 0.43, 0.50)
LIGHT = (0.94, 0.96, 0.98)
PALE = (0.975, 0.984, 0.992)
RULE = (0.80, 0.84, 0.88)
WHITE = (1, 1, 1)
TEXT = (0.14, 0.19, 0.25)

PERIODS = {"7 days": (7, None), "14 days": (14, None),
           "1 month": (None, 1), "3 months": (None, 3)}


def _month_shift(value: date, amount: int) -> date:
    idx = value.year * 12 + value.month - 1 + amount
    year, monthidx = divmod(idx, 12)
    month = monthidx + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def period_dates(period: str, today: date | None = None):
    """Inclusive dates, ending today. Calendar months are not fixed 30-day blocks."""
    today = today or datetime.now().astimezone().date()
    if period not in PERIODS:
        raise ValueError("Unknown reporting interval")
    days, months = PERIODS[period]
    if days is not None:
        return today - timedelta(days=days - 1), today
    # Subtract calendar months from the exclusive interval end. This gives an
    # intuitive rolling 'last calendar month(s) including today' selection.
    return _month_shift(today + timedelta(days=1), -months), today


def _pdf_literal(value: str) -> str:
    """Escape parentheses/backslashes and non-ASCII WinAnsi PDF string bytes."""
    b = str(value).encode("cp1252", errors="replace")
    out = []
    for c in b:
        if c in (40, 41, 92):
            out.append("\\" + chr(c))
        elif c < 32 or c >= 127:
            out.append("\\%03o" % c)
        else:
            out.append(chr(c))
    return "".join(out)


def _color(rgb):
    return " ".join(f"{v:.3f}" for v in rgb)


class Canvas:
    def __init__(self):
        self.commands = []

    def rect(self, x, y, w, h, rgb):
        self.commands.append(f"{_color(rgb)} rg {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")

    def line(self, x1, y1, x2, y2, color=RULE, width=0.45):
        self.commands.append(f"{_color(color)} RG {width:.2f} w "
                             f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def txt(self, x, y, value, size=8, *, bold=False, color=TEXT):
        if value is None or value == "":
            return
        face = "F2" if bold else "F1"
        self.commands.append(f"{_color(color)} rg BT /{face} {size:.2f} Tf "
                             f"1 0 0 1 {x:.2f} {y:.2f} Tm ({_pdf_literal(value)}) Tj ET")

    def check(self, x, y):
        # Draw a true vector checkmark: no external fonts or symbol dependencies.
        self.commands.append(f"{_color(TEAL)} RG 1.5 w {x:.2f} {y+1:.2f} m "
                             f"{x+3:.2f} {y-2:.2f} l {x+8:.2f} {y+5:.2f} l S")

    def data(self):
        return ("\n".join(self.commands) + "\n").encode("latin1")


def _write_pdf(destination: Path, pages):
    """Minimal standards-compliant PDF 1.4 with an xref table; no pip modules."""
    objects = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    page_ids = []
    for page in pages:
        stream = page.data()
        contents_id = len(objects) + 1
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream")
        page_id = len(objects) + 1
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
                        f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                        f"/Contents {contents_id} 0 R >>").encode("ascii"))
        page_ids.append(page_id)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (f"<< /Type /Pages /Kids [" + " ".join(f"{pid} 0 R" for pid in page_ids)
                  + f"] /Count {len(page_ids)} >>").encode("ascii")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, data in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(data)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    # Only the final output path is touched; no change to health database.
    destination.write_bytes(out)


def _time(row) -> str:
    try:
        return datetime.fromisoformat(row["recorded_at"]).strftime("%H:%M")
    except (ValueError, TypeError):
        return "?"


def _report_value(value):
    """Leave missing/nonfinite values blank without concealing recorded zeroes."""
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value.lower() in ("none", "nan", "inf", "-inf") else value


def _entry_cells(day_rows):
    """Return same-date grid lines, preserving ALL readings, not just latest."""
    meds = [r for r in day_rows if r["kind"] == "medication"]
    insulin = [r for r in day_rows if r["kind"] == "insulin"]
    am = [r for r in day_rows if r["kind"] == "blood_pressure" and r["bp_session"] == "AM"]
    pm = [r for r in day_rows if r["kind"] == "blood_pressure" and r["bp_session"] == "PM"]
    glucose = [r for r in day_rows if r["kind"] == "blood_glucose"]
    n = max(1, len(meds), len(insulin), len(am), len(pm), len(glucose))
    result = []
    for i in range(n):
        cells = [None] * 12
        if i < len(meds):
            cells[1] = ("tick", _time(meds[i]))
        if i < len(insulin):
            cells[2] = ("tick", _time(insulin[i]))
        for j, rows in ((3, am), (7, pm)):
            if i < len(rows):
                bp = rows[i]
                cells[j:j+4] = [_report_value(bp["sys_mmHg"]), _report_value(bp["dia_mmHg"]),
                                _report_value(bp["pulse_bpm"]), _time(bp)]
        if i < len(glucose):
            value = _report_value(glucose[i]["glucose_mmol_l"])
            cells[11] = f'{value}  /  {_time(glucose[i])}' if value else None
        result.append(cells)
    return result



def _positive_measurement(value):
    """Parse a measurement; zero, missing, negative and invalid entries do not count."""
    if value is None:
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


def _column_averages(rows, *, legacy=False):
    """Mean of each recorded column, not a mean of daily means.

    Readings lacking an AM/PM label are reported separately from labelled ones.
    Return blank cells if a column has no nonzero measurement in the period.
    """
    keys = ("sys_mmHg", "dia_mmHg", "pulse_bpm")
    buckets = [[[] for _ in range(3)] for _ in range(2)]
    glucose = []
    for row in rows:
        if row["kind"] == "blood_pressure":
            session = row["bp_session"]
            if legacy:
                if session in ("AM", "PM"):
                    continue
                group = 0
            else:
                if session not in ("AM", "PM"):
                    continue
                group = 0 if session == "AM" else 1
            for key_idx, key in enumerate(keys):
                measurement = _positive_measurement(row[key])
                if measurement is not None:
                    buckets[group][key_idx].append(measurement)
        elif row["kind"] == "blood_glucose" and not legacy:
            measurement = _positive_measurement(row["glucose_mmol_l"])
            if measurement is not None:
                glucose.append(measurement)

    def mean(values):
        if not values:
            return None
        # Keep one decimal place for both BP/pulse and glucose, including .0.
        return str((sum(values) / len(values)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

    if legacy:
        return [mean(bucket) for bucket in buckets[0]]
    return ([mean(bucket) for bucket in buckets[0]],
            [mean(bucket) for bucket in buckets[1]], mean(glucose))


def _average_row(page, y_top, values, *, legacy=False):
    """A clearly distinguished last table row aligned with the measured columns."""
    widths = (150, 100, 100, 100, 100) if legacy else COLS
    height = 23
    page.rect(MARGIN, y_top-height, sum(widths), height, LIGHT)
    page.line(MARGIN, y_top, MARGIN+sum(widths), y_top, TEAL, 1.2)
    x = MARGIN
    for i, (width, value) in enumerate(zip(widths, values)):
        if value is not None:
            page.txt(x + 6, y_top-15, value, 8.9, bold=True, color=TEAL if i else NAVY)
        x += width
        page.line(x, y_top-height, x, y_top, RULE, .35)
    page.line(MARGIN, y_top-height, x, y_top-height, TEAL, .75)
    return y_top-height

def _header(page, start, end, generated, patient, number, legacy=False):
    page.rect(0, PAGE_H-9, PAGE_W, 9, TEAL)
    page.txt(MARGIN, 553, "MEDICAL DAILY CHECKLIST", 17, bold=True, color=NAVY)
    title = "EARLIER UNASSIGNED BLOOD PRESSURE" if legacy else "DAILY RECORD SUMMARY"
    page.txt(MARGIN, 531, title, 10, bold=True, color=TEAL)
    page.txt(MARGIN, 509, f"Reporting period: {start:%d %b %Y} - {end:%d %b %Y}", 10, bold=True)
    if patient:
        page.txt(400, 509, f"Patient: {patient}", 9)
    page.txt(MARGIN, 492, "Times are taken from the recorded entries. BP: mmHg; pulse: bpm; glucose: mmol/L.",
             8, color=GREY)
    page.line(MARGIN, 483, PAGE_W - MARGIN, 483, RULE, 0.8)


def _table_head(page):
    top = 472
    group_bottom = 447
    bottom = 421
    x = MARGIN
    group_specs = (("DATE", 0, 1), ("MEDICATION", 1, 2), ("INSULIN", 2, 3),
                   ("BLOOD PRESSURE - AM", 3, 7), ("BLOOD PRESSURE - PM", 7, 11),
                   ("BLOOD GLUCOSE", 11, 12))
    for text, a, b in group_specs:
        left = MARGIN + sum(COLS[:a]); width = sum(COLS[a:b])
        page.rect(left, group_bottom, width, top-group_bottom, NAVY if a not in (3,7) else TEAL)
        page.txt(left + 7, group_bottom + 9, text, 7.6 if b-a > 1 else 7.1,
                 bold=True, color=WHITE)
        page.line(left+width, group_bottom, left+width, top, WHITE, .5)
    page.rect(MARGIN, bottom, sum(COLS), group_bottom-bottom, LIGHT)
    subtitles = ("dd/mm/yyyy", "Taken @", "Injected @", "SYS", "DIA", "PULSE", "Time",
                 "SYS", "DIA", "PULSE", "Time", "mmol/L / time")
    x = MARGIN
    for i, (w, sub) in enumerate(zip(COLS, subtitles)):
        page.txt(x+5, bottom+9, sub, 7.2, bold=(i in (3,4,5,7,8,9)), color=NAVY)
        page.line(x, bottom, x, group_bottom, RULE)
        x += w
    page.line(x, bottom, x, group_bottom, RULE)
    page.line(MARGIN, bottom, PAGE_W-MARGIN, bottom, RULE, .8)
    return bottom


def _row(page, y_top, cells, index, continuation=False):
    h = 19
    page.rect(MARGIN, y_top-h, sum(COLS), h, WHITE if index % 2 else PALE)
    x = MARGIN
    for i, (w, entry) in enumerate(zip(COLS, cells)):
        if isinstance(entry, tuple) and entry[0] == "tick":
            page.check(x+8, y_top-11)
            page.txt(x+22, y_top-13, entry[1], 8, color=TEAL, bold=True)
        elif entry is not None:
            page.txt(x+5, y_top-13, entry, 7.7 if i in (0,11) else 8)
        x += w
        page.line(x, y_top-h, x, y_top, RULE, .35)
    page.line(MARGIN, y_top-h, PAGE_W-MARGIN, y_top-h, RULE, .36)
    return y_top-h


def _footer(page, generated, current, total):
    page.line(MARGIN, 45, PAGE_W-MARGIN, 45, RULE, .7)
    page.txt(MARGIN, 30, "Self-recorded log. Blank = no entry recorded (not proof a task was missed).",
             7.5, color=GREY)
    page.txt(MARGIN, 17, f"Generated {generated:%d/%m/%Y %H:%M %Z}", 7, color=GREY)
    page.txt(PAGE_W-88, 20, f"Page {current} of {total}", 8, bold=True, color=NAVY)


def _unassigned_table(page, start_y):
    widths = (150, 100, 100, 100, 100)
    page.rect(MARGIN, start_y-28, sum(widths), 28, NAVY)
    x = MARGIN
    for sub, w in zip(("Date", "SYS (mmHg)", "DIA (mmHg)", "Pulse (bpm)", "Time"), widths):
        page.txt(x+6, start_y-18, sub, 8.2, bold=True, color=WHITE)
        x += w
    return start_y - 28


def generate_report_pdf(destination, period, events, *, today=None, patient="", generated=None):
    """Create a dated, printable report without changing source entries.

    events: SQLite Rows or dictionaries with the existing events columns.
    Returns (start_date, end_date, number_of_pages).
    """
    start, end = period_dates(period, today)
    generated = generated or datetime.now().astimezone()
    if not isinstance(patient, str):
        patient = ""
    patient = " ".join(patient.split())[:65]
    by_day = defaultdict(list)
    legacy = []
    for row in events:
        day_string = row["local_day"]
        if start.isoformat() <= day_string <= end.isoformat():
            if row["kind"] == "blood_pressure" and row["bp_session"] not in ("AM", "PM"):
                legacy.append(row)
            else:
                by_day[day_string].append(row)
    for day_events in by_day.values():
        day_events.sort(key=lambda r: (r["recorded_at"], r["id"]))
    legacy.sort(key=lambda r: (r["local_day"], r["recorded_at"], r["id"]))
    all_labelled = [row for rows in by_day.values() for row in rows]
    am_means, pm_means, glucose_mean = _column_averages(all_labelled)
    legacy_means = _column_averages(legacy, legacy=True)

    pages = []
    page = None
    y = 0
    day_index = 0

    def new_page(legacy_page=False):
        nonlocal page, y
        page = Canvas()
        pages.append(page)
        _header(page, start, end, generated, patient, len(pages), legacy=legacy_page)
        y = _unassigned_table(page, 472) if legacy_page else _table_head(page)

    new_page()
    today_day = start
    while today_day <= end:
        values = _entry_cells(by_day.get(today_day.isoformat(), []))
        for k, row_values in enumerate(values):
            if y < 75:
                new_page()
            row_values[0] = today_day.strftime("%d/%m/%Y")
            y = _row(page, y, row_values, day_index)
        today_day += timedelta(days=1)
        day_index += 1

    # Place the summary at the foot of the final daily table (or on a new
    # page with a fresh table heading if the final page is nearly full).
    if y < 101:
        new_page()
    average_cells = (["AVERAGE", None, None, *am_means, None,
                      *pm_means, None, glucose_mean])
    y = _average_row(page, y, average_cells)
    page.txt(MARGIN + 4, y - 13,
             "Means of all recorded values above zero; blanks and zeros excluded. AM and PM are separate.",
             7.5, color=GREY)

    if legacy:
        new_page(legacy_page=True)
        for i, row in enumerate(legacy):
            if y < 75:
                new_page(legacy_page=True)
            row_data = [datetime.fromisoformat(row["local_day"]).strftime("%d/%m/%Y"),
                        _report_value(row["sys_mmHg"]), _report_value(row["dia_mmHg"]),
                        _report_value(row["pulse_bpm"]), _time(row)]
            y_top = y
            page.rect(MARGIN, y_top-20, 550, 20, WHITE if i%2 else PALE)
            pos = MARGIN
            for data, w in zip(row_data, (150,100,100,100,100)):
                page.txt(pos+6, y_top-14, data, 8.5)
                pos += w
                page.line(pos, y_top-20, pos, y_top, RULE)
            page.line(MARGIN, y_top-20, MARGIN+550, y_top-20, RULE)
            y -= 20
        if y < 101:
            new_page(legacy_page=True)
        # Unassigned historical readings cannot be assigned to AM or PM.
        y = _average_row(page, y, ["AVERAGE", *legacy_means, None], legacy=True)
        page.txt(MARGIN, y-13,
                 "Earlier entries lack AM/PM labels; averages exclude blanks and zero values.",
                 7.5, color=GREY)

    for n, sheet in enumerate(pages, 1):
        _footer(sheet, generated, n, len(pages))
    dest = Path(destination)
    _write_pdf(dest, pages)
    return start, end, len(pages)
