"""Compile the original Hamming program and compare its timestamp-free tests."""
import ast
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "C:/python/public_domain/burkardt/hamming/hamming.py")


def canonical(text):
    result = []
    for line in text.splitlines():
        if not line.strip() or "version:" in line:
            continue
        tokens = re.findall(r"\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?|[A-Za-z_]+|[^\s\[\]]", line)
        result.append(tuple(format(Decimal(t).normalize(), "f") if t[0].isdigit() else t
                            for t in tokens))
    return result


def run(source, name, compare=False):
    command = [sys.executable, str(ROOT / "xp2f.py"), str(source), "--compile",
               "--out", str(OUT / (name + "_p.f90"))]
    if compare:
        command.append("--run-diff")
    proc = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=240)
    (OUT / (name + ".log")).write_text(proc.stdout + proc.stderr, encoding="utf-8")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Build: PASS" in proc.stdout, proc.stdout + proc.stderr
    assert proc.stderr.count("nested loop reuses active loop variable 'i'") == 1, proc.stderr
    if compare:
        py = proc.stdout.split("Run (python): PASS\n", 1)[1].split("\nwrote ", 1)[0]
        ft = proc.stdout.split("\nRun: PASS\n", 1)[1].split("\nRun diff:", 1)[0]
        assert canonical(py) == canonical(ft), proc.stdout + proc.stderr
        return "NORMALIZED MATCH (version banners, whitespace, array brackets excluded)"
    return "COMPILE PASS"


source = SOURCE.read_text(encoding="utf-8")
functions = [ast.get_source_segment(source, node) for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef)]
probe = OUT / "corpus_probe.py"
probe.write_text("\n\n".join(functions) + "\nhamming_test()\n", encoding="utf-8")
results = {"original": run(SOURCE, "full"),
           "original_tests": run(probe, "corpus_probe", compare=True)}
(OUT / "analysis.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
