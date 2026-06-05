#!/usr/bin/env python3
"""Try conservative repairs for generated Fortran files that failed to compile.

The tool is intentionally post-failure only.  It reads an xp2f_batch results
file, finds cases with a generated .f90 file and a failed gfortran build, writes
a sibling *_fix.f90 candidate, and recompiles that candidate with the same build
command.  Original generated files are not modified unless --in-place is used.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompileFailCase:
    index: int
    source: str
    f90_path: Path
    build_cmd: str
    diagnostics: str


CASE_RE = re.compile(r"^\[(\d+)/\d+\]\s+(.+?\.py)\s*$", re.IGNORECASE)
WROTE_RE = re.compile(r"^\s*wrote\s+(.+?\.f90)\s*$", re.IGNORECASE)
BUILD_RE = re.compile(r"^\s*Build:\s+(.+)$", re.IGNORECASE)
BUILD_FAIL_RE = re.compile(r"^\s*Build:\s*FAIL\b", re.IGNORECASE)
PROC_START_RE = re.compile(
    r"^\s*(?:(?:pure|elemental|impure|recursive|module)\s+)*"
    r"(?:function|subroutine)\b",
    re.IGNORECASE,
)
PROC_END_RE = re.compile(r"^\s*end\s+(?:function|subroutine)\b", re.IGNORECASE)
SUBROUTINE_START_RE = re.compile(r"^\s*subroutine\s+([A-Za-z]\w*)\s*\((.*)\)", re.IGNORECASE)
COMMENT_TYPE_RE = re.compile(
    r"^\s*!\s*(?:integer|int|real|float|logical|bool|complex|character|string|str)"
    r"\s+(.+)$",
    re.IGNORECASE,
)
DECL_RE = re.compile(r"^(\s*)(.+?\bintent\s*\([^)]*\).*?)::\s*(.+?)\s*$", re.IGNORECASE)
DECL_ANY_RE = re.compile(r"^\s*.+?::\s*(.+?)\s*$", re.IGNORECASE)


def split_entities(text: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            item = "".join(cur).strip()
            if item:
                parts.append(item)
            cur = []
            continue
        cur.append(ch)
    item = "".join(cur).strip()
    if item:
        parts.append(item)
    return parts


def parse_results(path: Path) -> list[CompileFailCase]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    cases: list[CompileFailCase] = []
    cur_index = 0
    cur_source = ""
    cur_f90: Path | None = None
    cur_build = ""
    cur_block: list[str] = []

    def finish() -> None:
        nonlocal cur_index, cur_source, cur_f90, cur_build, cur_block
        if cur_f90 is not None and cur_build and any(BUILD_FAIL_RE.match(x) for x in cur_block):
            cases.append(
                CompileFailCase(
                    index=cur_index,
                    source=cur_source,
                    f90_path=cur_f90,
                    build_cmd=cur_build,
                    diagnostics="\n".join(cur_block),
                )
            )

    for line in lines:
        cm = CASE_RE.match(line)
        if cm:
            finish()
            cur_index = int(cm.group(1))
            cur_source = cm.group(2)
            cur_f90 = None
            cur_build = ""
            cur_block = [line]
            continue
        if not cur_source:
            continue
        cur_block.append(line)
        wm = WROTE_RE.match(line)
        if wm:
            cur_f90 = Path(wm.group(1).strip())
            continue
        bm = BUILD_RE.match(line)
        if bm and not bm.group(1).upper().startswith(("FAIL", "PASS")):
            cur_build = bm.group(1).strip()
    finish()
    return cases


def comment_rank_hints(block: list[str]) -> dict[str, int]:
    hints: dict[str, int] = {}
    for line in block:
        m = COMMENT_TYPE_RE.match(line)
        if not m:
            continue
        spec = m.group(1).split(":", 1)[0]
        for name, dims in re.findall(r"\b([A-Za-z]\w*)\s*[\(\[]\s*([^\)\]]*)\s*[\)\]]", spec):
            rank = len([part for part in (x.strip() for x in dims.split(",")) if part])
            if rank > 0:
                lname = name.lower()
                hints[lname] = max(hints.get(lname, 0), rank)
    return hints


def set_entity_rank(entity: str, rank: int) -> tuple[str, str | None]:
    m = re.match(r"^\s*([A-Za-z]\w*)\s*(?:\([^)]*\))?\s*$", entity)
    if not m:
        return entity, None
    name = m.group(1)
    dims = ",".join(":" for _ in range(rank))
    return f"{name}({dims})", name.lower()


def rank1_decl_types(block: list[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    for line in block:
        raw = line.rstrip("\r\n")
        m = DECL_ANY_RE.match(raw)
        if not m:
            continue
        lhs = raw.split("::", 1)[0].lower()
        if "real" in lhs:
            typ = "real"
        elif "integer" in lhs:
            typ = "int"
        elif "logical" in lhs:
            typ = "logical"
        else:
            continue
        for ent in split_entities(m.group(1)):
            em = re.match(r"^\s*([A-Za-z]\w*)\s*\(:\)\s*$", ent, re.IGNORECASE)
            if em:
                names[em.group(1).lower()] = typ
    return names


def strip_stale_second_dimension(line: str, rank1_names: set[str]) -> str:
    for name in sorted(rank1_names, key=len, reverse=True):
        # Generated code often leaves stale row sections after a rank repair:
        # ccc(j + 1, :) -> ccc(j + 1), acc(k + 1, :) -> acc(k + 1).
        pat = re.compile(
            rf"\b{re.escape(name)}\s*\(\s*([^,\n]+?)\s*,\s*:\s*\)",
            re.IGNORECASE,
        )
        line = pat.sub(lambda m: f"{m.group(0).split('(', 1)[0]}({m.group(1).strip()})", line)
    return line


def rewrite_rank1_loadtxt_assignment(line: str, rank1_types: dict[str, str]) -> tuple[str, str | None]:
    m = re.match(
        r"^(\s*)([A-Za-z]\w*)\s*=\s*loadtxt_(?:real|int|logical)_2d\s*\((.*)\)\s*$",
        line.rstrip("\r\n"),
        re.IGNORECASE,
    )
    if not m:
        return line, None
    name = m.group(2).lower()
    typ = rank1_types.get(name)
    if typ not in {"real", "int", "logical"}:
        return line, None
    args = m.group(3).strip()
    if "usecols" in args.lower():
        return line, None
    eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
    helper = f"loadtxt_{typ}_1d"
    return f"{m.group(1)}{m.group(2)} = {helper}({args}, 0){eol}", helper


def strip_redundant_rank1_reshape(line: str, rank1_names: set[str]) -> str:
    for name in sorted(rank1_names, key=len, reverse=True):
        pat = re.compile(
            rf"\breshape\s*\(\s*{re.escape(name)}\s*,\s*\[\s*size\s*\(\s*{re.escape(name)}\s*\)\s*,\s*1\s*\]\s*\)",
            re.IGNORECASE,
        )
        line = pat.sub(name, line)
    return line


def wrap_rank1_savetxt_real_2d(line: str, rank1_names: set[str]) -> str:
    for name in sorted(rank1_names, key=len, reverse=True):
        pat = re.compile(
            rf"\bsavetxt_real_2d\s*\(([^,\n]+),\s*{re.escape(name)}\s*\)",
            re.IGNORECASE,
        )
        line = pat.sub(lambda m: f"savetxt_real_2d({m.group(1).strip()}, reshape({name}, [size({name}), 1]))", line)
    return line


def add_python_mod_imports(lines: list[str], helpers: set[str]) -> list[str]:
    if not helpers:
        return lines
    existing = "\n".join(
        line for line in lines if re.match(r"^\s*use\s+python_mod\b", line, re.IGNORECASE)
    ).lower()
    missing = [h for h in sorted(helpers) if h.lower() not in existing]
    if not missing:
        return lines
    out: list[str] = []
    inserted = False
    for line in lines:
        out.append(line)
        if (not inserted) and re.match(r"^\s*use\s+python_mod\b", line, re.IGNORECASE):
            indent = re.match(r"^(\s*)", line).group(1)
            eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
            out.append(f"{indent}use python_mod, only: {', '.join(missing)}{eol}")
            inserted = True
    return out


def entity_rank(entity: str) -> tuple[str, int] | None:
    m = re.match(r"^\s*([A-Za-z]\w*)\s*(?:\(([^)]*)\))?\s*$", entity)
    if not m:
        return None
    name = m.group(1).lower()
    dims = m.group(2)
    if dims is None:
        return name, 0
    rank = dims.count(":")
    return name, rank


def collect_subroutine_signatures(lines: list[str]) -> dict[str, dict[int, int]]:
    signatures: dict[str, dict[int, int]] = {}
    block: list[str] = []
    in_proc = False
    for line in lines:
        if not in_proc and PROC_START_RE.match(line):
            in_proc = True
            block = [line]
            continue
        if not in_proc:
            continue
        block.append(line)
        if PROC_END_RE.match(line):
            sm = SUBROUTINE_START_RE.match(block[0].rstrip("\r\n"))
            if sm:
                proc = sm.group(1).lower()
                args = [a.strip().lower() for a in split_entities(sm.group(2))]
                ranks_by_name: dict[str, int] = {}
                for decl in block:
                    dm = DECL_ANY_RE.match(decl.rstrip("\r\n"))
                    if not dm:
                        continue
                    for ent in split_entities(dm.group(1)):
                        er = entity_rank(ent)
                        if er:
                            ranks_by_name[er[0]] = er[1]
                signatures[proc] = {
                    i: ranks_by_name[arg]
                    for i, arg in enumerate(args)
                    if arg in ranks_by_name and ranks_by_name[arg] > 0
                }
            block = []
            in_proc = False
    return signatures


def rewrite_decl_entities_to_rank1(line: str, names: set[str]) -> tuple[str, set[str]]:
    raw = line.rstrip("\r\n")
    m = DECL_ANY_RE.match(raw)
    if not m:
        return line, set()
    prefix = raw.split("::", 1)[0]
    entities = split_entities(m.group(1))
    changed: set[str] = set()
    new_entities: list[str] = []
    for ent in entities:
        em = re.match(r"^\s*([A-Za-z]\w*)\s*\(:\s*,\s*:\)\s*$", ent, re.IGNORECASE)
        if em and em.group(1).lower() in names:
            new_entities.append(f"{em.group(1)}(:)")
            changed.add(em.group(1).lower())
        else:
            new_entities.append(ent)
    if not changed:
        return line, set()
    eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
    return f"{prefix} :: {', '.join(new_entities)}{eol}", changed


def call_actuals_from_line(line: str) -> tuple[str, list[str]] | None:
    m = re.search(r"\bcall\s+([A-Za-z]\w*)\s*\((.*)", line, re.IGNORECASE)
    if not m:
        return None
    proc = m.group(1).lower()
    text = m.group(2).split("&", 1)[0]
    # This handles the common generated case where the relevant actuals are on
    # the first physical line.  Ambiguous continuation-heavy calls are skipped.
    if ")" not in text:
        return None
    text = text.rsplit(")", 1)[0]
    return proc, split_entities(text)


def repair_rank1_call_actuals(
    lines: list[str],
    changes: list[str],
    helpers_needed: set[str],
) -> list[str]:
    signatures = collect_subroutine_signatures(lines)
    if not signatures:
        return lines

    def apply_block(block: list[str]) -> list[str]:
        force_rank1: set[str] = set()
        for line in block:
            parsed = call_actuals_from_line(line)
            if not parsed:
                continue
            proc, actuals = parsed
            sig = signatures.get(proc)
            if not sig:
                continue
            for idx, rank in sig.items():
                if rank != 1 or idx >= len(actuals):
                    continue
                actual = actuals[idx].strip()
                if re.match(r"^[A-Za-z]\w*$", actual):
                    force_rank1.add(actual.lower())
        if not force_rank1:
            return block

        first_pass: list[str] = []
        changed_names: set[str] = set()
        for line in block:
            newline, changed = rewrite_decl_entities_to_rank1(line, force_rank1)
            first_pass.append(newline)
            changed_names.update(changed)
        if not changed_names:
            return block

        rank1_types = rank1_decl_types(first_pass)
        rank1 = set(rank1_types)
        second_pass: list[str] = []
        for line in first_pass:
            line = strip_stale_second_dimension(line, rank1)
            line = strip_redundant_rank1_reshape(line, rank1)
            line = wrap_rank1_savetxt_real_2d(line, rank1)
            line, helper = rewrite_rank1_loadtxt_assignment(line, rank1_types)
            if helper:
                helpers_needed.add(helper)
                changes.append(f"rank1 loadtxt assignment uses {helper}")
            second_pass.append(line)
        for name in sorted(changed_names):
            changes.append(f"call-actual adjusted local {name} to rank1")
        return second_pass

    out: list[str] = []
    block: list[str] = []
    in_proc = False
    for line in lines:
        if not in_proc and PROC_START_RE.match(line):
            in_proc = True
            block = [line]
            continue
        if not in_proc:
            out.append(line)
            continue
        block.append(line)
        if PROC_END_RE.match(line):
            out.extend(apply_block(block))
            block = []
            in_proc = False
    if block:
        out.extend(apply_block(block))
    return out


def repair_comment_dummy_ranks(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    changes: list[str] = []
    helpers_needed: set[str] = set()

    def apply_block(block: list[str]) -> list[str]:
        hints = comment_rank_hints(block)
        if not hints:
            return block
        changed_names: set[str] = set()
        first_pass: list[str] = []
        for line in block:
            raw = line.rstrip("\r\n")
            eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
            m = DECL_RE.match(raw)
            if not m:
                first_pass.append(line)
                continue
            entities = split_entities(m.group(3))
            new_entities: list[str] = []
            for ent in entities:
                nm = re.match(r"^\s*([A-Za-z]\w*)", ent)
                lname = nm.group(1).lower() if nm else ""
                if lname in hints:
                    new_ent, changed = set_entity_rank(ent, hints[lname])
                    new_entities.append(new_ent)
                    if changed:
                        changed_names.add(changed)
                    continue
                new_entities.append(ent)
            if new_entities != entities:
                first_pass.append(f"{m.group(1)}{m.group(2).rstrip()} :: {', '.join(new_entities)}{eol}")
            else:
                first_pass.append(line)

        rank1_types = rank1_decl_types(first_pass)
        rank1 = set(rank1_types)
        second_pass = []
        for line in first_pass:
            line = strip_stale_second_dimension(line, rank1)
            line = strip_redundant_rank1_reshape(line, rank1)
            line = wrap_rank1_savetxt_real_2d(line, rank1)
            line, helper = rewrite_rank1_loadtxt_assignment(line, rank1_types)
            if helper:
                helpers_needed.add(helper)
                changes.append(f"rank1 loadtxt assignment uses {helper}")
            second_pass.append(line)
        for name in sorted(changed_names):
            changes.append(f"comment-rank adjusted dummy {name}")
        return second_pass

    block: list[str] = []
    in_proc = False
    for line in lines:
        if not in_proc and PROC_START_RE.match(line):
            in_proc = True
            block = [line]
            continue
        if not in_proc:
            out.append(line)
            continue
        block.append(line)
        if PROC_END_RE.match(line):
            out.extend(apply_block(block))
            block = []
            in_proc = False
    if block:
        out.extend(apply_block(block))
    out = repair_rank1_call_actuals(out, changes, helpers_needed)
    out = add_python_mod_imports(out, helpers_needed)
    return "".join(out), changes


def fixed_path_for(path: Path) -> Path:
    return path.with_name(path.stem + "_fix" + path.suffix)


def fixed_build_command(build_cmd: str, original: Path, fixed: Path) -> str:
    cmd = build_cmd.replace(str(original), str(fixed))
    cmd = cmd.replace(str(original.with_suffix(".exe")), str(fixed.with_suffix(".exe")))
    # If the build command used -o but did not derive from the .f90 name, make a
    # best-effort replacement to avoid clobbering the original executable.
    return cmd


def compile_fixed(build_cmd: str, original: Path, fixed: Path) -> tuple[bool, str]:
    cmd = fixed_build_command(build_cmd, original, fixed)
    cp = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    text = "\n".join(x for x in [cmd, cp.stdout, cp.stderr] if x)
    return cp.returncode == 0, text


def process_case(case: CompileFailCase, write: bool, compile_candidate: bool) -> tuple[str, bool]:
    if not case.f90_path.exists():
        return "missing_f90", False
    original = case.f90_path.read_text(encoding="utf-8", errors="ignore")
    repaired, changes = repair_comment_dummy_ranks(original)
    if repaired == original:
        return "no_change", False
    out_path = case.f90_path if write else fixed_path_for(case.f90_path)
    out_path.write_text(repaired, encoding="utf-8")
    change_text = "; ".join(dict.fromkeys(changes))
    if not compile_candidate:
        return f"wrote {out_path} ({change_text})", True
    ok, build_text = compile_fixed(case.build_cmd, case.f90_path, out_path)
    if ok:
        return f"compile_pass {out_path} ({change_text})", True
    tail = "\n".join(build_text.splitlines()[-8:])
    return f"compile_fail {out_path} ({change_text})\n{tail}", True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("results_file", type=Path)
    ap.add_argument("--limit", type=int, default=0, help="maximum compile-fail cases to try")
    ap.add_argument("--in-place", action="store_true", help="modify generated .f90 files in place")
    ap.add_argument("--no-compile", action="store_true", help="only write candidate fixed files")
    args = ap.parse_args()

    cases = parse_results(args.results_file)
    if args.limit > 0:
        cases = cases[: args.limit]

    tried = changed = compile_pass = 0
    print(f"compile_fail_cases={len(cases)}")
    for case in cases:
        tried += 1
        status, did_change = process_case(
            case,
            write=args.in_place,
            compile_candidate=not args.no_compile,
        )
        if did_change:
            changed += 1
        if status.startswith("compile_pass"):
            compile_pass += 1
        print(f"[{case.index}] {case.source}")
        print(f"  {status}")
    print(f"summary: tried={tried} changed={changed} compile_pass={compile_pass}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
