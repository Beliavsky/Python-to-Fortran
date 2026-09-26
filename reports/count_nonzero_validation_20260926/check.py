"""Compare Burkardt's unchanged chuckaluck_payoff for every dice/spot combination."""
import argparse
import ast
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=Path(
        "C:/python/public_domain/burkardt/chuckaluck_simulation/chuckaluck_simulation.py"))
    parser.add_argument("--ignore-comments", action="store_true",
                        help="bypass the separate dice[3] comment-rank inference problem")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    original = args.source.read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(original).body
              if isinstance(n, ast.FunctionDef) and n.name == "chuckaluck_payoff")
    work = Path(tempfile.mkdtemp(prefix="xp2f_count_nonzero_burkardt_"))
    src = work / "payoff.py"
    src.write_text("import numpy as np\n" + ast.get_source_segment(original, fn) + '''

for spot in range(1, 7):
    for a in range(1, 7):
        for b in range(1, 7):
            for c in range(1, 7):
                print(chuckaluck_payoff(spot, np.array([a, b, c], dtype=int)))
''', encoding="utf-8")
    command = [sys.executable, str(root / "xp2f.py"), str(src), "--compile"]
    if args.ignore_comments:
        command.append("--ignore-comments")
    build = subprocess.run(command,
                           cwd=work, capture_output=True, text=True, timeout=300)
    (work / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    assert build.returncode == 0 and "Build: PASS" in build.stdout, build.stdout + build.stderr
    outputs = []
    for name, command in [("python", [sys.executable, str(src)]),
                          ("fortran", [str(work / "payoff_p.exe")])]:
        run = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=60)
        (work / (name + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        outputs.append([int(v) for v in run.stdout.split()])
    assert len(outputs[0]) == 1296 and outputs[0] == outputs[1], outputs
    print("All 1296 chuckaluck payoffs match Python exactly.")
    print("Comment inference:", "disabled" if args.ignore_comments else "enabled")
    print("Sources, generated Fortran, and logs:", work)


if __name__ == "__main__":
    main()
