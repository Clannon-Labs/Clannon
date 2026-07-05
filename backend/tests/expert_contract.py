"""Conformance test for the shared expert entry-point + registration contract.

Every expert package under `experts/*/expert.py` exposes the SAME entry point
(see `experts/__init__.py` and `experts/CLAUDE.md` → Conventions):

    async def run(self, args: <ExpertIn>, env: ExpertEnv) -> ExpertOutput

This pins that uniform shape so an expert that drifts from it — a renamed/extra
parameter, a synchronous `run()`, a mistyped annotation, or an `output_schema`
that is not `ExpertOutput` — is caught here rather than at orchestration time.
It also pins each expert's least-privilege REGISTRATION (`permission` +
`tool_grants`) against its documented intent, so a silent broadening (or a
grant a permission level doesn't cover) regresses loudly instead of waiting for
the next manual audit. Both asserts the present, registered roster, so a newly
added expert is covered automatically with no edit to this file (a NEW expert
must be added to `_EXPECTED_REGISTRATION` below, or the pin test fails naming it).

Per QUEUE.md scope: this is a test only. If an expert ever diverges, the fix is a
`needs-reviewer` issue, not an edit to the expert to satisfy the test.
"""

from __future__ import annotations

import glob
import inspect
import os
import typing

from pydantic import BaseModel

import experts
from foundation import PermissionLevel
from registry.capabilities import CapabilityKind, ExpertOutput, discover, registry
from registry.capabilities.handler import ExpertEnv

# The exact run() parameter list every expert shares (self, the structured input,
# and the handler-supplied environment) — order and names both matter, because the
# handler calls `impl.run(args, env)` positionally.
_RUN_PARAMS = ["self", "args", "env"]


def _expert_specs():
    """Every registered (non-broken) expert spec, after discovery."""
    discover()
    return [registry.get_expert(c["key"]) for c in registry.catalog(CapabilityKind.EXPERT)]


def test_expert_roster_matches_files():
    """Enumeration guard: each `experts/*/expert.py` registers exactly one
    non-broken expert, so the contract check below cannot silently skip an expert
    that failed to register (a missing `@expert` decorator or a metadata error
    would drop it from the catalog, not raise)."""
    discover()
    experts_dir = os.path.dirname(experts.__file__)
    on_disk = glob.glob(os.path.join(experts_dir, "*", "expert.py"))
    ok = registry.catalog(CapabilityKind.EXPERT)
    broken = [b.key for b in registry.broken() if b.kind == CapabilityKind.EXPERT]

    assert broken == [], f"experts registered BROKEN: {broken}"
    assert len(ok) == len(on_disk), (
        f"{len(on_disk)} expert.py files but {len(ok)} registered experts "
        f"({sorted(c['key'] for c in ok)})"
    )


def test_expert_run_conforms_to_shared_contract():
    """Each expert's `run` is `async def run(self, args: <input_schema>, env:
    ExpertEnv) -> ExpertOutput`, and declares `output_schema = ExpertOutput`.

    Problems are collected so the assertion names every divergent expert at once
    rather than failing on the first."""
    specs = _expert_specs()
    assert specs, "no experts registered — discovery is broken"

    problems: list[str] = []
    for spec in specs:
        impl = spec.impl
        run = getattr(impl, "run", None)
        if run is None:
            problems.append(f"{spec.key}: no run() method")
            continue

        if not inspect.iscoroutinefunction(run):
            problems.append(f"{spec.key}: run() is not `async def`")

        params = list(inspect.signature(run).parameters)
        if params != _RUN_PARAMS:
            problems.append(f"{spec.key}: run params {params} != {_RUN_PARAMS}")

        # Resolve string annotations (every expert uses `from __future__ import
        # annotations`) against the defining module's namespace.
        try:
            hints = typing.get_type_hints(run)
        except Exception as exc:  # unresolved forward ref, etc.
            problems.append(f"{spec.key}: cannot resolve run() annotations: {exc!r}")
            hints = {}

        if "args" in hints and hints["args"] is not impl.input_schema:
            problems.append(
                f"{spec.key}: args annotation {hints['args']!r} is not its declared "
                f"input_schema {impl.input_schema!r}"
            )
        if "env" in hints and hints["env"] is not ExpertEnv:
            problems.append(f"{spec.key}: env annotation {hints['env']!r} is not ExpertEnv")
        if "return" in hints and hints["return"] is not ExpertOutput:
            problems.append(
                f"{spec.key}: return annotation {hints['return']!r} is not ExpertOutput"
            )

        # Return shape: the declared output schema is the shared ExpertOutput, and
        # the input schema is a real pydantic model (what the handler validates
        # `arguments` against before calling run()).
        if impl.output_schema is not ExpertOutput:
            problems.append(f"{spec.key}: output_schema {impl.output_schema!r} is not ExpertOutput")
        if not (isinstance(impl.input_schema, type) and issubclass(impl.input_schema, BaseModel)):
            problems.append(
                f"{spec.key}: input_schema {impl.input_schema!r} is not a pydantic BaseModel"
            )

    assert not problems, "expert run() contract divergences:\n  " + "\n  ".join(problems)


# Each expert's declared privilege: (permission, sorted tool_grants). Pinned from the
# security-review's round-2 least-privilege audit (2026-07-05) so a later edit that
# broadens a grant or downgrades a permission below what its tools need regresses
# loudly here, not just at the next manual re-audit. A code-execution expert MUST be
# EXECUTE; a NETWORK-tool-granted expert MUST be NETWORK (invariant A depends on the
# handler seeing the true permission); a tool-less reasoner is READ.
_EXPECTED_REGISTRATION: dict[str, tuple[PermissionLevel, tuple[str, ...]]] = {
    "code.engineer": (PermissionLevel.EXECUTE, ("code.run", "fs.read", "fs.write")),
    "data.analyst": (PermissionLevel.EXECUTE, ("code.run", "fs.read", "fs.write")),
    "docs.writer": (PermissionLevel.WRITE, ("fs.read", "fs.write")),
    "media.analyst": (PermissionLevel.READ, ("fs.read",)),
    "delivery.notifier": (PermissionLevel.NETWORK, ("http.request",)),
    "summary.condenser": (PermissionLevel.READ, ()),
    "verification.claims": (PermissionLevel.NETWORK, ("search.web", "web.fetch_url")),
    "web.research": (PermissionLevel.NETWORK, ("search.web", "web.fetch_url")),
    "synthesis.writer": (PermissionLevel.READ, ()),
}


def test_expert_registration_pins_least_privilege():
    """Each expert's `permission` + `tool_grants` match the pinned expectation, and
    every registered expert has a pin (an unpinned expert fails this loudly, rather
    than silently skipping the check for a newly added one)."""
    specs = {spec.key: spec for spec in _expert_specs()}

    unpinned = set(specs) - set(_EXPECTED_REGISTRATION)
    assert not unpinned, (
        f"expert(s) {sorted(unpinned)} have no pinned expectation in "
        "_EXPECTED_REGISTRATION -- add one (permission, sorted tool_grants)."
    )

    problems: list[str] = []
    for key, (expected_permission, expected_grants) in _EXPECTED_REGISTRATION.items():
        spec = specs.get(key)
        if spec is None:
            problems.append(f"{key}: pinned but not registered (renamed or removed?)")
            continue
        if spec.permission is not expected_permission:
            problems.append(
                f"{key}: permission {spec.permission!r} != expected {expected_permission!r}"
            )
        grants = tuple(sorted(spec.tool_grants))
        if grants != expected_grants:
            problems.append(f"{key}: tool_grants {grants} != expected {expected_grants}")

    assert not problems, "expert registration drifted from its pin:\n  " + "\n  ".join(problems)
