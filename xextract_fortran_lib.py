#!/usr/bin/env python3
"""Extract the numerical library routines of python.f90 (the ones tagged
`!@pyapi ... lib=<topic>` on their public line) into a standalone Fortran
module, with everything they use, for a separate library repository.

    python xextract_fortran_lib.py [--src python.f90] [--out fortran_lib]
                                   [--module numpy_fortran] [--topics a,b]
                                   [--no-compile]
    python xextract_fortran_lib.py --apply-topics topics.tsv [--src python.f90]
    python xextract_fortran_lib.py --fill-tags [--src python.f90]

--apply-topics edits python.f90's tags from a table (routine<TAB>topic,
'#' comment lines and a "routine" header skipped): the topic becomes the
tag's lib= (replacing one there); 'exclude' and 'internal' remove it. A
public name without a tag gets a public line of its own with a minimal
tag (!@pyapi lib=<topic>).

--fill-tags completes the tags that have lib= but no kind=/args=: kind=,
ret= (a function's result), args= (each dummy argument's type, rank,
intent and optional) from the procedure's declarations, and desc= from
the comment that follows its header (for a generic interface, those of
its first specific procedure, and the list of specifics).

Writes, in the output directory:
  <module>.f90  the module: the tagged routines and generic interfaces
                (public, grouped by topic on compact declaration lines),
                the procedures, interfaces, types, parameters and
                variables they need (private), and python.f90's intrinsic
                module uses;
  ROUTINES.md   the public routines by topic, from the tags' args= and desc=;
  report.txt    what was extracted, the external procedures needed at link
                time (LAPACK), and the tagged routines without a lib= topic.
Then compiles the module with gfortran -c (unless --no-compile), which
checks that nothing outside it (python_mod) is referenced.
Eligible scalar pure procedures are promoted to pure elemental in the
extracted module; procedures used as callbacks inside it are preserved.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import textwrap
from collections import defaultdict
from pathlib import Path

import fortran_purity

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
INTRINSIC_SUBROUTINES = {"move_alloc", "random_number", "random_seed", "get_environment_variable", "cpu_time",
                         "system_clock", "date_and_time", "execute_command_line", "get_command_argument",
                         "get_command", "mvbits"}
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
            # The body with continuation lines joined.
            body = " ".join(strip_comment(lines[k]).strip() for k in range(i + 1, j))
            body = re.sub(r"&\s*&?", " ", body)
            for mp in re.finditer(r"module\s+procedure\s+([\w\s,]+?)(?=module\s+procedure|$)", body, re.I):
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


def add_ford_api_summaries(src: str) -> str:
    """Seed missing FORD summaries from API metadata, keeping authored docs.

    Generic descriptions also document their specifics. Comments follow the
    complete (possibly continued) declaration so extraction preserves them.
    This does not infer argument semantics or convert implementation comments.
    """
    lines, _, _, types, ifaces, tags, procs, _ = parse(src)
    descriptions = {}
    for name, tag in tags.items():
        desc = tag_field(tag, "desc")
        if desc:
            descriptions[name] = desc
    for name, (_, specifics) in ifaces.items():
        if name in descriptions:
            for specific in specifics:
                descriptions.setdefault(specific, descriptions[name])
    starts = {body[0]: (name, body) for name, body in procs.items()}
    starts.update({body[0]: (name, body) for name, (body, _) in ifaces.items()})
    starts.update({body[0]: (name, body) for name, body in types.items()})
    insertions = {}
    for i, line in enumerate(lines):
        if line not in starts:
            continue
        name, body = starts[line]
        if name not in descriptions:
            continue
        end = i
        while strip_comment(lines[end]).rstrip().endswith("&"):
            end += 1
        # Respect both inline/following !! and preceding !> documentation.
        following = []
        for item in lines[end + 1:]:
            if item.strip() and not item.lstrip().startswith("!"):
                break
            following.append(item)
        preceding = []
        for item in reversed(lines[:i]):
            if item.strip() and not item.lstrip().startswith("!"):
                break
            preceding.append(item)
        if (any("!!" in item for item in lines[i:end + 1])
                or any(item.lstrip().startswith(("!!", "!*")) for item in following)
                or any(item.lstrip().startswith(("!>", "!|")) for item in preceding)):
            continue
        indent = re.match(r"\s*", line).group() + "   "
        desc = descriptions[name].strip()
        insertions[end] = textwrap.wrap(desc, width=100 - len(indent) - 3,
                                       break_long_words=False, break_on_hyphens=False)
    out = []
    for i, line in enumerate(lines):
        out.append(line)
        if i in insertions:
            indent = re.match(r"\s*", lines[i]).group() + "   "
            out.extend(indent + "!! " + text for text in insertions[i])
    return "\n".join(out) + "\n"


def _split_top(s: str) -> list[str]:
    """s split at commas outside parentheses."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def _statements(body: list[str]) -> list[str]:
    """The code of body as statements (continuations joined, comments
    dropped), up to an internal contains."""
    out, cur = [], ""
    for line in body:
        code = strip_comment(line).rstrip()
        s = code.lstrip()
        if s.startswith("&"):
            s = s[1:]
        if s.endswith("&"):
            cur += s[:-1] + " "
            continue
        stmt = (cur + s).strip()
        cur = ""
        if re.match(r"^contains\b", stmt, re.I):
            break
        if stmt:
            out.append(stmt)
    return out


def _type_text(spec: str) -> str:
    spec = re.sub(r"\s+", "", spec.lower())
    m = re.match(r"^(real|integer|complex|logical)(?:\((?:kind=)?(\w+)\))?$", spec)
    if m:
        return m.group(1) + (f"({m.group(2)})" if m.group(2) and m.group(2) != "4" else "")
    m = re.match(r"^character(?:\((?:len=)?([*:\w]+)\))?$", spec)
    if m:
        return f"character({m.group(1) or '1'})"
    m = re.match(r"^type\((\w+)\)$", spec)
    if m:
        return f"type({m.group(1)})"
    return spec


def signature(body: list[str]):
    """(kind, ret, args) of a procedure's lines, args as name:type(dims):
    intent(...):optional entries, ret a function's result type and dims."""
    stmts = _statements(body)
    head = stmts[0]
    m = re.match(r"^(.*?)\b(function|subroutine)\s+(\w+)\s*(?:\(([^)]*)\))?\s*(?:result\s*\(\s*(\w+)\s*\))?",
                 head, re.I)
    if not m:
        return None
    prefix, kind, name, dummies, result = m.groups()
    dummies = [d.strip().lower() for d in (dummies or "").split(",") if d.strip()]
    result = (result or name).lower()
    info = {}
    for s in stmts[1:]:
        if "::" not in s:
            continue
        spec, ents = s.split("::", 1)
        parts = _split_top(spec)
        typ = _type_text(parts[0])
        attrs = [a.strip().lower() for a in parts[1:]]
        dims_attr = next((a[len("dimension"):] for a in attrs if a.startswith("dimension")), "")
        intent = next((re.sub(r"\s+", "", a) for a in attrs if a.startswith("intent")), "")
        optional = "optional" in attrs
        for e in _split_top(ents):
            mm = re.match(r"^(\w+)\s*(\([^=]*\))?", e)
            if not mm:
                continue
            nm = mm.group(1).lower()
            dims = re.sub(r"\s+", "", mm.group(2) or dims_attr)
            if dims:
                # Only the rank: x(n, 2) and x(:,:) are both (:,:).
                dims = "(" + ",".join(":" for _ in _split_top(dims[1:-1])) + ")"
            info[nm] = (typ + dims, intent, optional)
    args = []
    for d in dummies:
        typ, intent, optional = info.get(d, ("?", "", False))
        args.append(":".join([d, typ] + ([intent] if intent else []) + (["optional"] if optional else [])))
    ret = None
    if kind.lower() == "function":
        ptype = re.search(r"\b(real|integer|complex|logical|character)\b(\s*\([^)]*\))?", prefix or "", re.I)
        if result in info:
            ret = info[result][0]
        elif ptype:
            ret = _type_text(ptype.group(0))
    return kind.lower(), ret, args


# Descriptions of public routines whose source has no comment to take one
# from (used by --fill-tags).
DESC_OVERRIDES = {
    "interp_periodic_0d": "np.interp(x, xp, fp, period=p) at a scalar x",
    "loadtxt_real_vector": "np.loadtxt of a one-column (or flattened) text file as a real vector",
    "loadtxt_int_vector": "np.loadtxt(..., dtype=int) of a text file as an integer vector",
    "loadtxt_logical_vector": "np.loadtxt(..., dtype=bool) of a text file as a logical vector (nonzero is true)",
    "c_minimum": "np.minimum of complex numbers in numpy's order (real part, then imaginary part)",
    "cumsum_complex": "cumulative sum of a complex vector",
    "cumprod_complex": "cumulative product of a complex vector",
    "sorted_complex_vec": "np.sort of a complex vector (by real part, then imaginary part, NaN last): a sorted copy",
    "sorted_complex_2d": "np.sort of a complex matrix along dimension dim (1 = down columns)",
    "argsort_complex_2d": "np.argsort (0-based) of a complex matrix along dimension dim",
    "median_complex_2d": "np.median of a complex matrix along dimension dim",
    "repeat_complex": "np.repeat of a complex vector: each element reps times",
    "tile_complex": "np.tile of a complex vector reps times",
    "np_ceil": "np.ceil of a float: NaN and infinities unchanged, no integer conversion",
    "where_indices_2d": "np.argwhere of a logical matrix: the 0-based (row, column) of each true element, in C order",
    "where_axis_2d": "np.nonzero(mask)[axis] of a logical matrix: 0-based row (axis 0) or column (axis 1) indices "
                     "of the true elements, in C order",
    "where_pair_2d": "pair 0-based row and column index vectors (a length-1 one broadcast) as a 2 x n index array",
}


def _first_sentence(text: str) -> str:
    """text up to its first '. ' outside parentheses (at least 20
    characters), at most about 180 characters."""
    depth = 0
    for i, ch in enumerate(text):
        depth += {"(": 1, ")": -1}.get(ch, 0)
        if ch == "." and depth == 0 and i >= 20 and (i + 1 == len(text) or text[i + 1] == " "):
            text = text[:i]
            break
    if len(text) > 180:
        text = text[:177].rsplit(" ", 1)[0] + " ..."
    return text.strip().rstrip(";,:").replace('"', "'")


def leading_comment(body: list[str], before: list[str] | None = None) -> str:
    """The comment lines after a procedure's header (else the ones just
    before it), as one sentence."""
    i = 0
    while i < len(body) and strip_comment(body[i]).rstrip().endswith("&"):
        i += 1
    words = []
    for line in body[i + 1:]:
        s = line.strip()
        if not s.startswith("!"):
            break
        words.append(s.lstrip("!").strip())
    if not words and before:
        for line in reversed(before):
            s = line.strip()
            if not s.startswith("!"):
                break
            words.insert(0, s.lstrip("!").strip())
    return _first_sentence(re.sub(r"\s+", " ", " ".join(words)).strip())


def fill_tags(src: Path) -> int:
    text = src.read_text(encoding="utf-8")
    lines, uses, decls, types, ifaces, tags, procs, order = parse(text)
    out, filled, nodesc = [], 0, []
    for line in text.splitlines():
        mt = TAG.match(line.strip())
        if not (mt and tag_field(mt.group(2), "lib") and not tag_field(mt.group(2), "args")
                and not tag_field(mt.group(2), "kind")):
            out.append(line)
            continue
        name = mt.group(1).lower()
        generic = None
        body = procs.get(name)
        if body is None and name in ifaces:
            generic = ifaces[name][1]
            body = procs.get(generic[0]) if generic else None
        if body is None:
            out.append(line)
            continue
        sig = signature(body)
        if sig is None:
            out.append(line)
            continue
        kind, ret, args = sig
        first = generic[0] if generic else name
        # The comment block just above the procedure, if any.
        start = next((k for k, l in enumerate(lines) if lines[k:k + len(body)] == body), None)
        before = lines[max(0, start - 6):start] if start else []
        desc = (DESC_OVERRIDES.get(name) or DESC_OVERRIDES.get(first)
                or (tag_field(tags[first], "desc") if generic and first in tags else None)
                or leading_comment(body, before))
        if generic:
            desc = (desc + " " if desc else "") + f"(generic: {', '.join(generic)})"
        if not desc:
            nodesc.append(name)
        lib = tag_field(mt.group(2), "lib")
        parts = [f"kind={kind}"] + ([f"ret={ret}"] if ret else []) + [f"args={','.join(args)}", f"lib={lib}"]
        if desc:
            parts.append(f'desc="{desc}"')
        out.append(f"public :: {mt.group(1)} !@pyapi " + " ".join(parts))
        filled += 1
    src.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"tags filled: {filled}; without a description: {len(nodesc)} {nodesc}")
    return 0


def apply_topics(src: Path, table: Path) -> int:
    topics = {}
    for line in table.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("routine\t"):
            continue
        f = line.split("\t")
        if len(f) >= 2 and f[1].strip():
            topics[f[0].strip().lower()] = f[1].strip()
    lines = src.read_text(encoding="utf-8").splitlines()
    out, changed, added, untouched = [], 0, 0, set(topics)
    for line in lines:
        mt = TAG.match(line.strip())
        if mt and mt.group(1).lower() in topics:
            name = mt.group(1).lower()
            untouched.discard(name)
            topic = topics[name]
            new = re.sub(r"\s+lib=\S+", "", line)
            if topic not in {"exclude", "internal"}:
                new = (re.sub(r"(\s+desc=)", rf" lib={topic}\1", new, count=1) if " desc=" in new
                       else new.rstrip() + f" lib={topic}")
            changed += new != line
            out.append(new)
            continue
        m = re.match(r"^public\s*::\s*([^!]*)$", line.strip(), re.I)
        if m and "@pyapi" not in line:
            names = [n.strip() for n in m.group(1).split(",") if n.strip()]
            keep, own = [], []
            for n in names:
                untouched.discard(n.lower())
                tp = topics.get(n.lower())
                (own if tp and tp not in {"exclude", "internal"} else keep).append((n, tp))
            if own:
                if keep:
                    out.append("public :: " + ", ".join(n for n, _ in keep))
                for n, tp in own:
                    out.append(f"public :: {n} !@pyapi lib={tp}")
                    added += 1
                continue
        out.append(line)
    src.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    print(f"tags changed: {changed}; tags added: {added}; table names not found: {sorted(untouched)}")
    return 0


TOPIC_HEADINGS = {
    "arrays": "Array creation and manipulation",
    "calculus": "Calculus and interpolation",
    "fft": "Fast Fourier transforms",
    "integers": "Integer operations",
    "io": "Input and output",
    "linalg": "Linear algebra",
    "math": "Mathematical functions",
    "polynomial": "Polynomials",
    "random": "Random sampling",
    "signal": "Signal processing",
    "sorting": "Sorting and searching",
    "special": "Special functions",
    "statistics": "Statistics",
    "timeseries": "Time series",
}


def grouped_public_declarations(by_topic, width=100):
    """Alphabetize topics/names and pack names without continuation lines."""
    lines = []
    prefix = "public :: "
    for topic in sorted(by_topic):
        names = sorted(by_topic[topic])
        if not names:
            continue
        lines += ["", "! " + TOPIC_HEADINGS.get(topic, topic.replace("_", " ").capitalize())]
        line = prefix
        for name in names:
            separator = "" if line == prefix else ", "
            if line != prefix and len(line) + len(separator) + len(name) > width:
                lines.append(line)
                line = prefix
                separator = ""
            line += separator + name
        lines.append(line)
    if lines:
        lines.append("")
    return lines


def omit_inherited_uses(lines, module_uses):
    """Omit redundant simple intrinsic USE ONLY lists in module procedures.

    Keep interfaces (no automatic host association), internal procedures and
    BLOCK scopes (possible host shadowing), renames, unrestricted imports and
    continued statements. Partial overlap is retained rather than rewritten.
    """
    pattern = re.compile(
        r"^use\s*,\s*intrinsic\s*::\s*([a-z_]\w*)\s*,\s*only\s*:\s*"
        r"([a-z_]\w*(?:\s*,\s*[a-z_]\w*)*)\s*$", re.I)
    inherited = defaultdict(set)
    for line in module_uses:
        match = pattern.fullmatch(strip_comment(line).strip())
        if match:
            inherited[match[1].lower()].update(n.strip().lower() for n in match[2].split(','))
    output = []
    interface_depth = procedure_depth = block_depth = 0
    continued = False
    for line in lines:
        code = strip_comment(line).strip()
        was_continued, continued = continued, code.endswith('&')
        if IFACE_END.match(code):
            interface_depth -= 1
        elif re.match(r"^(?:abstract\s+)?interface\b", code, re.I):
            interface_depth += 1
        elif not interface_depth:
            if PROC_END.match(code) or re.fullmatch(r"end", code, re.I):
                procedure_depth -= 1
            elif PROC_START.match(code):
                procedure_depth += 1
            elif re.fullmatch(r"end\s*block(?:\s+\w+)?", code, re.I):
                block_depth -= 1
            elif re.fullmatch(r"(?:\w+\s*:\s*)?block", code, re.I):
                block_depth += 1
            elif procedure_depth == 1 and not block_depth and not was_continued:
                match = pattern.fullmatch(code)
                if match and {n.strip().lower() for n in match[2].split(',')} <= inherited[match[1].lower()]:
                    if '!' in line:
                        output.append(line[:len(line) - len(line.lstrip())] + line[line.index('!'):])
                    continue
        output.append(line)
    return output


def omit_inherited_implicit_none(lines):
    """Omit plain IMPLICIT NONE where the host already supplies it.

    Interface bodies have independent implicit typing rules. An internal
    procedure below a host with explicit implicit typing also needs its
    own IMPLICIT NONE, so retain it in that case.
    """
    output = []
    scopes = []
    interface_depth = 0
    for line in lines:
        code = strip_comment(line).strip()
        if IFACE_END.match(code):
            interface_depth -= 1
        elif re.match(r"^(?:abstract\s+)?interface\b", code, re.I):
            interface_depth += 1
        elif not interface_depth:
            if PROC_END.match(code) or re.fullmatch(r"end", code, re.I):
                if scopes:
                    scopes.pop()
            elif PROC_START.match(code):
                scopes.append(scopes[-1] if scopes else True)
            elif scopes and re.fullmatch(r"implicit\s+none", code, re.I):
                inherited = scopes[-1]
                scopes[-1] = True
                if inherited:
                    # Retain useful comments attached to the removed statement.
                    if "!" in line:
                        indent = line[:len(line) - len(line.lstrip())]
                        output.append(indent + line[line.index("!"):])
                    continue
            elif scopes and re.match(r"implicit\b", code, re.I):
                # Conservatively retain descendants' declarations after
                # any other IMPLICIT specification in the host.
                scopes[-1] = False
        output.append(line)
    return output


def promote_library_elementals(lines):
    """Promote scalar pure helpers in the extracted library's own call graph.

    Unlike python.f90, the extracted module need not preserve transpiler
    callback uses outside this module. Internal procedure-argument uses
    still prevent promotion. Compiler verification remains enabled by default.
    """
    lines = fortran_purity.mark_elemental_where_provable(lines)
    return [re.sub(r"^(\s*)elemental\b", r"\1pure elemental", line, flags=re.I)
            for line in lines]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=HERE / "python.f90")
    ap.add_argument("--out", type=Path, default=HERE / "fortran_lib")
    ap.add_argument("--module", default="numpy_fortran")
    ap.add_argument("--topics", default="", help="comma-separated lib= topics (default: all)")
    ap.add_argument("--no-compile", action="store_true")
    ap.add_argument("--apply-topics", type=Path, help="set the tags' lib= topics from this table and stop")
    ap.add_argument("--fill-tags", action="store_true", help="complete tags that have only lib= and stop")
    args = ap.parse_args()
    if args.apply_topics:
        return apply_topics(args.src, args.apply_topics)
    if args.fill_tags:
        return fill_tags(args.src)
    source = add_ford_api_summaries(args.src.read_text(encoding="utf-8"))
    lines, uses, decls, types, ifaces, tags, procs, order = parse(source)
    topics = {t for t in args.topics.split(",") if t}
    lib = {n: t for n, t in tags.items() if tag_field(t, "lib") and (not topics or tag_field(t, "lib") in topics)}
    by_topic = defaultdict(list)
    for n, t in lib.items():
        by_topic[tag_field(t, "lib")].append(n)
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
            if m and m.group(1).lower() not in defined | INTRINSIC_SUBROUTINES:
                externals.add(m.group(1).lower())
    args.out.mkdir(parents=True, exist_ok=True)
    o = [f"! {args.module}: numerical routines (numpy's algorithms) extracted from python.f90",
         "! of the Python-to-Fortran transpiler by xextract_fortran_lib.py. Do not edit:",
         "! regenerate from python.f90. See that project's README (Third-Party Code)",
         "! for the sources and licenses of code adapted from other projects.",
         f"module {args.module}"]
    o += ["!! Standalone numerical helpers extracted from `python.f90`.",
          "!!", "!! Public routines are grouped by topic in ROUTINES.md. Generic interfaces",
          "!! select the appropriate type and rank; consult each specific signature.",
          "!! LAPACK-backed routines require the external LAPACK procedures at link time.",
          "!! Regenerate this module rather than editing it; documentation lives in python.f90."]
    o += uses + ["implicit none", "private"]
    o += [l for names, l in decls if set(names) & need_decls]
    for n in sorted(need_types):
        o += types[n]
    o += grouped_public_declarations(by_topic)
    for n in sorted(need_ifaces):
        o += ifaces[n][0]
    o.append("contains")
    for n in order:
        if n in need_procs:
            o.append("")
            o += omit_inherited_implicit_none(omit_inherited_uses(procs[n], uses))
    o.append(f"end module {args.module}")
    o = promote_library_elementals(o)
    f90 = args.out / f"{args.module}.f90"
    f90.write_text("\n".join(o) + "\n", encoding="utf-8")
    # Routine list.
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
