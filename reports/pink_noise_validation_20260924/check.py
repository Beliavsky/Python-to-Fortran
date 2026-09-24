"""Recheck the unchanged Burkardt program with recorded Python RNG draws."""
import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys


def compare_log(text, out):
    assert "Build: PASS" in text and "Run: PASS" in text, text[-2000:]
    py = text.split("Run (python): PASS\n", 1)[1].split("\nwrote ", 1)[0]
    ft = text.split("Run: PASS\n", 1)[1].split("\nRun diff:", 1)[0]
    (out / "python.stdout").write_text(py, encoding="utf-8")
    (out / "fortran.stdout").write_text(ft, encoding="utf-8")

    def tokens(output):
        lines = []
        for line in output.splitlines():
            if re.match(r"\s*(python|numpy) version:", line):
                continue
            if re.fullmatch(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) [A-Z][a-z]{2}\s+\d+ \d\d:\d\d:\d\d \d{4}", line.strip()):
                continue
            lines.extend(line.split())
        return lines

    py_tokens, ft_tokens = tokens(py), tokens(ft)
    assert len(py_tokens) == len(ft_tokens), (len(py_tokens), len(ft_tokens))
    for i, (p, f) in enumerate(zip(py_tokens, ft_tokens)):
        if p == f:
            continue
        atol = 1.e-10
        match = re.fullmatch(r"[-+]?\d+\.(\d+)(?:[Ee]([-+]?\d+))?", p)
        if match:
            atol = max(atol, 0.500001 * 10.0 ** (int(match[2] or 0) - len(match[1])))
        try:
            equal = math.isclose(float(p), float(f), rel_tol=1.e-6, abs_tol=atol)
        except ValueError:
            equal = False
        assert equal, (i, p, f)
    print(f"MATCH: {len(py_tokens)} tokens at Python displayed precision; timestamps/version banners excluded")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(
        "C:/python/public_domain/burkardt/pink_noise/pink_noise.py"))
    parser.add_argument("--check-log", action="store_true", help="recheck saved output without rebuilding")
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    if args.check_log:
        compare_log((out / "run.log").read_text(encoding="utf-8"), out)
        return 0
    root = out.parents[1]
    work = out / "work"
    work.mkdir(exist_ok=True)
    source = work / "pink_noise.py"
    shutil.copy2(args.source, source)
    proc = subprocess.run(
        [sys.executable, str(root / "xp2f.py"), str(source),
         "--compile", "--run-diff", "--rng-replay"],
        cwd=work, capture_output=True, text=True, timeout=300,
    )
    (out / "run.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    if proc.returncode:
        print(proc.stdout[-2000:])
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    compare_log(proc.stdout, out)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
