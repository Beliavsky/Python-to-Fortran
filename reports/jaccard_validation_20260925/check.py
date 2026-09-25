"""Build the unchanged Burkardt example and compare its five distances."""
import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path,
                        default=Path("C:/python/public_domain/burkardt/jaccard_distance/jaccard_distance.py"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    work = Path(tempfile.mkdtemp(prefix="xp2f_jaccard_check_"))
    source = work / "jaccard_distance.py"
    shutil.copy2(args.source, source)
    build = subprocess.run([sys.executable, str(root / "xp2f.py"), str(source), "--compile"],
                           cwd=work, capture_output=True, text=True, timeout=300)
    (work / "build.log").write_text(build.stdout + build.stderr, encoding="utf-8")
    assert build.returncode == 0 and "Build: PASS" in build.stdout, build.stdout + build.stderr
    outputs = []
    exe = source.with_name("jaccard_distance_p.exe")
    for label, command in [("python", [sys.executable, str(source)]), ("fortran", [str(exe)])]:
        run = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=60)
        (work / (label + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
        assert run.returncode == 0, run.stdout + run.stderr
        outputs.append([float(v) for v in re.findall(r"Computed distance\s*=\s*(\S+)", run.stdout)])
    assert len(outputs[0]) == len(outputs[1]) == 5, outputs
    assert all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
               for a, b in zip(*outputs)), outputs
    print("All five distances match:", outputs[1])
    print("Build and execution logs:", work)


if __name__ == "__main__":
    main()
