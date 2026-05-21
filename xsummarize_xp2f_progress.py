#!/usr/bin/env python3
"""Summarize xp2f Burkardt batch result progress files."""

from __future__ import annotations

import argparse
import glob
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


OUTCOME_RE = re.compile(
    r"Outcomes:\s+"
    r"full_pass=(?P<full_pass>\d+)\s+"
    r"transpile_fail=(?P<transpile_fail>\d+)\s+"
    r"compile_fail=(?P<compile_fail>\d+)\s+"
    r"run_fail=(?P<run_fail>\d+)\s+"
    r"other_fail=(?P<other_fail>\d+)"
)

STAMP_RE = re.compile(r"burkardt_python_results_(?P<date>\d{8,9})_(?P<time>\d{1,4})(?P<ampm>am|pm)\.txt$", re.I)


def parse_datetime_from_name(path: Path) -> datetime | None:
    """Parse timestamps like 20260430_6pm, 20260429_0330pm, 20260506_0944am."""
    match = STAMP_RE.search(path.name)
    if not match:
        return None

    date_text = match.group("date")
    # Be tolerant of the observed typo 202060502_10am -> 20260502_10am.
    if len(date_text) == 9 and date_text.startswith("20206"):
        date_text = "2026" + date_text[5:]
    if len(date_text) != 8:
        return None

    time_text = match.group("time")
    ampm = match.group("ampm").lower()
    if len(time_text) <= 2:
        hour = int(time_text)
        minute = 0
    else:
        hour = int(time_text[:-2])
        minute = int(time_text[-2:])

    if not (1 <= hour <= 12 and 0 <= minute <= 59):
        return None
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    try:
        return datetime.strptime(date_text, "%Y%m%d").replace(hour=hour, minute=minute)
    except ValueError:
        return None


def read_outcomes(path: Path) -> dict[str, int] | None:
    for line in path.read_text(errors="replace").splitlines():
        match = OUTCOME_RE.search(line)
        if match:
            return {key: int(value) for key, value in match.groupdict().items()}
    return None


def build_dataframe(pattern: str, include_undated: bool = False) -> pd.DataFrame:
    rows = []
    for name in glob.glob(pattern):
        path = Path(name)
        outcomes = read_outcomes(path)
        if outcomes is None:
            continue
        dt = parse_datetime_from_name(path)
        if dt is None and not include_undated:
            continue
        entries = sum(outcomes.values())
        rows.append(
            {
                "datetime": pd.NaT if dt is None else pd.Timestamp(dt),
                "file": path.name,
                "entries": entries,
                **outcomes,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values(["datetime", "file"], na_position="last").reset_index(drop=True)
    df["full_pass_delta"] = df["full_pass"].diff().fillna(0).astype(int)
    df["transpile_fail_delta"] = df["transpile_fail"].diff().fillna(0).astype(int)
    df["compile_fail_delta"] = df["compile_fail"].diff().fillna(0).astype(int)
    df["run_fail_delta"] = df["run_fail"].diff().fillna(0).astype(int)
    df["other_fail_delta"] = df["other_fail"].diff().fillna(0).astype(int)
    df["full_pass_rate"] = (df["full_pass"] / df["entries"]).round(4)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pattern",
        nargs="?",
        default="burkardt_python_results*.txt",
        help="glob pattern for result files",
    )
    parser.add_argument("--csv", help="optional CSV output path")
    parser.add_argument("--include-undated", action="store_true", help="include files without a parseable timestamp")
    parser.add_argument("--tail", type=int, default=0, help="print only the last N rows")
    args = parser.parse_args()

    df = build_dataframe(args.pattern, include_undated=args.include_undated)
    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"wrote {args.csv}")

    shown = df.tail(args.tail) if args.tail and not df.empty else df
    if shown.empty:
        print("No result files with Outcomes lines found.")
    else:
        print(shown.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
