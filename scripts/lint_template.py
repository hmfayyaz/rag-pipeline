#!/usr/bin/env python3
"""Architectural consistency checker for the cookiecutter template.

Detects patterns that compile but silently break at runtime, produce
wrong output, or violate the repo's architecture rules.

Exit code: 0 = clean, 1 = violations found.

Usage:
    python scripts/lint_template.py [--fix-hints]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).parent.parent / "template" / "{{cookiecutter.project_slug}}"
BACKEND_ROOT = TEMPLATE_ROOT / "backend" / "app"
FRONTEND_ROOT = TEMPLATE_ROOT / "frontend" / "src"

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    check_id: str
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    path: str
    line: int
    message: str
    hint: str = ""

    def __str__(self) -> str:
        loc = f"{self.path}:{self.line}"
        badge = f"[{self.severity}]"
        text = f"  {badge:<12} {self.check_id}  {loc}\n             {self.message}"
        if self.hint:
            text += f"\n             hint: {self.hint}"
        return text


@dataclass
class CheckResult:
    check_id: str
    description: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_jinja(text: str) -> str:
    """Remove Jinja2 block tags but keep line numbers intact."""
    text = re.sub(r"\{%-?\s*(if|elif|else|endif|for|endfor|raw|endraw)[^%]*%\}", "", text)
    return text


def _iter_py(root: Path):
    if root.exists():
        yield from root.rglob("*.py")


def _iter_tsx(root: Path):
    if root.exists():
        yield from root.rglob("*.tsx")
        yield from root.rglob("*.ts")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(TEMPLATE_ROOT.parent.parent))
    except ValueError:
        return str(path)


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


# ---------------------------------------------------------------------------
# B001 — db.commit() in repository files
# ---------------------------------------------------------------------------


def check_b001_db_commit() -> CheckResult:
    result = CheckResult("B001", "db.commit() in repository files (use db.flush() instead)")
    pattern = re.compile(r"\bdb\.commit\s*\(\s*\)")
    for path in _iter_py(BACKEND_ROOT / "repositories"):
        for lineno, line in enumerate(_read_lines(path), 1):
            if pattern.search(line):
                result.violations.append(
                    Violation(
                        "B001",
                        "HIGH",
                        _rel(path),
                        lineno,
                        "db.commit() found in repository",
                        "Session auto-commits via get_db_session. Use db.flush() + db.refresh().",
                    )
                )
    return result


# ---------------------------------------------------------------------------
# B002 — In-function imports that should be at module level
# ---------------------------------------------------------------------------

# Matches indented imports that have no circular-import justification
_B002_RE = re.compile(
    r"^\s{4,}(?:import\s+(asyncio|os|sys|threading|subprocess)\b"
    r"|from\s+app\.core\.config\s+import\s+settings)"
)


def check_b002_inline_imports() -> CheckResult:
    result = CheckResult(
        "B002",
        "In-function imports (asyncio/os/sys/settings) in repos/services — should be module-level",
    )
    dirs = [BACKEND_ROOT / "repositories", BACKEND_ROOT / "services"]

    for search_dir in dirs:
        for path in _iter_py(search_dir):
            for lineno, line in enumerate(_read_lines(path), 1):
                if _B002_RE.match(line):
                    result.violations.append(
                        Violation(
                            "B002",
                            "MEDIUM",
                            _rel(path),
                            lineno,
                            f"In-function import: {line.strip()}",
                            "Move to module top-level; no circular-import risk for stdlib or settings.",
                        )
                    )
    return result


# ---------------------------------------------------------------------------
# B003 — asyncio.run() outside tasks/ and commands/
# ---------------------------------------------------------------------------

_B003_ALLOWED_DIRS = {
    "worker",
    "tasks",
    "commands",
    "agents",
}


def check_b003_asyncio_run() -> CheckResult:
    result = CheckResult(
        "B003", "asyncio.run() outside tasks/commands — raises RuntimeError inside FastAPI"
    )
    pattern = re.compile(r"\basyncio\.run\s*\(")
    for path in _iter_py(BACKEND_ROOT):
        parts = set(path.relative_to(BACKEND_ROOT).parts)
        if parts & _B003_ALLOWED_DIRS:
            continue
        for lineno, line in enumerate(_read_lines(path), 1):
            if pattern.search(line):
                result.violations.append(
                    Violation(
                        "B003",
                        "CRITICAL",
                        _rel(path),
                        lineno,
                        "asyncio.run() called — fails with RuntimeError inside FastAPI event loop",
                        "Make the function async and use await, or run in a ThreadPoolExecutor.",
                    )
                )
    return result


# ---------------------------------------------------------------------------
# T001 — Unbalanced Jinja2 if/endif blocks
# ---------------------------------------------------------------------------


def check_t001_jinja_balance() -> CheckResult:
    result = CheckResult("T001", "Unbalanced Jinja2 {%- if %} / {%- endif %} blocks")
    if_re = re.compile(r"\{%-?\s*if\b")
    endif_re = re.compile(r"\{%-?\s*endif\b")
    raw_re = re.compile(r"\{%-?\s*raw\b")
    endraw_re = re.compile(r"\{%-?\s*endraw\b")

    for path in TEMPLATE_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix in (".pyc", ".png", ".jpg", ".ico", ".woff", ".woff2", ".ttf"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        depth = 0
        raw_depth = 0
        for _lineno, line in enumerate(text.splitlines(), 1):
            if endraw_re.search(line):
                raw_depth -= 1
            elif raw_re.search(line):
                raw_depth += 1
                continue
            if raw_depth > 0:
                continue
            depth += len(if_re.findall(line))
            depth -= len(endif_re.findall(line))

        if depth != 0:
            result.violations.append(
                Violation(
                    "T001",
                    "HIGH",
                    _rel(path),
                    0,
                    f"Unbalanced if/endif: net depth = {depth:+d}",
                )
            )
    return result


# ---------------------------------------------------------------------------
# T002 — TSX files with {{ }} double-brace conflicts (not cookiecutter vars)
# ---------------------------------------------------------------------------

_COOKIECUTTER_VAR_RE = re.compile(r"\{\{-?\s*cookiecutter\.")
_DOUBLE_BRACE_RE = re.compile(r"\{\{")
_RAW_BLOCK_RE = re.compile(r"\{%-?\s*raw\b.*?\{%-?\s*endraw\b", re.DOTALL)
_JINJA_IF_RE = re.compile(r"\{%-?\s*if\b")


def check_t002_tsx_raw() -> CheckResult:
    result = CheckResult(
        "T002",
        "TSX files with {{ }} JSX patterns that Jinja2 will misinterpret",
    )

    for path in (FRONTEND_ROOT / "app").rglob("*.tsx"):
        lines = _read_lines(path)
        full_text = "\n".join(lines)

        if not _JINJA_IF_RE.search(full_text):
            continue

        # Remove already-protected raw blocks and cookiecutter var uses
        stripped = _RAW_BLOCK_RE.sub("", full_text)
        stripped = _COOKIECUTTER_VAR_RE.sub("", stripped)

        # Any remaining {{ is ambiguous JSX that Jinja2 will process
        conflict_lines = []
        for lineno, line in enumerate(stripped.splitlines(), 1):
            if _DOUBLE_BRACE_RE.search(line):
                conflict_lines.append(lineno)

        if conflict_lines:
            result.violations.append(
                Violation(
                    "T002",
                    "HIGH",
                    _rel(path),
                    conflict_lines[0],
                    f"{{ }}{{ }} JSX double-brace at lines {conflict_lines[:3]} will be parsed as Jinja2",
                    "Wrap the JSX body in {%% raw %%}...{%% endraw %%}.",
                )
            )
    return result


# ---------------------------------------------------------------------------
# F001 — Direct fetch() in "use client" components
# ---------------------------------------------------------------------------


def check_f001_direct_fetch() -> CheckResult:
    result = CheckResult(
        "F001", 'Direct fetch("/api/v1/...") in "use client" components (use apiClient instead)'
    )
    use_client_re = re.compile(r'"use client"')
    # Only flag fetch calls to the backend API (/api/v1/), not Next.js API routes (/api/auth/, etc.)
    fetch_backend_re = re.compile(r'\bfetch\s*\(\s*["\`]/api/v1/')

    for path in (FRONTEND_ROOT / "app").rglob("*.tsx"):
        lines = _read_lines(path)
        full_text = "\n".join(lines)
        if not use_client_re.search(full_text):
            continue
        for lineno, line in enumerate(lines, 1):
            if fetch_backend_re.search(line) and "// ok-direct-fetch" not in line:
                result.violations.append(
                    Violation(
                        "F001",
                        "MEDIUM",
                        _rel(path),
                        lineno,
                        f"Direct fetch() to backend API: {line.strip()[:80]}",
                        "Use apiClient.get/post/patch/delete from lib/api-client for consistent error handling.",
                    )
                )
    return result


# ---------------------------------------------------------------------------
# F002 — Hook files not exported from hooks/index.ts
# ---------------------------------------------------------------------------


def check_f002_hook_exports() -> CheckResult:
    result = CheckResult("F002", "Hook files missing re-export from hooks/index.ts")
    hooks_dir = FRONTEND_ROOT / "hooks"
    index_path = hooks_dir / "index.ts"
    if not hooks_dir.exists() or not index_path.exists():
        return result

    try:
        index_text = index_path.read_text(encoding="utf-8")
    except OSError:
        return result

    for path in hooks_dir.glob("use-*.ts"):
        stem = path.stem
        if stem not in index_text:
            result.violations.append(
                Violation(
                    "F002",
                    "LOW",
                    _rel(path),
                    0,
                    f"{path.name} not re-exported from hooks/index.ts",
                    f'Add: export * from "./{stem}";',
                )
            )
    return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

CHECKS = [
    check_b001_db_commit,
    check_b002_inline_imports,
    check_b003_asyncio_run,
    check_t001_jinja_balance,
    check_t002_tsx_raw,
    check_f001_direct_fetch,
    check_f002_hook_exports,
]

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def run(show_passed: bool = False) -> int:
    results: list[CheckResult] = []
    for check_fn in CHECKS:
        results.append(check_fn())

    total_violations = sum(len(r.violations) for r in results)
    counts: dict[str, int] = defaultdict(int)

    for r in results:
        for v in r.violations:
            counts[v.severity] += 1

    print(f"\n{'=' * 70}")
    print("  Template Architecture Lint")
    print(f"{'=' * 70}\n")

    for r in results:
        status = "PASS" if r.passed else f"FAIL ({len(r.violations)})"
        icon = "✓" if r.passed else "✗"
        print(f"  {icon} [{r.check_id}] {r.description:<55} {status}")
        if not r.passed:
            violations_sorted = sorted(
                r.violations, key=lambda v: SEVERITY_ORDER.get(v.severity, 9)
            )
            for v in violations_sorted:
                print(str(v))
        elif show_passed:
            print("       (no violations)")

    print(f"\n{'=' * 70}")
    if total_violations == 0:
        print("  All checks passed.\n")
        return 0
    else:
        severity_summary = "  " + "  ".join(
            f"{k}: {counts[k]}" for k in ["CRITICAL", "HIGH", "MEDIUM", "LOW"] if counts[k]
        )
        print(f"  {total_violations} violation(s) found.\n{severity_summary}\n")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show-passed", action="store_true", help="Print passing checks too")
    args = parser.parse_args()
    sys.exit(run(show_passed=args.show_passed))


if __name__ == "__main__":
    main()
