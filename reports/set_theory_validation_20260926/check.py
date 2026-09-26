"""Build unchanged Burkardt set_theory and compare order-independent results."""
import argparse
import ast
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def results(output):
    rows = []
    membership = []
    for line in output.splitlines():
        line = line.strip()
        if "member of A." in line or "proper subset of A." in line:
            membership.append(" ".join(line.split()))
        if line.startswith("{"):
            line = re.sub(r"np\.int\d+\((-?\d+)\)", r"\1", line)
            rows.append(sorted(ast.literal_eval(line)))
        elif re.fullmatch(r"[-\d\s]+", line):
            rows.append(sorted(int(v) for v in line.split()))
    # pop() can choose any remaining member; compare all five as a set,
    # retaining the count/uniqueness check to catch repeated returns.
    popped = [row[0] for row in rows[-5:] if len(row) == 1]
    return rows[:-5], membership, popped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path(
        "C:/python/public_domain/burkardt/set_theory/set_theory.py"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = Path(tempfile.mkdtemp(prefix="xp2f_set_theory_validation_"))
    src = work / "set_theory.py"
    shutil.copy2(args.source, src)
    print("Artifacts:", work, flush=True)
    build = subprocess.run([sys.executable, str(root / "xp2f.py"), str(src), "--compile"],
                           cwd=work, capture_output=True, text=True, timeout=300)
    (work / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    assert build.returncode == 0 and "Build: PASS" in build.stdout, build.stdout + build.stderr
    outputs = []
    for name, command in [("python", [sys.executable, str(src)]),
                          ("fortran", [str(work / "set_theory_p.exe")])]:
        run = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=60)
        (work / (name + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        outputs.append(results(run.stdout))
    assert outputs[0][:2] == outputs[1][:2], outputs
    assert len(outputs[0][0]) == 14, outputs
    assert len(outputs[0][1]) == 12, outputs
    print("PASS: 13 sets, cardinality, 11 membership tests, and proper subset.")
    expected = {1, 6, 11, 31, 41}
    assert len(outputs[0][2]) == 5 and set(outputs[0][2]) == expected, outputs[0][2]
    popped = outputs[1][2]
    if len(popped) == 5 and set(popped) == expected:
        print("PASS: five distinct valid pops.")
    else:
        raise AssertionError(f"Incorrect Fortran pop results: {popped}")


if __name__ == "__main__":
    main()
