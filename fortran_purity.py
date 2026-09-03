"""Determine PURE-eligibility of generated Fortran procedures by examining
the EMITTED Fortran text, not the Python source that produced it.

Ported (and trimmed to just what xp2f.py needs) from the sibling project's
c:\\python\\fortran\\xpure.py / fortran_scan.py -- a mature, already-tested
static analyzer that scans procedures in a Fortran source file, ignores ones
already marked pure/elemental, flags concrete purity blockers (I/O, RNG/
system intrinsics, calls to known non-pure procedures, writes to
INTENT(IN) dummies, SAVE/DATA statements, non-local assignments, etc.), and
propagates purity through the call graph to a fixed point.

Why Fortran-level rather than Python-AST-level: xp2f.py's OWN Python-AST
purity heuristic (function_is_pure/compute_local_functions_purity) has to
keep pace with every Python construct the transpiler ever supports (numpy
methods, math/cmath, scipy, pandas, ...) -- a structurally open-ended list
that's easy to leave gaps in (confirmed missing: bare `math.sqrt(...)`/
`math.erf(...)` calls, and an overly-conservative rule that disqualifies
`x = np.asarray(x, ...)`-style argument rebinding even though the codegen
always safely shadow-copies it into a fresh local rather than writing the
actual INTENT(IN) dummy). What Fortran's `pure` keyword actually requires is
a small, fixed vocabulary -- no write to an INTENT(IN)/unspecified-intent
dummy, no I/O, no call to an impure procedure, no module-state mutation --
checkable directly against the EMITTED code, with no per-Python-feature
special-casing needed at all.

This module is used ADDITIVELY: xp2f.py's existing Python-AST pass still
runs first and still marks whatever it currently marks pure. This module
then runs as a later post-processing pass over the fully-generated (and
already text-cleaned-up) Fortran, and promotes any STILL-not-pure procedure
to `pure` when the Fortran-level analysis proves it's safe. It only ever
ADDS `pure`, never removes one the earlier pass already decided on -- so a
gap in this port can only mean a missed opportunity, never a wrong build.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

PROC_START_RE = re.compile(
    r"^\s*(?P<preprefix>(?:(?:pure|elemental|impure|recursive|module)\s+)*)"
    r"(?P<lead>(?:(?:double\s+precision|integer|real|logical|complex|character\b(?:\s*\([^)]*\))?"
    r"|type\s*\([^)]*\)|class\s*\([^)]*\))\s*(?:\([^)]*\))?\s*,?\s*)?)"
    r"(?P<prefix>(?:(?:pure|elemental|impure|recursive|module)\s+)*)"
    r"(?P<kind>function|subroutine)\s+"
    r"(?P<name>[a-z][a-z0-9_]*)\s*(?P<arglist>\([^)]*\))?",
    re.IGNORECASE,
)

PRINT_RE = re.compile(r"^\s*print\b", re.IGNORECASE)
READ_RE = re.compile(r"^\s*read\s*\(", re.IGNORECASE)
WRITE_RE = re.compile(r"^\s*write\s*\(", re.IGNORECASE)
INLINE_IO_RE = re.compile(r"\)\s*(read|write)\s*\(", re.IGNORECASE)
FILE_IO_RE = re.compile(r"^\s*(open|close|rewind|backspace|flush|inquire)\b", re.IGNORECASE)
SAVE_STMT_RE = re.compile(r"^\s*save\b", re.IGNORECASE)
DATA_STMT_RE = re.compile(r"^\s*data\b", re.IGNORECASE)

ERROR_STOP_RE = re.compile(r"\berror\s+stop\b", re.IGNORECASE)
STOP_RE = re.compile(r"\bstop\b", re.IGNORECASE)

CALL_RE = re.compile(r"\bcall\s+([a-z][a-z0-9_]*)\b", re.IGNORECASE)
INVOCATION_RE = re.compile(r"\b([a-z][a-z0-9_]*)\s*(?=\()", re.IGNORECASE)
TYPE_BOUND_INVOCATION_RE = re.compile(r"%\s*([a-z][a-z0-9_]*)\s*(?=\()", re.IGNORECASE)
USE_RE = re.compile(
    r"^\s*use\b(?:\s*,\s*(?:non_intrinsic|intrinsic)\s*)?(?:\s*::\s*|\s+)([a-z][a-z0-9_]*)",
    re.IGNORECASE,
)
INTERFACE_START_RE = re.compile(r"^\s*(abstract\s+)?interface\b(?:\s+([a-z][a-z0-9_]*))?", re.IGNORECASE)
END_INTERFACE_RE = re.compile(r"^\s*end\s+interface\b", re.IGNORECASE)
MODULE_PROCEDURE_RE = re.compile(r"^\s*module\s+procedure\b(.+)$", re.IGNORECASE)
PROCEDURE_DECL_RE = re.compile(r"^\s*procedure\s*\(", re.IGNORECASE)
EXTERNAL_STMT_RE = re.compile(r"^\s*external\b(?P<rhs>.*)$", re.IGNORECASE)
PROCEDURE_BINDING_ALIAS_RE = re.compile(r"^\s*procedure\b(?:\s*,[^:]*)?\s*::\s*(.+)$", re.IGNORECASE)
USE_ONLY_RE = re.compile(r"^\s*use\b.*?\bonly\s*:\s*(.+)$", re.IGNORECASE)
GENERIC_BINDING_RE = re.compile(r"^\s*generic\b(?:\s*,[^:]*)?\s*::\s*([a-z]\w*)\s*=>\s*(.+)$", re.IGNORECASE)
TYPE_DECL_RE = re.compile(
    r"^\s*(integer|real|logical|character|complex|type\b|class\b|procedure\b)",
    re.IGNORECASE,
)
NO_COLON_DECL_RE = re.compile(
    r"^\s*(?P<spec>(?:integer|real|logical|complex|character)\s*(?:\([^)]*\))?"
    r"|type\s*\([^)]*\)|class\s*\([^)]*\))\s+(?P<rhs>.+)$",
    re.IGNORECASE,
)
ASSIGN_RE = re.compile(
    r"^\s*([a-z][a-z0-9_]*(?:\s*%\s*[a-z][a-z0-9_]*)?)\s*(?:\([^)]*\))?\s*=",
    re.IGNORECASE,
)
ALLOC_DEALLOC_RE = re.compile(r"^\s*(allocate|deallocate)\s*\((.+)\)\s*$", re.IGNORECASE)
DO_ITERATOR_RE = re.compile(r"^\s*(?:[a-z][a-z0-9_]*\s*:\s*)?do\s+([a-z][a-z0-9_]*)\s*=", re.IGNORECASE)
DECL_RE = re.compile(
    r"^(\s*)(?P<preprefix>(?:(?:pure|elemental|impure|recursive|module)\s+)*)"
    r"(?P<lead>(?:(?:double\s+precision|integer|real|logical|complex|character\b(?:\s*\([^)]*\))?"
    r"|type\s*\([^)]*\)|class\s*\([^)]*\))\s*(?:\([^)]*\))?\s*,?\s*)?)"
    r"(?P<prefix>(?:(?:pure|elemental|impure|recursive|module)\s+)*)"
    r"(?P<kind>function|subroutine)\b",
    re.IGNORECASE,
)

IMPURE_INTRINSICS = {
    "random_number",
    "random_seed",
    "random_normal",
    "date_and_time",
    "cpu_time",
    "system_clock",
    "execute_command_line",
    "get_command",
    "get_command_argument",
    "get_environment_variable",
}


def strip_comment(line: str) -> str:
    """Strip trailing Fortran comments while preserving quoted text."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "!" and not in_single and not in_double:
            return line[:i]
    return line


def split_fortran_statements(code: str) -> List[str]:
    """Split code into semicolon-delimited statements, respecting quoted strings."""
    out: List[str] = []
    cur: List[str] = []
    in_single = False
    in_double = False
    for ch in code:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            seg = "".join(cur).strip()
            if seg:
                out.append(seg)
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


def join_continued_lines(lines: Iterable[str]) -> List[Tuple[int, str]]:
    """Join free-form continuation lines and keep the originating start line."""
    out: List[Tuple[int, str]] = []
    cur_parts: List[str] = []
    cur_start: Optional[int] = None
    need_more = False

    for lineno, raw in enumerate(lines, start=1):
        code = strip_comment(raw).rstrip("\r\n")
        seg = code.rstrip()
        if not seg and not need_more:
            continue

        if cur_start is None:
            cur_start = lineno

        if cur_parts:
            lead = seg.lstrip()
            if lead.startswith("&"):
                seg = lead[1:].lstrip()

        seg = seg.rstrip()
        has_trailing_cont = seg.endswith("&")
        if has_trailing_cont:
            seg = seg[:-1].rstrip()

        if seg:
            cur_parts.append(seg)

        need_more = has_trailing_cont
        if need_more:
            continue

        joined = " ".join(cur_parts).strip()
        if joined:
            out.append((cur_start, joined))
        cur_parts = []
        cur_start = None

    if cur_parts and cur_start is not None:
        joined = " ".join(cur_parts).strip()
        if joined:
            out.append((cur_start, joined))
    return out


def iter_fortran_statements(lines: Iterable[str]) -> List[Tuple[int, str]]:
    """Return semicolon-split statements as (start_line, statement_text)."""
    out: List[Tuple[int, str]] = []
    for lineno, joined in join_continued_lines(lines):
        for stmt in split_fortran_statements(joined):
            if stmt:
                out.append((lineno, stmt))
    return out


def executable_action(line: str) -> str:
    """Return the action after nested single-line IF conditions, if present."""
    action = line.strip()
    while re.match(r"^if\s*\(", action, re.IGNORECASE):
        open_paren = action.find("(")
        depth = 0
        in_single = False
        in_double = False
        close_paren = -1
        i = open_paren
        while i < len(action):
            ch = action[i]
            if ch == "'" and not in_double:
                if in_single and i + 1 < len(action) and action[i + 1] == "'":
                    i += 2
                    continue
                in_single = not in_single
            elif ch == '"' and not in_single:
                if in_double and i + 1 < len(action) and action[i + 1] == '"':
                    i += 2
                    continue
                in_double = not in_double
            elif not in_single and not in_double:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        close_paren = i
                        break
            i += 1
        if close_paren < 0:
            return action
        tail = action[close_paren + 1:].lstrip()
        if not tail or re.match(r"^then\b", tail, re.IGNORECASE):
            return action
        action = tail
    return action


@dataclass
class Procedure:
    name: str
    kind: str
    start: int
    end: int = -1
    attrs: Set[str] = field(default_factory=set)
    body: List[Tuple[int, str]] = field(default_factory=list)
    parent: Optional[str] = None
    dummy_names: Set[str] = field(default_factory=set)
    dummy_args: List[str] = field(default_factory=list)
    result_name: Optional[str] = None

    @property
    def is_pure_or_elemental(self) -> bool:
        return "pure" in self.attrs or "elemental" in self.attrs

    @property
    def selector(self) -> str:
        return f"{self.name}@{self.start}"


@dataclass
class AnalysisResult:
    procedures: List[Procedure]
    candidates: List[Procedure]
    rejected: List[Tuple[Procedure, List[str]]]
    procedure_actual_names: Set[str] = field(default_factory=set)


def parse_arglist_order(arglist: Optional[str]) -> List[str]:
    """Parse procedure arguments while preserving their declared order."""
    if not arglist:
        return []
    inner = arglist.strip()[1:-1].strip()
    if not inner:
        return []
    out: List[str] = []
    for tok in inner.split(","):
        name = tok.strip().lower()
        if re.match(r"^[a-z][a-z0-9_]*$", name):
            out.append(name)
    return out


def split_top_level_commas(text: str) -> List[str]:
    """Split text by top-level commas, ignoring nested parentheses and strings."""
    out: List[str] = []
    cur: List[str] = []
    depth = 0
    in_single = False
    in_double = False
    for ch in text:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            elif ch == "," and depth == 0:
                out.append("".join(cur).strip())
                cur = []
                continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail:
        out.append(tail)
    return out


def parse_declared_names_from_decl(line: str) -> Set[str]:
    """Extract declared names from a Fortran declaration line."""
    if "::" not in line:
        return set()
    rhs = line.split("::", 1)[1]
    out: Set[str] = set()
    for chunk in rhs.split(","):
        name = chunk.strip()
        if not name:
            continue
        if "=" in name and "=>" not in name:
            name = name.split("=", 1)[0].strip()
        if "=>" in name:
            name = name.split("=>", 1)[0].strip()
        m = re.match(r"^([a-z][a-z0-9_]*)", name, re.IGNORECASE)
        if m:
            out.add(m.group(1).lower())
    return out


def parse_declared_names_any(line: str) -> Set[str]:
    """Extract declared names from declarations with or without ::."""
    if "::" in line:
        return parse_declared_names_from_decl(line)
    m = NO_COLON_DECL_RE.match(line.strip())
    if not m:
        return set()
    out: Set[str] = set()
    for chunk in split_top_level_commas(m.group("rhs")):
        name = chunk.strip()
        if not name:
            continue
        if "=" in name and "=>" not in name:
            name = name.split("=", 1)[0].strip()
        if "=>" in name:
            name = name.split("=>", 1)[0].strip()
        mm = re.match(r"^([a-z][a-z0-9_]*)", name, re.IGNORECASE)
        if mm:
            out.add(mm.group(1).lower())
    return out


def parse_declared_entities(line: str) -> List[Tuple[str, bool]]:
    """Extract declared entities and whether each has an inline array spec."""
    rhs = ""
    if "::" in line:
        rhs = line.split("::", 1)[1]
    else:
        m = NO_COLON_DECL_RE.match(line.strip())
        if not m:
            return []
        rhs = m.group("rhs")
    out: List[Tuple[str, bool]] = []
    for chunk in split_top_level_commas(rhs):
        text = chunk.strip()
        if not text:
            continue
        m = re.match(r"^([a-z][a-z0-9_]*)\s*(\()?", text, re.IGNORECASE)
        if not m:
            continue
        out.append((m.group(1).lower(), m.group(2) is not None))
    return out


def base_identifier(expr: str) -> Optional[str]:
    """Return the base identifier at the start of an expression string."""
    m = re.match(r"^\s*([a-z][a-z0-9_]*)", expr, re.IGNORECASE)
    if not m:
        return None
    return m.group(1).lower()


def declaration_has_saved_initialization(line: str) -> bool:
    """Whether a local declaration initializes a non-constant entity.

    Explicit initialization gives a local variable implicit SAVE semantics,
    which is forbidden in a pure procedure. PARAMETER initialization is the
    intentional exception.
    """
    if "::" not in line:
        return False
    attributes, entities = line.split("::", 1)
    if re.search(r"\bparameter\b", attributes, re.IGNORECASE):
        return False
    return any("=" in entity for entity in split_top_level_commas(entities))


def procedure_modified_dummies(proc: Procedure) -> Set[Tuple[int, str]]:
    """Return zero-based positions and names of INTENT(OUT/INOUT) dummies."""
    modified: Set[Tuple[int, str]] = set()
    positions = {name: index for index, name in enumerate(proc.dummy_args)}
    for _line_number, code in proc.body:
        low = code.lower()
        intent = parse_decl_intent(low)
        if intent not in {"out", "inout"}:
            continue
        for name in parse_declared_names_any(low) & proc.dummy_names:
            if name in positions:
                modified.add((positions[name], name))
    return modified


def procedure_dummy_procedures(proc: Procedure) -> Set[Tuple[int, str]]:
    """Return positions and names of dummy arguments that are procedures."""
    procedure_dummies: Set[Tuple[int, str]] = set()
    positions = {name: index for index, name in enumerate(proc.dummy_args)}
    for _line_number, code in proc.body:
        low = code.lower()
        declared: Set[str] = set()
        if PROCEDURE_DECL_RE.match(low):
            declared = parse_declared_names_any(low)
        elif TYPE_DECL_RE.match(low) and re.search(r"\bexternal\b", low):
            declared = parse_declared_names_any(low)
        else:
            external_match = EXTERNAL_STMT_RE.match(low)
            if external_match:
                for item in split_top_level_commas(external_match.group("rhs")):
                    match = re.match(r"^\s*([a-z][a-z0-9_]*)", item, re.IGNORECASE)
                    if match:
                        declared.add(match.group(1).lower())
        for name in declared & proc.dummy_names:
            procedure_dummies.add((positions[name], name))
    return procedure_dummies


def call_actual_arguments(line: str, call_match: "re.Match[str]") -> List[str]:
    """Extract actual argument text following a matched procedure name."""
    position = call_match.end()
    while position < len(line) and line[position].isspace():
        position += 1
    if position >= len(line) or line[position] != "(":
        return []
    start = position + 1
    depth = 1
    in_single = False
    in_double = False
    position += 1
    while position < len(line):
        character = line[position]
        if character == "'" and not in_double:
            in_single = not in_single
        elif character == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    return split_top_level_commas(line[start:position])
        position += 1
    return []


def modified_call_actuals(actuals: List[str], modified_dummies: Set[Tuple[int, str]]) -> List[str]:
    """Resolve actual expressions corresponding to modified dummy arguments."""
    positional: List[str] = []
    keyword: Dict[str, str] = {}
    for actual in actuals:
        match = re.match(r"^\s*([a-z][a-z0-9_]*)\s*=(?!=|>)\s*(.+)$", actual, re.IGNORECASE)
        if match:
            keyword[match.group(1).lower()] = match.group(2).strip()
        else:
            positional.append(actual.strip())
    resolved = []
    for position, dummy_name in modified_dummies:
        if dummy_name in keyword:
            resolved.append(keyword[dummy_name])
        elif position < len(positional):
            resolved.append(positional[position])
    return resolved


def parse_type_bound_bindings(lines: List[str]) -> Dict[str, Set[str]]:
    """Map type-bound binding and generic names to implementation procedures."""
    bindings: Dict[str, Set[str]] = {}
    pending_generics: List[Tuple[str, List[str]]] = []
    for line in lines:
        low = line.lower().strip()
        procedure_match = PROCEDURE_BINDING_ALIAS_RE.match(low)
        if procedure_match:
            for item in split_top_level_commas(procedure_match.group(1)):
                if "=>" not in item:
                    continue
                binding, implementation = (part.strip() for part in item.split("=>", 1))
                if re.fullmatch(r"[a-z]\w*", binding) and re.fullmatch(r"[a-z]\w*", implementation):
                    bindings.setdefault(binding, set()).add(implementation)
            continue
        generic_match = GENERIC_BINDING_RE.match(low)
        if generic_match:
            names = [name.strip() for name in split_top_level_commas(generic_match.group(2))]
            pending_generics.append((generic_match.group(1).lower(), names))
    for generic, names in pending_generics:
        targets = bindings.setdefault(generic, set())
        for name in names:
            targets.update(bindings.get(name, {name}))
    return bindings


def parse_impure_deferred_type_bound_bindings(lines: List[str]) -> Set[str]:
    """Return deferred binding names whose abstract interfaces are not PURE."""
    explicitly_pure_interfaces = {
        proc.name.lower() for proc in parse_procedures(lines) if proc.is_pure_or_elemental
    }
    impure_bindings: Set[str] = set()
    deferred_re = re.compile(
        r"^\s*procedure\s*\(\s*([a-z][a-z0-9_]*)\s*\)"
        r"\s*,[^:]*\bdeferred\b[^:]*::\s*(.+)$",
        re.IGNORECASE,
    )
    for _line_number, line in join_continued_lines(lines):
        match = deferred_re.match(line)
        if not match or match.group(1).lower() in explicitly_pure_interfaces:
            continue
        for item in split_top_level_commas(match.group(2)):
            binding = item.split("=>", 1)[0].strip().lower()
            if re.fullmatch(r"[a-z][a-z0-9_]*", binding):
                impure_bindings.add(binding)
    return impure_bindings


def parse_use_renames(lines: List[str]) -> Dict[str, Set[str]]:
    """Map local names in USE, ONLY rename lists to imported names."""
    renames: Dict[str, Set[str]] = {}
    for _line_number, line in join_continued_lines(lines):
        match = USE_ONLY_RE.match(line.lower().strip())
        if not match:
            continue
        for item in split_top_level_commas(match.group(1)):
            if "=>" not in item:
                continue
            local_name, imported_name = (part.strip() for part in item.split("=>", 1))
            if re.fullmatch(r"[a-z]\w*", local_name) and re.fullmatch(r"[a-z]\w*", imported_name):
                renames.setdefault(local_name, set()).add(imported_name)
    return renames


def parse_use_only_names(lines: List[str]) -> Set[str]:
    """Return local names imported by non-intrinsic USE, ONLY statements."""
    imported: Set[str] = set()
    for _line_number, line in join_continued_lines(lines):
        low = line.lower().strip()
        if re.match(r"^use\s*,\s*intrinsic\b", low):
            continue
        match = USE_ONLY_RE.match(low)
        if not match:
            continue
        for item in split_top_level_commas(match.group(1)):
            local_name = item.split("=>", 1)[0].strip()
            if re.fullmatch(r"[a-z][a-z0-9_]*", local_name):
                imported.add(local_name)
    return imported


def extract_io_control_list(line: str, keyword: str) -> Optional[str]:
    """Extract the control-list substring from READ/WRITE statement text."""
    s = line.strip()
    if not s.lower().startswith(keyword):
        return None
    p0 = s.find("(")
    if p0 < 0:
        return None
    depth = 0
    in_single = False
    in_double = False
    for i in range(p0, len(s)):
        ch = s[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return s[p0 + 1:i]
    return None


def parse_decl_intent(line_low: str) -> Optional[str]:
    """Parse INTENT information from a declaration fragment."""
    m = re.search(r"\bintent\s*\(\s*(inout|out|in)\s*\)", line_low)
    if m:
        return m.group(1).lower()
    return None


def decl_has_value_attr(line_low: str, declared: Set[str]) -> bool:
    """Return True when VALUE appears in declaration attribute/spec context."""
    if not declared:
        return False
    if "::" in line_low:
        spec = line_low.split("::", 1)[0]
        return re.search(r"\bvalue\b", spec) is not None

    first_name_pos: Optional[int] = None
    for name in declared:
        m = re.search(rf"\b{re.escape(name.lower())}\b", line_low)
        if m:
            if first_name_pos is None or m.start() < first_name_pos:
                first_name_pos = m.start()
    if first_name_pos is None:
        return False
    spec = line_low[:first_name_pos]
    return re.search(r"\bvalue\b", spec) is not None


def io_unit_expr_from_control(control: str) -> Optional[str]:
    """Return the unit expression from an I/O control list when present."""
    tokens = split_top_level_commas(control)
    if not tokens:
        return None
    for tok in tokens:
        if "=" in tok:
            lhs, rhs = tok.split("=", 1)
            if lhs.strip().lower() == "unit":
                return rhs.strip()
    first = tokens[0].strip()
    if "=" in first:
        return None
    return first


def parse_procedures(lines: List[str]) -> List[Procedure]:
    """Parse procedures and their bodies from source lines."""
    stack: List[Procedure] = []
    out: List[Procedure] = []
    interface_depth = 0

    for lineno, stmt in iter_fortran_statements(lines):
        low = stmt.lower().strip()

        if re.match(r"^\s*(abstract\s+)?interface\b", low):
            interface_depth += 1
            continue
        if re.match(r"^\s*end\s+interface\b", low):
            if interface_depth > 0:
                interface_depth -= 1
            continue

        if interface_depth > 0:
            continue

        m_start = PROC_START_RE.match(low)
        if m_start:
            attrs = set((m_start.group("preprefix") or "").split())
            attrs.update((m_start.group("prefix") or "").split())
            parent = stack[-1].name if stack else None
            dummy_args = parse_arglist_order(m_start.group("arglist"))
            dummy_names = set(dummy_args)
            m_result = re.search(r"\bresult\s*\(\s*([a-z][a-z0-9_]*)\s*\)", low, re.IGNORECASE)
            result_name = m_result.group(1).lower() if m_result else None
            if result_name is None and m_start.group("kind").lower() == "function":
                result_name = m_start.group("name").lower()
            stack.append(
                Procedure(
                    name=m_start.group("name"),
                    kind=m_start.group("kind"),
                    start=lineno,
                    attrs=attrs,
                    parent=parent,
                    dummy_names=dummy_names,
                    dummy_args=dummy_args,
                    result_name=result_name,
                )
            )
            continue

        if stack and low.startswith("end"):
            toks = low.split()
            is_proc_end = False
            end_kind: Optional[str] = None
            if len(toks) == 1 and toks[0] == "end":
                is_proc_end = True
            elif len(toks) >= 2 and toks[0] == "end" and toks[1] in {"function", "subroutine"}:
                is_proc_end = True
                end_kind = toks[1]
            if is_proc_end:
                top = stack[-1]
                if end_kind is None or end_kind == top.kind:
                    top.end = lineno
                    out.append(stack.pop())
                    continue

        if stack:
            stack[-1].body.append((lineno, stmt))

    while stack:
        top = stack.pop()
        top.end = len(lines)
        out.append(top)

    out.sort(key=lambda p: p.start)
    return out


def has_function_reference(line: str, callee: str) -> bool:
    """Heuristically detect function-style references to a given name in code."""
    return re.search(rf"\b{re.escape(callee)}\s*\(", line, flags=re.IGNORECASE) is not None


IDENT_RE = re.compile(r"[a-z][a-z0-9_]*", re.IGNORECASE)


def line_identifiers(line: str) -> Set[str]:
    """Extract lowercase identifiers from one Fortran statement line."""
    return {m.group(0).lower() for m in IDENT_RE.finditer(line)}


def parse_module_procedure_pointers(lines: List[str], procedures: List[Procedure]) -> Set[str]:
    """Return procedure pointers declared outside procedure bodies."""
    procedure_ranges = [(proc.start, proc.end) for proc in procedures]
    names: Set[str] = set()
    for lineno, stmt in iter_fortran_statements(lines):
        if any(start <= lineno <= end for start, end in procedure_ranges):
            continue
        low = stmt.strip().lower()
        if PROCEDURE_DECL_RE.match(low) and re.search(r"\bpointer\b", low):
            names.update(parse_declared_names_any(low))
    return names


def procedures_used_as_actual_arguments(
    parsed_by_key: Dict[str, List[Procedure]],
    procedure_bindings: Optional[Dict[str, Set[str]]] = None,
    generic_interfaces: Optional[Dict[str, Set[str]]] = None,
    statements_by_key: Optional[Dict[str, List[str]]] = None,
) -> Set[str]:
    """Find source procedures passed to procedure dummy arguments."""
    known_procedure_names = {
        proc.name.lower() for procedures in parsed_by_key.values() for proc in procedures
    }
    procedure_dummies_by_name: Dict[str, Set[Tuple[int, str]]] = {}
    for procedures in parsed_by_key.values():
        for proc in procedures:
            procedure_dummies_by_name.setdefault(proc.name.lower(), set()).update(
                procedure_dummy_procedures(proc)
            )

    aliases: Dict[str, Set[str]] = {}
    for name, targets in (generic_interfaces or {}).items():
        aliases.setdefault(name, set()).update(targets)
    for name, targets in (procedure_bindings or {}).items():
        aliases.setdefault(name, set()).update(targets)
    for alias, targets in aliases.items():
        positions: Set[Tuple[int, str]] = set()
        for target in targets:
            positions.update(procedure_dummies_by_name.get(target, set()))
        if positions:
            procedure_dummies_by_name.setdefault(alias, set()).update(positions)

    used_as_actual: Set[str] = set()
    for key, procedures in parsed_by_key.items():
        if statements_by_key is None:
            statements = [code for proc in procedures for _line_number, code in proc.body]
        else:
            statements = statements_by_key.get(key, [])
        for code in statements:
            low = code.lower()
            if TYPE_DECL_RE.match(low) or EXTERNAL_STMT_RE.match(low):
                continue
            for match in INVOCATION_RE.finditer(low):
                callee = match.group(1).lower()
                actuals = call_actual_arguments(low, match)
                for actual in actuals:
                    keyword_match = re.match(
                        r"^\s*[a-z][a-z0-9_]*\s*=(?!=|>)\s*(.+)$", actual, re.IGNORECASE
                    )
                    expression = keyword_match.group(1) if keyword_match else actual
                    actual_match = re.fullmatch(r"\s*([a-z][a-z0-9_]*)\s*", expression, re.IGNORECASE)
                    if actual_match:
                        actual_name = actual_match.group(1).lower()
                        if actual_name in known_procedure_names:
                            used_as_actual.add(actual_name)

                procedure_dummies = procedure_dummies_by_name.get(callee, set())
                if not procedure_dummies:
                    continue
                for actual in modified_call_actuals(actuals, procedure_dummies):
                    actual_match = re.fullmatch(r"\s*([a-z][a-z0-9_]*)\s*", actual, re.IGNORECASE)
                    if actual_match:
                        actual_name = actual_match.group(1).lower()
                        if actual_name in known_procedure_names:
                            used_as_actual.add(actual_name)
    return used_as_actual


def analyze_lines(
    lines: List[str],
    external_name_status: Optional[Dict[str, bool]] = None,
    modified_dummies_by_name: Optional[Dict[str, Set[Tuple[int, str]]]] = None,
    generic_interfaces: Optional[Dict[str, Set[str]]] = None,
    procedure_bindings: Optional[Dict[str, Set[str]]] = None,
    impure_deferred_bindings: Optional[Set[str]] = None,
    imported_names: Optional[Set[str]] = None,
    strict_unknown_calls: bool = False,
    assumed_pure_selectors: Optional[Set[str]] = None,
) -> AnalysisResult:
    """Analyze procedures and classify likely pure candidates or rejections.

    ``assumed_pure_selectors`` supports call-graph fixed-point analysis. A
    procedure in that set is provisionally treated as pure when resolving
    calls, but it is still analyzed and returned as a candidate only if it
    has no direct or propagated purity blockers.
    """
    procs = parse_procedures(lines)
    if not procs:
        return AnalysisResult(procs, [], [])

    assumed_pure = {selector.lower() for selector in (assumed_pure_selectors or set())}

    def is_known_pure(proc: Procedure) -> bool:
        return proc.is_pure_or_elemental or proc.selector.lower() in assumed_pure

    by_name: Dict[str, List[Procedure]] = {}
    for p in procs:
        by_name.setdefault(p.name.lower(), []).append(p)
    has_nonpure_name = {
        name for name, plist in by_name.items() if any(not is_known_pure(p) for p in plist)
    }
    external_nonpure = {
        name for name, is_pure in (external_name_status or {}).items() if not is_pure
    }
    external_status = external_name_status or {}
    generics = generic_interfaces or {}
    bindings = procedure_bindings or {}
    deferred_nonpure = impure_deferred_bindings or set()
    imported = imported_names or set()
    modified_by_name = modified_dummies_by_name or {}
    generic_nonpure_names = {
        gname
        for gname, targets in generics.items()
        if any(t in has_nonpure_name or t in external_nonpure for t in targets)
    }
    binding_nonpure_names = {
        name
        for name, targets in bindings.items()
        if any(target in has_nonpure_name or target in external_nonpure for target in targets)
    }
    ref_nonpure_names = has_nonpure_name | external_nonpure | generic_nonpure_names | binding_nonpure_names

    candidates: List[Procedure] = []
    rejected: List[Tuple[Procedure, List[str]]] = []

    for proc in procs:
        if proc.is_pure_or_elemental:
            continue

        reasons: List[str] = []
        if "impure" in proc.attrs:
            reasons.append("procedure is explicitly declared IMPURE")
        local_names: Set[str] = set(proc.dummy_names)
        if proc.result_name:
            local_names.add(proc.result_name.lower())
        dummy_with_intent_or_value: Set[str] = set()
        dummy_intent: Dict[str, str] = {}
        character_names: Set[str] = set()
        external_proc_names: Set[str] = set()

        children = [p for p in procs if p.parent and p.parent.lower() == proc.name.lower()]
        nonpure_children = [c.name for c in children if not is_known_pure(c)]
        if nonpure_children:
            reasons.append(f"contains non-pure internal procedures: {', '.join(nonpure_children)}")

        for ln, code in proc.body:
            low = code.lower()
            if not low.strip():
                continue
            action = executable_action(low)

            if TYPE_DECL_RE.match(low):
                if re.search(r"\bsave\b", low):
                    reasons.append(f"line {ln}: SAVE attribute in declaration")
                if declaration_has_saved_initialization(low):
                    reasons.append(f"line {ln}: initialized local variable has implicit SAVE")
                declared = parse_declared_names_any(low)
                if declared:
                    local_names.update(declared)
                    if re.search(r"\bexternal\b", low):
                        external_proc_names.update(declared)
                    if low.strip().startswith("character"):
                        character_names.update(declared)
                    intent_attr = parse_decl_intent(low)
                    has_value_attr = decl_has_value_attr(low, declared)
                    if intent_attr or has_value_attr:
                        for d in proc.dummy_names:
                            if d in declared:
                                if intent_attr:
                                    dummy_intent[d] = intent_attr
                                elif has_value_attr:
                                    dummy_intent[d] = "value"
                    if "intent(" in low or has_value_attr:
                        for d in proc.dummy_names:
                            if d in declared:
                                dummy_with_intent_or_value.add(d)

            if PROCEDURE_DECL_RE.match(low):
                reasons.append(
                    f"line {ln}: procedure dummy/pointer declaration (conservatively treated as non-pure candidate)"
                )

            if SAVE_STMT_RE.match(low):
                reasons.append(f"line {ln}: SAVE statement")
            if DATA_STMT_RE.match(low):
                reasons.append(f"line {ln}: DATA statement")

            if PRINT_RE.match(action):
                reasons.append(f"line {ln}: PRINT statement")
            if FILE_IO_RE.match(action):
                reasons.append(f"line {ln}: file I/O statement")
            direct_read = READ_RE.match(action)
            direct_write = WRITE_RE.match(action)
            inline_io = INLINE_IO_RE.search(low)
            if direct_read or direct_write or inline_io:
                if direct_write:
                    io_kw = "write"
                    io_statement = action
                elif direct_read:
                    io_kw = "read"
                    io_statement = action
                else:
                    assert inline_io is not None
                    io_kw = inline_io.group(1).lower()
                    io_statement = low[inline_io.start(1):]
                control = extract_io_control_list(io_statement, io_kw)
                if control is None:
                    reasons.append(f"line {ln}: malformed {io_kw.upper()} control list")
                else:
                    unit_expr = io_unit_expr_from_control(control)
                    if unit_expr is None:
                        reasons.append(
                            f"line {ln}: {io_kw.upper()} without clear internal unit (conservative block)"
                        )
                    else:
                        ue = unit_expr.strip()
                        if ue == "*" or re.match(r"^[+-]?\d+$", ue):
                            reasons.append(f"line {ln}: external {io_kw.upper()} unit")
                        elif re.match(r"^['\"]", ue):
                            if io_kw == "write":
                                reasons.append(f"line {ln}: WRITE to literal internal file is not allowed")
                        else:
                            unit_base = base_identifier(ue)
                            if unit_base is None or unit_base not in character_names:
                                reasons.append(
                                    f"line {ln}: {io_kw.upper()} appears external/unknown (unit '{ue}')"
                                )
                            elif io_kw == "write":
                                if unit_base in proc.dummy_names:
                                    if proc.kind == "function":
                                        reasons.append(
                                            f"line {ln}: internal WRITE target '{unit_base}' is dummy in function"
                                        )
                                    else:
                                        dint = dummy_intent.get(unit_base, "")
                                        if dint not in {"out", "inout", "value"}:
                                            reasons.append(
                                                f"line {ln}: internal WRITE target dummy '{unit_base}' "
                                                "needs INTENT(OUT/INOUT) or VALUE"
                                            )
                                elif unit_base not in local_names:
                                    reasons.append(
                                        f"line {ln}: internal WRITE target '{unit_base}' is non-local"
                                    )
            stop_check = ERROR_STOP_RE.sub("", low)
            if STOP_RE.search(stop_check):
                reasons.append(f"line {ln}: STOP statement")

            for intr in IMPURE_INTRINSICS:
                if re.search(rf"\b(?:call\s+)?{re.escape(intr)}\b", low):
                    reasons.append(f"line {ln}: impure intrinsic '{intr}'")

            for m in CALL_RE.finditer(low):
                callee = m.group(1).lower()
                generic_targets = generics.get(callee, set())
                if callee in has_nonpure_name:
                    reasons.append(f"line {ln}: calls non-pure procedure '{callee}'")
                elif callee in external_nonpure:
                    reasons.append(f"line {ln}: calls known non-pure external procedure '{callee}'")
                elif generic_targets:
                    nonpure_targets = [t for t in generic_targets if t in ref_nonpure_names]
                    if nonpure_targets:
                        reasons.append(
                            f"line {ln}: generic '{callee}' resolves to non-pure procedure(s): "
                            + ", ".join(sorted(nonpure_targets))
                        )
                    elif strict_unknown_calls:
                        unknown_targets = [
                            t for t in generic_targets if t not in by_name and t not in external_status
                        ]
                        if unknown_targets:
                            reasons.append(
                                f"line {ln}: generic '{callee}' has unknown procedure(s): "
                                + ", ".join(sorted(unknown_targets))
                            )
                elif strict_unknown_calls and callee not in by_name and callee not in external_status:
                    reasons.append(f"line {ln}: call to unknown external procedure '{callee}'")

                modified_dummies = set(modified_by_name.get(callee, set()))
                for target in generic_targets:
                    modified_dummies.update(modified_by_name.get(target, set()))
                if modified_dummies:
                    actuals = call_actual_arguments(low, m)
                    for actual in modified_call_actuals(actuals, modified_dummies):
                        actual_base = base_identifier(actual)
                        if actual_base and actual_base not in local_names:
                            reasons.append(
                                f"line {ln}: call to '{callee}' defines non-local actual "
                                f"'{actual_base}' through INTENT(OUT/INOUT)"
                            )

            for match in TYPE_BOUND_INVOCATION_RE.finditer(low):
                binding = match.group(1).lower()
                if binding in deferred_nonpure:
                    reasons.append(
                        f"line {ln}: invokes deferred type-bound procedure '{binding}' "
                        "whose interface is not PURE"
                    )

            m_assign = ASSIGN_RE.match(action)
            if m_assign:
                lhs_base = base_identifier(m_assign.group(1))
                if lhs_base and lhs_base not in local_names:
                    reasons.append(
                        f"line {ln}: assignment to non-local variable '{lhs_base}' (possible host/module state)"
                    )

            m_alloc = ALLOC_DEALLOC_RE.match(action)
            if m_alloc:
                inner = m_alloc.group(2)
                first_obj = inner.split(",", 1)[0].strip()
                obj_base = base_identifier(first_obj)
                if obj_base and obj_base not in local_names:
                    reasons.append(f"line {ln}: {m_alloc.group(1).lower()} of non-local variable '{obj_base}'")

            do_iterator = DO_ITERATOR_RE.match(action)
            if do_iterator and do_iterator.group(1).lower() not in local_names:
                reasons.append(f"line {ln}: DO iterator '{do_iterator.group(1).lower()}' is non-local")

            ids_on_line = line_identifiers(low)
            for callee in (ids_on_line & ref_nonpure_names):
                if callee == proc.name.lower():
                    continue
                if has_function_reference(low, callee):
                    reasons.append(f"line {ln}: references non-pure function '{callee}'")
            for callee in (ids_on_line & external_proc_names):
                if callee == proc.name.lower():
                    continue
                if has_function_reference(low, callee):
                    if external_status.get(callee, False):
                        continue
                    if callee in external_status:
                        reasons.append(f"line {ln}: references known non-pure EXTERNAL function '{callee}'")
                    else:
                        reasons.append(f"line {ln}: references EXTERNAL function '{callee}' (purity unknown)")
            for match in INVOCATION_RE.finditer(low):
                callee = match.group(1).lower()
                if callee not in imported:
                    continue
                if external_status.get(callee, False):
                    continue
                local_definitions = by_name.get(callee, [])
                if local_definitions and all(is_known_pure(item) for item in local_definitions):
                    continue
                alias_targets = bindings.get(callee, set()) | generics.get(callee, set())
                if alias_targets and all(external_status.get(name, False) for name in alias_targets):
                    continue
                reasons.append(f"line {ln}: invokes imported entity '{callee}' whose purity is unknown")

        if proc.kind == "subroutine":
            for d in sorted(proc.dummy_names):
                if d not in dummy_with_intent_or_value:
                    reasons.append(
                        f"dummy argument '{d}' lacks explicit INTENT/VALUE declaration (conservative pure check)"
                    )
        elif proc.kind == "function":
            for d in sorted(proc.dummy_names):
                dint = dummy_intent.get(d, "")
                if dint not in {"in", "value"}:
                    reasons.append(
                        f"dummy argument '{d}' lacks INTENT(IN)/VALUE declaration required for pure function"
                    )

        deduped: List[str] = []
        seen = set()
        for r in reasons:
            if r not in seen:
                deduped.append(r)
                seen.add(r)

        if deduped:
            rejected.append((proc, deduped))
        else:
            candidates.append(proc)

    return AnalysisResult(procs, candidates, rejected)


def split_code_comment(line: str) -> Tuple[str, str]:
    """Split a line into code and trailing comment segments."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "!" and not in_single and not in_double:
            return line[:i], line[i:]
    return line, ""


def add_pure_to_declaration(line: str) -> Tuple[str, bool]:
    """Insert PURE into a procedure declaration line when missing."""
    code, comment = split_code_comment(line)
    m = DECL_RE.match(code)
    if not m:
        return line, False
    preprefix = m.group("preprefix") or ""
    prefix = m.group("prefix") or ""
    lead = m.group("lead") or ""
    attrs = {a.lower() for a in f"{preprefix} {prefix}".split()}
    if "pure" in attrs or "elemental" in attrs or "impure" in attrs:
        return line, False
    indent = m.group(1)
    kind = m.group("kind")
    tail = code[m.end("kind"):]
    new_code = f"{indent}pure {preprefix}{lead}{prefix}{kind}{tail}"
    return f"{new_code}{comment}", True


def elemental_shape_compatible(proc: Procedure) -> bool:
    """Check the scalar dummy/result constraints ELEMENTAL requires.

    Every dummy argument must be a plain scalar (declared, with no array/
    DIMENSION/POINTER/ALLOCATABLE attribute), a function's result must
    also be scalar, and the procedure itself must not take a dummy
    PROCEDURE argument (elemental subprograms cannot have one, per the
    Fortran standard).
    """
    if procedure_dummy_procedures(proc):
        return False
    declared: Set[str] = set()
    nonscalar: Set[str] = set()
    result_name = (proc.result_name or proc.name).lower()
    pointer_or_allocatable: Set[str] = set()
    for _, code in proc.body:
        low = code.lower()
        if not TYPE_DECL_RE.match(low):
            continue
        declared_here = parse_declared_names_any(low)
        declared.update(declared_here)
        if "allocatable" in low or re.search(r"\bpointer\b", low):
            pointer_or_allocatable.update(declared_here)
        line_has_dimension = "dimension" in low
        for name, has_entity_paren in parse_declared_entities(low):
            if line_has_dimension or has_entity_paren:
                nonscalar.add(name)

    for d in proc.dummy_names:
        if d not in declared or d in nonscalar or d in pointer_or_allocatable:
            return False
    if proc.kind == "function":
        if result_name in nonscalar:
            return False
        if result_name in pointer_or_allocatable:
            return False
    return True


def add_elemental_to_declaration(line: str) -> Tuple[str, bool]:
    """Insert ELEMENTAL into an already-PURE procedure declaration line."""
    code, comment = split_code_comment(line)
    m = DECL_RE.match(code)
    if not m:
        return line, False
    preprefix = m.group("preprefix") or ""
    prefix = m.group("prefix") or ""
    lead = m.group("lead") or ""
    pre_attrs = [a for a in preprefix.split() if a]
    post_attrs = [a for a in prefix.split() if a]
    attrs_l = [a.lower() for a in pre_attrs + post_attrs]
    if "elemental" in attrs_l or "impure" in attrs_l or "pure" not in attrs_l:
        return line, False
    filtered_pre = [a for a in pre_attrs if a.lower() != "pure"]
    filtered_post = [a for a in post_attrs if a.lower() != "pure"]
    indent = m.group(1)
    kind = m.group("kind")
    tail = code[m.end("kind"):]
    pre_text = " ".join(["pure", "elemental"] + filtered_pre) + " "
    post_text = (" ".join(filtered_post) + " ") if filtered_post else ""
    new_code = f"{indent}{pre_text}{lead}{post_text}{kind}{tail}"
    return f"{new_code}{comment}", True


def apply_decl_edit_at_or_continuation(lines: List[str], idx: int, editor) -> bool:
    """Apply declaration editor at idx, or on a continued signature line."""
    if idx < 0 or idx >= len(lines):
        return False

    new_line, did_change = editor(lines[idx])
    if did_change:
        lines[idx] = new_line
        return True

    code0, _comment0 = split_code_comment(lines[idx])
    if not code0.rstrip().endswith("&"):
        return False

    j = idx + 1
    while j < len(lines):
        raw = lines[j]
        stripped = raw.strip()
        if not stripped or stripped.startswith("!"):
            j += 1
            continue
        codej, commentj = split_code_comment(raw)
        m = re.match(r"^(\s*&?\s*)(.*)$", codej)
        if not m:
            return False
        lead = m.group(1)
        core = m.group(2)
        edited_core, did_change_core = editor(core)
        if not did_change_core:
            return False
        lines[j] = f"{lead}{edited_core}{commentj}"
        return True
    return False


_GENERIC_INTERFACE_START_RE = re.compile(r"^\s*interface\s+([a-z][a-z0-9_]*)\s*$", re.IGNORECASE)
_GENERIC_INTERFACE_END_RE = re.compile(r"^\s*end\s+interface\b", re.IGNORECASE)
_MODULE_PROCEDURE_LINE_RE = re.compile(r"^\s*module\s+procedure\s*(?:::)?\s*(.+)$", re.IGNORECASE)


def _parse_generic_interface_targets(lines: List[str]) -> Dict[str, Set[str]]:
    """Map a named `interface NAME ... module procedure X, Y ... end
    interface` block's generic NAME to its underlying concrete procedure
    names (e.g. python.f90's `interface optval` -> {optval_int,
    optval_real, optval_logical, optval_char}).

    A generic name declared this way (as opposed to a type-bound
    `generic ::` binding, which parse_type_bound_bindings already covers)
    is what generated code actually calls -- `optval(...)`, never
    `optval_real(...)` directly -- so its OWN purity has to be derived
    from ALL of its constituent implementations, not looked up as if it
    were itself a concrete procedure with a body (parse_procedures never
    finds one, since there isn't one).
    """
    targets: Dict[str, Set[str]] = {}
    current: Optional[str] = None
    for _lineno, stmt in iter_fortran_statements(lines):
        low = stmt.strip()
        m_start = _GENERIC_INTERFACE_START_RE.match(low)
        if m_start:
            current = m_start.group(1).lower()
            targets.setdefault(current, set())
            continue
        if _GENERIC_INTERFACE_END_RE.match(low):
            current = None
            continue
        if current is None:
            continue
        m_mp = _MODULE_PROCEDURE_LINE_RE.match(low)
        if m_mp:
            for item in m_mp.group(1).split(","):
                nm = item.strip().lower()
                if re.fullmatch(r"[a-z][a-z0-9_]*", nm):
                    targets[current].add(nm)
    return targets


def collect_dp_returning_function_names(lines: List[str]) -> Set[str]:
    """Return the lowercase names of every scalar real(kind=dp)-returning
    FUNCTION defined in `lines` (any nesting level).

    Two signature shapes this project's own codegen and its vendored
    runtime helpers both use:
    - inline: `real(kind=dp) function NAME(...) [result(v)]` -- the type
      is right there on the signature line, nothing else to check.
    - `function NAME(...) result(v)` (no inline type) -- v's own type
      comes from a separate declaration inside the body; only counted
      when that declaration is a plain SCALAR `real(kind=dp)` (no array
      shape -- kept narrow, since callers of this registry use it to
      strip a scalar `real(FUNC(...), kind=dp)` cast).
    """
    stmt_by_lineno = dict(iter_fortran_statements(lines))
    inline_re = re.compile(
        r"^\s*(?:(?:pure|elemental|impure|recursive|module)\s+)*real\s*\(\s*kind\s*=\s*dp\s*\)\s+function\b",
        re.IGNORECASE,
    )
    decl_re = re.compile(r"^\s*real\s*\(\s*kind\s*=\s*dp\s*\)(?:\s*,\s*[a-z_]+)*\s*::\s*(.+)$", re.IGNORECASE)
    names: Set[str] = set()
    for proc in parse_procedures(lines):
        if proc.kind != "function" or proc.result_name is None:
            continue
        sig = stmt_by_lineno.get(proc.start, "")
        if inline_re.match(sig):
            names.add(proc.name.lower())
            continue
        for _, stmt in proc.body:
            dm = decl_re.match(stmt)
            if not dm:
                continue
            for ent in split_top_level_commas(dm.group(1)):
                base = ent.split("=", 1)[0].strip()
                if "(" in base:
                    continue
                if base.lower() == proc.result_name:
                    names.add(proc.name.lower())
                    break
    return names


def load_external_purity_registry(runtime_helper_paths: Iterable[Path]) -> Dict[str, bool]:
    """Build a name->is_pure registry from vendored runtime .f90 helper files.

    Reads each file's OWN pure/non-pure declarations directly -- ground
    truth, not a hand-maintained guess -- and collects top-level (non-
    internal) procedure names. A name is only "pure" here when EVERY
    definition of it across the given files is pure/elemental; anything
    else (including a name this scan never saw at all) is left absent, and
    analyze_lines treats an absent external name as "unknown" rather than
    "known impure" unless strict_unknown_calls is requested.

    A generic interface name (see _parse_generic_interface_targets) is
    registered too, as pure only when EVERY one of its constituent
    `module procedure` targets is -- without this, a call to a generic
    like python_mod's `optval(...)` (never itself a concrete procedure
    parse_procedures can find a body for) was always "purity unknown"
    even when all four of its actual implementations (optval_int/_real/
    _logical/_char) are pure, blocking `pure` on every caller that uses a
    Python default-argument value at all.
    """
    definitions: Dict[str, List[bool]] = {}
    generic_targets: Dict[str, Set[str]] = {}
    for path in runtime_helper_paths:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        lines = text.splitlines()
        for proc in parse_procedures(lines):
            if proc.parent is not None:
                continue
            definitions.setdefault(proc.name.lower(), []).append(proc.is_pure_or_elemental)
        for gname, targets in _parse_generic_interface_targets(lines).items():
            generic_targets.setdefault(gname, set()).update(targets)
    registry = {name: all(statuses) for name, statuses in definitions.items()}
    for gname, targets in generic_targets.items():
        if gname in registry:
            continue
        if targets and all(registry.get(t) is True for t in targets):
            registry[gname] = True
    return registry


def mark_pure_where_provable(
    f90_lines: List[str],
    external_name_status: Optional[Dict[str, bool]] = None,
    strict_unknown_calls: bool = True,
) -> List[str]:
    """Promote generated procedures to PURE wherever the emitted Fortran
    itself proves it's safe, iterating to a fixed point over the file's own
    call graph so unit A calling already-confirmed-pure unit B propagates
    correctly (mirrors the sibling project's multi-file
    analyze_source_files_fixed_point, specialized to a single in-memory
    file since every OTHER linked file here is a fixed, vendored helper
    whose purity is read via external_name_status instead of re-derived).

    Only ever ADDS a `pure ` prefix to a procedure not already marked
    pure/elemental/impure -- never touches one already decided either way,
    so this is safe to layer on top of an existing, independent purity
    decision (xp2f.py's own Python-AST-based pass runs first; this is a
    second chance for whatever it missed, not a replacement).
    """
    procedure_bindings = parse_type_bound_bindings(f90_lines)
    impure_deferred_bindings = parse_impure_deferred_type_bound_bindings(f90_lines)
    use_renames = parse_use_renames(f90_lines)
    use_only_names = parse_use_only_names(f90_lines)
    file_bindings = {name: set(targets) for name, targets in procedure_bindings.items()}
    for name, targets in use_renames.items():
        file_bindings.setdefault(name, set()).update(targets)

    parsed = parse_procedures(f90_lines)
    module_pointer_names = parse_module_procedure_pointers(f90_lines, parsed)
    external_status = dict(external_name_status or {})
    for name in module_pointer_names:
        external_status[name] = False

    modified_dummies_by_name: Dict[str, Set[Tuple[int, str]]] = {}
    for proc in parsed:
        modified_dummies_by_name.setdefault(proc.name.lower(), set()).update(
            procedure_modified_dummies(proc)
        )

    assumed: Set[str] = {
        proc.selector.lower() for proc in parsed if not proc.is_pure_or_elemental and "impure" not in proc.attrs
    }

    result: Optional[AnalysisResult] = None
    for _ in range(max(1, len(parsed)) + 1):
        result = analyze_lines(
            f90_lines,
            external_name_status=external_status,
            modified_dummies_by_name=modified_dummies_by_name,
            procedure_bindings=file_bindings,
            impure_deferred_bindings=impure_deferred_bindings,
            imported_names=use_only_names,
            strict_unknown_calls=strict_unknown_calls,
            assumed_pure_selectors=assumed,
        )
        viable = {proc.selector.lower() for proc in result.candidates}
        next_assumed = assumed & viable
        if next_assumed == assumed:
            break
        assumed = next_assumed

    if result is None:
        return f90_lines

    updated = list(f90_lines)
    for proc in result.candidates:
        idx = proc.start - 1
        apply_decl_edit_at_or_continuation(updated, idx, add_pure_to_declaration)
    return updated


def mark_elemental_where_provable(f90_lines: List[str]) -> List[str]:
    """Promote an already-PURE procedure to PURE ELEMENTAL wherever the
    emitted Fortran proves it's safe: every dummy argument (and the
    result, for a function) is a plain scalar, the procedure takes no
    dummy PROCEDURE argument, and the procedure is never itself passed as
    an actual argument anywhere in this file (an elemental procedure
    cannot be supplied where a procedure dummy is expected).

    Intended to run AFTER mark_pure_where_provable, once purity is
    already resolved in the text -- unlike that function, this one is
    opt-in (see xp2f.py's --elemental flag): ELEMENTAL is not a pure
    upside the way PURE is. It carries a real usage constraint (the
    callback restriction above) and only pays off if a caller could
    actually exploit automatic array broadcasting, so it's offered as a
    choice rather than always applied.
    """
    parsed = parse_procedures(f90_lines)
    procedure_actual_names = procedures_used_as_actual_arguments({"self": parsed})

    updated = list(f90_lines)
    for proc in parsed:
        if proc.kind not in {"function", "subroutine"}:
            continue
        if not proc.is_pure_or_elemental or "elemental" in proc.attrs:
            continue
        if not proc.dummy_names:
            continue
        if proc.name.lower() in procedure_actual_names:
            continue
        if not elemental_shape_compatible(proc):
            continue
        idx = proc.start - 1
        apply_decl_edit_at_or_continuation(updated, idx, add_elemental_to_declaration)
    return updated
