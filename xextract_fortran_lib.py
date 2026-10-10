#!/usr/bin/env python3
"""Extract the numerical library routines of python.f90 (the ones tagged
`!@pyapi ... lib=<topic>` on their public line) into a standalone Fortran
module, with everything they use, for a separate library repository.

    python xextract_fortran_lib.py [--src python.f90] [--out fortran_lib]
                                   [--module numpy_fortran] [--topics a,b]
                                   [--no-compile]

Writes, in the output directory:
  <module>.f90  the module: the tagged routines and generic interfaces
                (public), the procedures, interfaces, types, parameters and
                variables they need (private), and python.f90's intrinsic
                module uses;
  ROUTINES.md   the public routines by topic, from the tags' args= and desc=;
  report.txt    what was extracted, the external procedures needed at link
                time (LAPACK), and the tagged routines without a lib= topic.
Then compiles the module with gfortran -c (unless --no-compile), which
checks that nothing outside it (python_mod) is referenced.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC_START = re.compile(
    r"^\s*(?:(?:pure|elemental|recursive|impure|module)\s+)*"
    r"(?:(?:integer|real|logical|complex|character|type)\s*(?:\([^)]*\))?\s*(?:(?:pure|elemental|recursive)\s+)*)?"
    r"(function|subroutine)\s+([a-z_]\w*)", re.I)
PROC_END = re.compile(r"^\s*end\s*(function|subroutine)\b", re.I)
IFACE_START = re.compile(r"^\s*interface\s+([a-z_]\w*)\s*$", re.I)
IFACE_ANON = re.compile(r"^\s*(abstract\s+)?interface\s*$", re.I)
IFACE_END = re.compile(r"^\s*end\s*interface\b", re.I)
TYPE_START = re.compile(r"^\s*type\s*(?:,[^:]*)?(?:::)?\s*([a-z_]\w*)\s*$", re.I)
TYPE_END = re.compile(r"^\s*end\s*type\b", re.I)
WORD = re.compile(r"\b[a-z_]\w*\b", re.I)
TAG = re.compile(r"^public\s*::\s*([a-z_]\w*)\s*!@pyapi(.*)$", re.I)


def strip_comment(line: str) -> str:
    """The code of a line without its comment and string literals."""
    out, q = [], None
    for ch in line:
        if q:
            if ch == q:
                q = None
            continue
        if ch in "'\"":
            q = ch
            continue
        if ch == "!":
            break
        out.append(ch)
    return "".join(out)


def parse(src: str):
    lines = src.splitlines()
    head_end = next(i for i, l in enumerate(lines) if re.match(r"^contains\s*$", l.strip(), re.I))
    end_mod = max(i for i, l in enumerate(lines) if re.match(r"^\s*end\s+module\b", l, re.I))
    # Specification part: uses, parameters/variables, types, interfaces, publics.
    uses, decls, types, ifaces, tags = [], [], {}, {}, {}
    i = 0
    while i < head_end:
        l = lines[i]
        code = strip_comment(l).strip()
        m_t = TYPE_START.match(code)
        m_i = IFACE_START.match(code)
        if m_t and not re.match(r"^\s*type\s*\(", code, re.I):
            j = i
            while not TYPE_END.match(strip_comment(lines[j])):
                j += 1
            types[m_t.group(1).lower()] = lines[i:j + 1]
            i = j + 1
            continue
        if m_i:
            j = i
            while not IFACE_END.match(strip_comment(lines[j])):
                j += 1
            procs = []
            for k in range(i + 1, j):
                mp = re.match(r"^\s*module\s+procedure\s+(.*)$", strip_comment(lines[k]), re.I)
                if mp:
                    procs += [p.strip().lower() for p in mp.group(1).split(",") if p.strip()]
            ifaces[m_i.group(1).lower()] = (lines[i:j + 1], procs)
            i = j + 1
            continue
        mt = TAG.match(l.strip())
        if mt:
            tags[mt.group(1).lower()] = mt.group(2)
        if re.match(r"^\s*use\b", code, re.I):
            uses.append(l)
        elif "::" in code and not re.match(r"^\s*(public|private)\b", code, re.I):
            names = [n.split("=")[0].split("(")[0].strip().lower() for n in code.split("::", 1)[1].split(",")]
            decls.append((names, l))
        i += 1
    # Module procedures (an internal procedure stays in its host).
    procs, order = {}, []
    i = head_end + 1
    while i < end_mod:
        code = strip_comment(lines[i])
        m = PROC_START.match(code)
        if m and not re.match(r"^\s*end\b", code, re.I):
            name = m.group(2).lower()
            depth, j = 0, i
            while True:
                cj = strip_comment(lines[j])
                if PROC_START.match(cj) and not re.match(r"^\s*end\b", cj, re.I):
                    depth += 1
                elif PROC_END.match(cj):
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            procs[name] = lines[i:j + 1]
            order.append(name)
            i = j + 1
            continue
        i += 1
    return lines, uses, decls, types, ifaces, tags, procs, order


def tag_field(tag: str, key: str) -> str | None:
    m = re.search(rf'\b{key}=("([^"]*)"|\S+)', tag)
    if not m:
        return None
    return m.group(2) if m.group(2) is not None else m.group(1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=HERE / "python.f90")
    ap.add_argument("--out", type=Path, default=HERE / "fortran_lib")
    ap.add_argument("--module", default="numpy_fortran")
    ap.add_argument("--topics", default="", help="comma-separated lib= topics (default: all)")
    ap.add_argument("--no-compile", action="store_true")
    args = ap.parse_args()
    lines, uses, decls, types, ifaces, tags, procs, order = parse(args.src.read_text(encoding="utf-8"))
    topics = {t for t in args.topics.split(",") if t}
    lib = {n: t for n, t in tags.items() if tag_field(t, "lib") and (not topics or tag_field(t, "lib") in topics)}
    untopiced = sorted(n for n, t in tags.items() if not tag_field(t, "lib"))
    decl_names = {n: l for names, l in decls for n in names}
    # Closure over references.
    need_procs, need_ifaces, need_types, need_decls = set(), set(), set(), set()
    todo = list(lib)
    seen = set()
    while todo:
        n = todo.pop()
        if n in seen:
            continue
        seen.add(n)
        body = []
        if n in ifaces:
            need_ifaces.add(n)
            todo += ifaces[n][1]
            continue
        if n in procs:
            need_procs.add(n)
            body = procs[n]
        elif n in types:
            need_types.add(n)
            body = types[n]
        elif n in decl_names:
            need_decls.add(n)
            body = [decl_names[n]]
        else:
            continue
        for l in body:
            for w in WORD.findall(strip_comment(l)):
                w = w.lower()
                if w != n and w not in seen and (w in procs or w in ifaces or w in types or w in decl_names):
                    todo.append(w)
    missing = sorted(n for n in lib if n not in procs and n not in ifaces)
    # External procedures (LAPACK and the like) called but not defined here.
    defined = set(procs) | set(ifaces)
    externals = set()
    for n in need_procs:
        for l in procs[n]:
            m = re.match(r"^\s*call\s+([a-z_]\w*)", strip_comment(l), re.I)
            if m and m.group(1).lower() not in defined:
                externals.add(m.group(1).lower())
    args.out.mkdir(parents=True, exist_ok=True)
    o = [f"! {args.module}: numerical routines (numpy's algorithms) extracted from python.f90",
         "! of the Python-to-Fortran transpiler by xextract_fortran_lib.py. Do not edit:",
         "! regenerate from python.f90. See that project's README (Third-Party Code)",
         "! for the sources and licenses of code adapted from other projects.",
         f"module {args.module}"]
    o += uses + ["implicit none", "private"]
    o += [l for names, l in decls if set(names) & need_decls]
    for n in sorted(need_types):
        o += types[n]
    for n in sorted(lib):
        o.append(f"public :: {n}")
    for n in sorted(need_ifaces):
        o += ifaces[n][0]
    o.append("contains")
    for n in order:
        if n in need_procs:
            o.append("")
            o += procs[n]
    o.append(f"end module {args.module}")
    f90 = args.out / f"{args.module}.f90"
    f90.write_text("\n".join(o) + "\n", encoding="utf-8")
    # Routine list.
    by_topic = defaultdict(list)
    for n, t in lib.items():
        by_topic[tag_field(t, "lib")].append(n)
    md = [f"# {args.module}", "", f"{len(lib)} public routines, extracted from python.f90.", ""]
    for topic in sorted(by_topic):
        md += [f"## {topic}", "", "| routine | kind | arguments | description |", "|---|---|---|---|"]
        for n in sorted(by_topic[topic]):
            t = lib[n]
            md.append(f"| `{n}` | {tag_field(t, 'kind') or ''} | `{(tag_field(t, 'args') or '').replace('|', '/')}` "
                      f"| {tag_field(t, 'desc') or ''} |")
        md.append("")
    (args.out / "ROUTINES.md").write_text("\n".join(md), encoding="utf-8")
    rep = [f"public routines: {len(lib)}", f"procedures: {len(need_procs)}", f"generic interfaces: {len(need_ifaces)}",
           f"types: {len(need_types)}", f"module variables/parameters: {sorted(need_decls)}",
           f"external procedures (link LAPACK etc.): {sorted(externals)}",
           f"tagged names not found as procedures or interfaces: {missing}",
           f"tagged routines without a lib= topic ({len(untopiced)}): {', '.join(untopiced)}"]
    (args.out / "report.txt").write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("\n".join(rep[:7]))
    print(f"wrote {f90}, ROUTINES.md, report.txt in {args.out}")
    if args.no_compile:
        return 0
    p = subprocess.run(["gfortran", "-c", "-Wall", "-Wno-unused-dummy-argument", f90.name], cwd=args.out,
                       capture_output=True, text=True)
    errs = [l for l in (p.stdout + p.stderr).splitlines() if "Error" in l]
    print("compile:", "PASS" if p.returncode == 0 else "FAIL")
    if p.returncode != 0:
        print("\n".join((p.stdout + p.stderr).splitlines()[:30]))
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())
