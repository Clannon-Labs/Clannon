#!/usr/bin/env python3
"""
backend/scripts/check_invariants.py

Hermetic grep-based invariant audit for the Clannon backend.

Runs the same checks as the /invariant-check skill and prints a per-invariant
PASS/FAIL/WARN table.  Stand-in for the Semgrep CI gate described in issue #15;
once that gate is merged, this script stays as a fast local pre-commit check.

Usage (from repo root):
    python backend/scripts/check_invariants.py

    # scope to only the files changed vs main (faster pre-commit sweep):
    python backend/scripts/check_invariants.py --changed-only

Exit code:
    0   all checks PASS or WARN
    1   one or more checks FAIL
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file so the script is location-independent)
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPT_DIR.parent.parent          # .../Clannon
BACKEND_ROOT = _SCRIPT_DIR.parent              # .../Clannon/backend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXCLUDE_DIRS = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
# Exclude this script and its test file — both contain the check patterns as
# string literals (not actual imports) and would produce false positives.
_SELF = Path(__file__).resolve()
_EXCLUDE_FILES: frozenset[Path] = frozenset([
    _SELF,
    _SELF.parent.parent / "tests" / "test_check_invariants.py",
])

# Files whose internal-import hits are accepted by the maintainer as intentional.
# New hits outside this list still FAIL; waived hits are printed as 'waived' so
# nothing is silently excused.
_MEMORY_INTERNALS_ALLOWLIST: dict[Path, str] = {
    BACKEND_ROOT / "core" / "warmup.py": (
        "startup warm path / ops-healthcheck concern, not a memory query; "
        "MemoryPort exposes no warm() surface so a direct internal import is intentional"
    ),
    BACKEND_ROOT / "api" / "_health.py": (
        "readiness probe / ops-healthcheck concern, not a memory query — same "
        "class as the warmup.py waiver; it calls store.healthcheck(), never a "
        "scoped read or write"
    ),
    BACKEND_ROOT / "scripts" / "decision_memory_demo.py": (
        "demo script patches the embeddings/store module seams for hermetic demo "
        "mode (the same seams tests patch); its real memory traffic goes through "
        "the Manager door"
    ),
    BACKEND_ROOT / "scripts" / "persistent_memory_demo.py": (
        "demo script patches the embeddings/store module seams for hermetic demo "
        "mode (the same seams tests patch); its real memory traffic goes through "
        "the Manager door"
    ),
}


def _iter_py_files(root: Path, only: set[Path] | None = None) -> list[Path]:
    """Return sorted list of .py files under root, skipping excluded dirs."""
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in _EXCLUDE_DIRS for part in path.parts):
            continue
        if path in _EXCLUDE_FILES:
            continue
        if only is not None and path not in only:
            continue
        files.append(path)
    return files


def _read(path: Path) -> tuple[list[str], str]:
    """Return (lines, full_content). Lines are 1-indexed in results."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [], ""
    return text.splitlines(), text


def _grep(
    files: list[Path],
    pattern: str,
    *,
    flags: int = 0,
    exclude_pattern: str | None = None,
    excl_flags: int = re.IGNORECASE,
) -> list[tuple[Path, int, str]]:
    """
    Return (path, 1-based lineno, stripped line) for every line that matches
    pattern and does not match exclude_pattern.
    """
    rx = re.compile(pattern, flags)
    excl_rx = re.compile(exclude_pattern, excl_flags) if exclude_pattern else None
    hits: list[tuple[Path, int, str]] = []
    for path in files:
        lines, _ = _read(path)
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                if excl_rx and excl_rx.search(line):
                    continue
                hits.append((path, i, line.strip()))
    return hits


class Result(NamedTuple):
    label: str
    invariant_ref: str
    status: str       # "PASS" | "FAIL" | "WARN"
    hits: list[tuple[Path, int, str]]
    note: str = ""
    # Hits that matched the pattern but were accepted via an explicit allowlist.
    # Printed as 'waived: ...' so excused violations remain visible in CI output.
    waived: list[tuple[Path, int, str]] = []


_STATUS_COLOR = {"PASS": "\033[32m", "FAIL": "\033[31m", "WARN": "\033[33m"}
_RESET = "\033[0m"


def _colorize(status: str) -> str:
    if sys.stdout.isatty():
        return f"{_STATUS_COLOR.get(status, '')}{status}{_RESET}"
    return status


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _print_results(results: list[Result]) -> None:
    col_w = max(len(r.label) for r in results) + 2
    print()
    print(f"  {'CHECK':<{col_w}}  STATUS  HITS")
    print(f"  {'-' * col_w}  ------  ----")
    for r in results:
        print(f"  {r.label:<{col_w}}  {_colorize(r.status):<6}  {len(r.hits)}")
    print()
    for r in results:
        if r.hits or r.waived or r.note:
            print(f"── {r.label} ({r.invariant_ref}) ──")
            if r.note:
                print(f"   note: {r.note}")
            for path, lineno, line in r.hits:
                print(f"   {_rel(path)}:{lineno}  {line}")
            for path, lineno, line in r.waived:
                print(f"   waived: {_rel(path)}:{lineno}  {line}")
            print()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_pydantic_ai_confined(files: list[Path]) -> Result:
    """
    §III.12 — pydantic_ai import must be confined to core/llm.

    FAIL if any file outside backend/core/llm/ or backend/tests/ imports
    pydantic_ai.
    """
    core_llm = BACKEND_ROOT / "core" / "llm"
    tests_dir = BACKEND_ROOT / "tests"
    candidates = [
        f for f in files
        if not _is_under(f, core_llm) and not _is_under(f, tests_dir)
    ]
    hits = _grep(
        candidates,
        r"\bimport pydantic_ai\b|from pydantic_ai\b",
    )
    status = "FAIL" if hits else "PASS"
    return Result(
        label="pydantic_ai confined to core/llm",
        invariant_ref="§III.12",
        status=status,
        hits=hits,
        note="Any hit outside core/llm/ or tests/ is a hard violation.",
    )


def check_memory_internals_confined(files: list[Path]) -> Result:
    """
    §V.20 / §I.7 — memory internals (store, embeddings, writer) must not be
    imported outside core/memory.  All callers must go through MemoryPort.

    FAIL on any import of the internal submodules outside core/memory/ that is
    not covered by _MEMORY_INTERNALS_ALLOWLIST.

    backend/tests/ is excluded (same as check #1): test files intentionally
    import internals to exercise them; that is test-by-design, not a violation.

    Allowlisted paths are printed as 'waived' so nothing is silently excused.
    Any NEW hit outside the allowlist still fails.
    """
    core_memory = BACKEND_ROOT / "core" / "memory"
    tests_dir = BACKEND_ROOT / "tests"
    candidates = [
        f for f in files
        if not _is_under(f, core_memory) and not _is_under(f, tests_dir)
    ]
    all_hits = _grep(
        candidates,
        r"from core\.memory import (store|embeddings|writer)"
        r"|import core\.memory\.(store|embeddings|writer)",
    )

    fail_hits: list[tuple[Path, int, str]] = []
    waived_hits: list[tuple[Path, int, str]] = []
    for path, lineno, line in all_hits:
        if path in _MEMORY_INTERNALS_ALLOWLIST:
            reason = _MEMORY_INTERNALS_ALLOWLIST[path]
            waived_hits.append((path, lineno, f"{line}  [waived: {reason}]"))
        else:
            fail_hits.append((path, lineno, line))

    status = "FAIL" if fail_hits else "PASS"
    return Result(
        label="memory internals confined to core/memory",
        invariant_ref="§V.20 / §I.7",
        status=status,
        hits=fail_hits,
        waived=waived_hits,
        note=(
            "callers outside core/memory must use MemoryPort, not store/embeddings/writer; "
            "tests/ excluded (test-by-design); allowlisted startup paths printed as 'waived'"
        ),
    )


def check_foundation_dep_direction(files: list[Path]) -> Result:
    """
    §III dep direction — foundation must not import upward (core, security,
    registry, experts, tools, api, delivery).

    FAIL on any such import in the supplied files.  Caller must pre-filter to
    backend/foundation/ so the check stays hermetic (no BACKEND_ROOT dependency).
    """
    hits = _grep(
        files,
        r"^\s*(from|import)\s+(core|security|registry|experts|tools|api|delivery)\b",
    )
    status = "FAIL" if hits else "PASS"
    return Result(
        label="foundation imports nothing upward",
        invariant_ref="§III (dep direction)",
        status=status,
        hits=hits,
        note="foundation/ must only depend on stdlib and third-party packages.",
    )


def check_no_bare_set(files: list[Path]) -> Result:
    """
    §V.22 — Postgres tenant-scoping must use SET LOCAL inside a transaction,
    never a bare connection-level SET.

    Flag lines that look like session-level SET commands (SET role, SET
    search_path, SET var=...) but do NOT say SET LOCAL.  SQL DML clauses
    (UPDATE … SET col = val) are excluded by pattern.
    """
    candidates = [f for f in files if f.suffix == ".py"]
    # Match lines with a bare SET for tenant scope: SET role / SET search_path /
    # SET <word> = value — but NOT SET LOCAL, and not SQL DML (UPDATE/INSERT/CREATE/ALTER).
    hits_raw = _grep(
        candidates,
        r"(?i)\bSET\s+(?!LOCAL\b)(role|search_path|app\.\w+|session\.\w+|config\b)",
        flags=re.IGNORECASE,
        # Exclude obvious DML and comment lines.
        exclude_pattern=r"(?i)(UPDATE|INSERT|CREATE|ALTER|--|\#)",
    )
    status = "FAIL" if hits_raw else "PASS"
    return Result(
        label="SET LOCAL not bare connection SET",
        invariant_ref="§V.22",
        status=status,
        hits=hits_raw,
        note=(
            "tenant-scoping SQL must use SET LOCAL inside an explicit transaction "
            "(RLS enforcement); a bare SET leaks across connection pool reuse"
        ),
    )


def check_network_tools_ssrf_gate(files: list[Path]) -> Result:
    """
    §IV.17 — NETWORK-permission tools/experts that make direct HTTP calls must
    route them through validate_public_url (the SSRF gate).

    Caller should pass backend/tools/ and backend/experts/ files.

    FAIL if a file declares `permission = PermissionLevel.NETWORK`, imports an
    HTTP client (httpx / requests / aiohttp / urllib.request), and does NOT call
    validate_public_url.

    WARN if a file declares NETWORK permission but makes no direct HTTP calls
    (e.g. routes through core/llm or registered sub-tools) — review to confirm
    no hidden HTTP path.
    """
    HTTP_CLIENTS = re.compile(
        r"\b(import\s+httpx|import\s+requests|import\s+aiohttp"
        r"|from\s+urllib\s+import|import\s+urllib\.request)\b"
    )
    # Match only class/module-level declarations, not comparison expressions.
    NETWORK_DECL = re.compile(r"\bpermission\s*=\s*PermissionLevel\.NETWORK\b")
    SSRF_GATE = re.compile(r"validate_public_url")

    fail_hits: list[tuple[Path, int, str]] = []
    warn_hits: list[tuple[Path, int, str]] = []

    for path in files:
        _, content = _read(path)
        if not NETWORK_DECL.search(content):
            continue
        has_http_client = bool(HTTP_CLIENTS.search(content))
        has_gate = bool(SSRF_GATE.search(content))
        if has_http_client and not has_gate:
            fail_hits.append((path, 0, "PermissionLevel.NETWORK + HTTP client without validate_public_url"))
        elif not has_http_client and not has_gate:
            warn_hits.append((path, 0, "PermissionLevel.NETWORK but no HTTP client import — confirm no hidden HTTP path"))

    status = "FAIL" if fail_hits else ("WARN" if warn_hits else "PASS")
    return Result(
        label="NETWORK tools route through SSRF gate",
        invariant_ref="§IV.17",
        status=status,
        hits=fail_hits + warn_hits,
        note=(
            "FAILs have an HTTP client without the gate; "
            "WARNs use NETWORK permission but no direct HTTP client (e.g. routes via LLM or sub-tools)"
        ),
    )


def check_agent_run_confined_to_retry(files: list[Path]) -> Result:
    """
    No-bypass invariant (security review 2026-07-25) — `agent.run(` (the
    pydantic-ai SDK call) must be invoked only inside core/llm/retry.py. Every
    other layer routes through retry.run_agent instead (framework.py's
    run_structured, search.py's grounded search both do) so the shared
    transient-retry wrapper — and the budget-enforcement anchor once it lands —
    can never be skipped by a second call site.

    FAIL if any file outside backend/core/llm/retry.py or backend/tests/
    contains the literal `agent.run(`. tests/ is excluded (test-by-design —
    e.g. tests/llm_provider_failover.py discusses agent.run() in prose/asserts,
    not as a second real call site).
    """
    retry_module = BACKEND_ROOT / "core" / "llm" / "retry.py"
    tests_dir = BACKEND_ROOT / "tests"
    candidates = [
        f for f in files
        if f != retry_module and not _is_under(f, tests_dir)
    ]
    hits = _grep(candidates, r"\bagent\.run\(")
    status = "FAIL" if hits else "PASS"
    return Result(
        label="agent.run( confined to core/llm/retry.py",
        invariant_ref="no-bypass (retry/budget anchor, security review 2026-07-25)",
        status=status,
        hits=hits,
        note="a second agent.run( call site would skip the shared retry wrapper and the budget anchor.",
    )


def check_budget_keys_confined_to_core_budget(files: list[Path]) -> Result:
    """
    No-bypass invariant (security review 2026-07-25) — a raw `budget:` Redis
    key literal must be constructed only inside core/budget/ (the sole broker
    for reserve/reconcile/seed). A hand-rolled key elsewhere would read or
    write the money ledger outside the atomic Lua-script door, defeating the
    no-overspend guarantee (core/budget/redis_budget.py's own docstring).

    FAIL if any file outside backend/core/budget/ or backend/tests/ contains a
    string literal starting with "budget:". tests/ is excluded (test-by-design
    — tests assert against the real key format directly, same carve-out as
    the other confinement checks).
    """
    core_budget = BACKEND_ROOT / "core" / "budget"
    tests_dir = BACKEND_ROOT / "tests"
    candidates = [
        f for f in files
        if not _is_under(f, core_budget) and not _is_under(f, tests_dir)
    ]
    hits = _grep(candidates, r"[\"']budget:")
    status = "FAIL" if hits else "PASS"
    return Result(
        label="raw budget: keys confined to core/budget/",
        invariant_ref="no-bypass (money layer, security review 2026-07-25)",
        status=status,
        hits=hits,
        note="a hand-rolled budget: key outside core/budget/ would bypass reserve/reconcile's atomic Lua door.",
    )


def check_foundation_deep_import(files: list[Path]) -> Result:
    """
    §III.13 smell — callers outside foundation/ should import from the package
    surface (`from foundation import X`), not deep submodules
    (`from foundation.transport import X`).

    WARN (non-fatal): prefer the public surface to insulate against internal
    restructuring.
    """
    foundation_dir = BACKEND_ROOT / "foundation"
    candidates = [f for f in files if not _is_under(f, foundation_dir)]
    hits = _grep(
        candidates,
        r"from foundation\.(transport|vocab|contracts)\b",
    )
    status = "WARN" if hits else "PASS"
    return Result(
        label="no deep-import of foundation submodules",
        invariant_ref="§III.13 (smell)",
        status=status,
        hits=hits,
        note="prefer `from foundation import X` over `from foundation.transport import X`",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _changed_py_files() -> set[Path] | None:
    """
    Return the set of .py files changed vs main (git diff), or None if git
    is unavailable or there are no changed Python files.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "main...HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        paths = set()
        for line in result.stdout.splitlines():
            p = REPO_ROOT / line.strip()
            if p.suffix == ".py" and p.exists():
                paths.add(p)
        return paths if paths else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Invariant audit for the Clannon backend (stand-in for issue #15 Semgrep gate)."
    )
    ap.add_argument(
        "--changed-only",
        action="store_true",
        help="Scope to files changed vs main (git diff --name-only main...HEAD).",
    )
    args = ap.parse_args()

    only: set[Path] | None = None
    if args.changed_only:
        only = _changed_py_files()
        if only:
            print(f"[changed-only] scoping to {len(only)} changed .py file(s)")
        else:
            print("[changed-only] no changed .py files detected — scanning full tree")

    all_files = _iter_py_files(BACKEND_ROOT, only=only)

    print(f"\nClannon invariant check — {len(all_files)} file(s) scanned\n")

    # Pre-filter file lists for checks that are scoped to specific subtrees.
    foundation_files = [f for f in all_files if _is_under(f, BACKEND_ROOT / "foundation")]
    network_capable_files = [
        f for f in all_files
        if _is_under(f, BACKEND_ROOT / "tools") or _is_under(f, BACKEND_ROOT / "experts")
    ]

    results = [
        check_pydantic_ai_confined(all_files),
        check_memory_internals_confined(all_files),
        check_foundation_dep_direction(foundation_files),
        check_no_bare_set(all_files),
        check_network_tools_ssrf_gate(network_capable_files),
        check_foundation_deep_import(all_files),
        check_agent_run_confined_to_retry(all_files),
        check_budget_keys_confined_to_core_budget(all_files),
    ]

    _print_results(results)

    fail_count = sum(1 for r in results if r.status == "FAIL")
    warn_count = sum(1 for r in results if r.status == "WARN")
    pass_count = sum(1 for r in results if r.status == "PASS")

    verdict_parts = [f"{pass_count} PASS"]
    if warn_count:
        verdict_parts.append(f"{warn_count} WARN")
    if fail_count:
        verdict_parts.append(f"{fail_count} FAIL")

    verdict_line = ", ".join(verdict_parts)

    if fail_count:
        print(f"RESULT: {verdict_line} — fix violations before merging (issue #15 tracks the CI gate)")
    else:
        print(f"RESULT: {verdict_line} — no hard violations detected")

    print()
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
