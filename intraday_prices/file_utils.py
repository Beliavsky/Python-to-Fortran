# TRANSLATION NOTES: the original expand_file_patterns() expands
# command-line glob patterns (via `glob`/`pathlib.Path`, with a `set` for
# dedup) into a sorted list of existing file paths -- it exists only to
# serve argparse's "accept multiple files or wildcards" CLI convenience.
# None of that has a Fortran equivalent (no glob, no Path, no set/list-of-
# paths), and it's moot anyway: every translated script in this directory
# takes one hardcoded input filename instead of CLI glob patterns, so there
# is nothing left to expand. `os.path.isfile`/`pathlib.Path.exists` are
# also unsupported (no file-existence check in xp2f.py), so this is kept
# as a minimal, supported filename-suffix check instead, just so the file
# remains a genuine translation target rather than dead code.


def has_csv_suffix(filename):
    return filename[-4:] == ".csv"


def main():
    filename = "spy_5min_databento.csv"
    if has_csv_suffix(filename):
        print("csv file:", filename)
    else:
        print("not a csv file:", filename)


if __name__ == "__main__":
    main()
