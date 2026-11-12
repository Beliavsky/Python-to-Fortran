"""Build focused FORD documentation for runtime or standalone numerical helpers."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", action="store_true",
                        help="regenerate and document numpy_fortran instead of python_mod")
    parser.add_argument("--output", type=Path,
                        help="HTML directory (default: docs/generated/runtime or library)")
    args = parser.parse_args()
    kind = "library" if args.library else "runtime"
    output = (args.output or ROOT / "docs" / "generated" / kind).resolve()
    if args.library:
        result = subprocess.run([sys.executable, str(ROOT / "xextract_fortran_lib.py"),
                                 "--no-compile"], cwd=ROOT)
        if result.returncode:
            return result.returncode
    source = ROOT / "fortran_lib" / "numpy_fortran.f90" if args.library else ROOT / "python.f90"
    # Never scan the repository recursively: it contains many unrelated modules,
    # examples and generated translations, sometimes with duplicate names.
    with tempfile.TemporaryDirectory(prefix="p2f_ford_") as work:
        shutil.copy2(source, Path(work) / source.name)
        return subprocess.run([sys.executable, "-m", "ford",
                               str(ROOT / "docs" / "ford" / f"{kind}.md"),
                               "--src_dir", work, "--output_dir", str(output)], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
