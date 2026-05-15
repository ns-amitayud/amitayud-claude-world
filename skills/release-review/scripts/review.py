#!/usr/bin/env python3
"""
release-review helper
Usage:
  review.py filter <csv_path>
      Print NSProxy ticket keys with any of columns 23-30 still empty.

  review.py write <csv_path> <key> <q1> <q2> <q3> <q4> <q5> <q6> <q7> <q8>
      Write answers for one ticket into the CSV (in place).

  review.py convert <csv_path>
      Convert CSV to XLSX saved as <stem>-reviewed.xlsx alongside the input.
"""
import sys
import csv
import re
from datetime import datetime

COMPONENT_COL = 10   # Components
KEY_COL = 1
STATUS_COL = 3       # Status
RESOLVED_COL = 8     # Resolved date
RESOLUTION_COL = 19  # Resolution
ANSWER_COLS = list(range(23, 31))   # cols 23-30 inclusive (Q1-Q8)

# Only process tickets that are done — exclude In Progress, Reopened, Open
VALID_STATUSES = {'closed', 'resolved', 'pending close'}
VALID_RESOLUTIONS = {'fixed', 'done'}

# Minimum resolved date — tickets resolved before this are from prior releases
# and should not be processed even if fix_versions includes this release.
# Override via --since=YYYY-MM-DD on the command line.
DEFAULT_MIN_RESOLVED = datetime(2026, 1, 1)


def load_csv(path):
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.reader(f))


def is_nsproxy_row(row):
    if len(row) <= COMPONENT_COL:
        return False
    # Matches "NS Proxy (NSP)", "nsproxy", "NSProxy", etc.
    return bool(re.search(r'ns.?proxy', row[COMPONENT_COL], re.IGNORECASE))


def needs_answers(row):
    """True if any of the 8 answer columns is blank."""
    for col in ANSWER_COLS:
        if len(row) <= col or not row[col].strip():
            return True
    return False


def is_release_ready(row, min_resolved=DEFAULT_MIN_RESOLVED):
    """True if ticket is done and resolved after min_resolved date."""
    status = row[STATUS_COL].strip().lower() if len(row) > STATUS_COL else ''
    resolution = row[RESOLUTION_COL].strip().lower() if len(row) > RESOLUTION_COL else ''
    if status not in VALID_STATUSES or resolution not in VALID_RESOLUTIONS:
        return False
    resolved_str = row[RESOLVED_COL].strip() if len(row) > RESOLVED_COL else ''
    if not resolved_str:
        return False
    try:
        resolved = datetime.strptime(resolved_str, '%m/%d/%Y %H:%M:%S')
        return resolved >= min_resolved
    except ValueError:
        return False


def cmd_filter(csv_path, min_resolved=DEFAULT_MIN_RESOLVED):
    rows = load_csv(csv_path)
    results = []
    for row in rows[1:]:   # skip header
        if is_nsproxy_row(row) and is_release_ready(row, min_resolved) and needs_answers(row):
            results.append(row[KEY_COL])
    print('\n'.join(results))


def cmd_write(csv_path, key, answers):
    """answers: list of 8 strings for cols 23-30."""
    rows = load_csv(csv_path)
    matched = False
    for row in rows[1:]:
        if row[KEY_COL] == key:
            # Pad row if shorter than col 30
            while len(row) <= 30:
                row.append('')
            for i, ans in enumerate(answers):
                row[ANSWER_COLS[i]] = ans
            matched = True
            break
    if not matched:
        print(f"ERROR: key {key} not found in {csv_path}", file=sys.stderr)
        sys.exit(1)
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"OK: wrote answers for {key}")


def cmd_convert(csv_path):
    import pandas as pd
    from pathlib import Path
    df = pd.read_csv(csv_path, dtype=str).fillna('')
    out_path = Path(csv_path).with_stem(Path(csv_path).stem + '-reviewed').with_suffix('.xlsx')
    df.to_excel(out_path, index=False, engine='openpyxl')
    print(f"Saved: {out_path}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    path = sys.argv[2]
    if cmd == 'filter':
        # Optional: --since=YYYY-MM-DD to override minimum resolved date
        min_resolved = DEFAULT_MIN_RESOLVED
        for arg in sys.argv[3:]:
            if arg.startswith('--since='):
                min_resolved = datetime.strptime(arg.split('=', 1)[1], '%Y-%m-%d')
        cmd_filter(path, min_resolved)
    elif cmd == 'write':
        # args: review.py write <csv> <key> <q1> .. <q8>
        if len(sys.argv) != 12:
            print("write requires: csv_path key q1 q2 q3 q4 q5 q6 q7 q8")
            sys.exit(1)
        cmd_write(path, sys.argv[3], sys.argv[4:12])
    elif cmd == 'convert':
        cmd_convert(path)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
