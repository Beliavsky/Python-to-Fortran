# TRANSLATION NOTES: heavily simplified. The original's job is entirely
# file/CLI plumbing (argparse, glob-pattern input resolution via
# file_utils, output-path derivation from pathlib.Path.stem) wrapped
# around timezone-aware datetime handling (`.dt.tz_localize(...,
# ambiguous=, nonexistent=)`, `.dt.strftime`, a regex to reformat the UTC
# offset from "-0500" to "-05:00") and writing a *fresh* DataFrame built
# column-by-column from `pd.DataFrame()` via `.to_csv(...)`. None of
# tz_localize/strftime/regex, or building/writing a new DataFrame from
# scratch, are in xp2f.py's supported subset (only reading a DataFrame via
# pd.read_csv is supported; the datetime type here is naive local time
# with no timezone concept at all -- see dataframe_index_datetime.f90's
# own notes). What's kept is the one piece of genuinely portable logic:
# joining a separate Date string and Time string into one Databento-style
# "yyyy-mm-dd hh:mm:ss" timestamp string (no timezone offset, since none
# is supported).


def combine_date_time(date_str, time_str):
    """Join "YYYY-MM-DD" and "HH:MM" into "YYYY-MM-DD HH:MM:00"."""
    return date_str + " " + time_str + ":00"


def main():
    dates = ["2023-03-28", "2023-03-28", "2023-03-29"]
    times = ["09:30", "09:35", "09:30"]
    n = len(dates)
    for i in range(n):
        print(combine_date_time(dates[i], times[i]))


if __name__ == "__main__":
    main()
