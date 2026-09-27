"""Compare the unchanged Burkardt driver, excluding time/version banners."""
import argparse
import difflib
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def normalized(text):
    lines = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line or "version:" in line.lower():
            continue
        if re.fullmatch(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \w{3} \d{1,2} \d\d:\d\d:\d\d \d{4}", line):
            continue
        lines.append(line)
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path(
        "C:/python/public_domain/burkardt/partition_greedy/partition_greedy.py"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = Path(tempfile.mkdtemp(prefix="xp2f_partition_greedy_validation_"))
    src = work / "partition_greedy.py"
    shutil.copy2(args.source, src)
    print("Artifacts:", work, flush=True)
    build = subprocess.run([sys.executable, str(root / "xp2f.py"), str(src), "--compile"],
                           cwd=work, capture_output=True, text=True, timeout=300)
    (work / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    assert build.returncode == 0 and "Build: PASS" in build.stdout, build.stdout + build.stderr
    outputs = []
    for name, command in [("python", [sys.executable, str(src)]),
                          ("fortran", [str(work / "partition_greedy_p.exe")])]:
        run = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=60)
        (work / (name + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        outputs.append(normalized(run.stdout))
    assert outputs[0] == outputs[1], "\n".join(difflib.unified_diff(*outputs, fromfile="python", tofile="fortran"))
    assert sum(line.startswith("Discrepancy =") for line in outputs[0]) == 6
    print("PASS: all six problems match, including partition assignments, sums, and discrepancies.")


if __name__ == "__main__":
    main()
