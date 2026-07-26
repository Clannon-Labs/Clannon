"""
Frontend<->backend SSE event-contract drift test (Critical Benchmark 6).

The frontend mock client (`frontend/src/lib/api/{mock,mock-data,types}.ts`) defines
the live-run SSE contract the real backend must serve: the event `type` names, their
payload shapes, and the enum vocabularies (run status, decision-log kind, expert
status). The backend emits those same events from `api/run_state.py` (the RunState
mappers) and `api/run_driver.py` (the conversational close event), declared in
`api/README.md`. If the two sides silently diverge, the UI either drops events the
backend sends (data loss) or renders `undefined` for fields the backend stopped
sending. C6's failure condition is exactly this contract divergence.

WHAT THIS TEST DOES
  1. Pins the FRONTEND contract into a committed, machine-checkable fixture
     (`fixtures/sse_contract.json`) and asserts the fixture still matches the
     frontend source (so the fixture cannot rot silently as the frontend evolves).
  2. Extracts the BACKEND's emitted events from the real code, two ways that must
     agree: the authoritative event-NAME set comes from source-scanning EVERY emit
     site (`run_state.py` + `run_driver.py`), and the payload SHAPES come from RUNNING
     the real RunState mappers (plus `run_driver._collect_sources` for the `sources`
     event's nested `Source` items -- not a RunState mapper, but still real code, run
     for real rather than left to the shallow scan). A scan-vs-run reconciliation
     fails loudly if a new emit site is ever added to `run_state.py` without being
     exercised by this harness -- otherwise that new event type would silently escape
     every drift check below (the exact C6 failure mode: the backend emits an event
     the frontend drops). Run statuses / decision kinds are introspected from
     `ACTIVE_STAGES` / `DecisionLogKind`.
  3. Classifies every divergence as MATERIAL (a real break) or INFORMATIONAL (a
     forward-compatible gap: the frontend declares an event the backend has not
     wired yet, which is safe because the frontend ignores events it does not know).
  4. Cross-checks `api/README.md`'s declared SSE frame list against the code so the
     documented backend contract cannot drift from what the backend actually emits.

ACCEPTANCE / DRIFT POLICY
  * Aligned contract -> the tests PASS.
  * MATERIAL drift -> `test_no_material_contract_drift` emits a ready-to-file
    needs-reviewer escalation (banner-marked, and written to $SSE_CONTRACT_DRIFT_REPORT
    when set) and FAILS. It never edits the frontend or the backend to force a pass;
    reconciling a real divergence is a maintainer decision. The test itself cannot
    call `gh` (no credentials in CI by design) -- it produces the issue body and the
    loop/CI opens the needs-reviewer issue from the marker.

Hermetic: no network, no models, no DB. Run from `backend/`:
    .venv/bin/python -m pytest tests/benchmarks/sse_contract_drift.py -q
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
_FIXTURE = _HERE.parent / "fixtures" / "sse_contract.json"
_REPO_ROOT = _HERE.parents[3]
_BACKEND_ROOT = _HERE.parents[2]
_FRONTEND_API = _REPO_ROOT / "frontend" / "src" / "lib" / "api"
_TYPES_TS = _FRONTEND_API / "types.ts"
_MOCK_TS = _FRONTEND_API / "mock.ts"
_RUN_STATE_PY = _BACKEND_ROOT / "api" / "run_state.py"
_RUN_DRIVER_PY = _BACKEND_ROOT / "api" / "run_driver.py"
_README_MD = _BACKEND_ROOT / "api" / "README.md"

# A stable banner so the unattended loop / CI can recognise this escalation in the
# test output and open the needs-reviewer issue from it.
_ESCALATION_BANNER = "=== NEEDS-REVIEWER: FRONTEND<->BACKEND SSE CONTRACT DRIFT ==="


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def _load_fixture() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Frontend extraction (parse the TypeScript source)
# ---------------------------------------------------------------------------

def _strip_ts_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)   # block + JSDoc comments
    src = re.sub(r"//[^\n]*", "", src)                # line comments
    return src


def _ts_union_values(src: str, type_name: str) -> list[str]:
    """String-literal members of `export type NAME = "a" | "b" | ...;`."""
    m = re.search(rf"export type {type_name}\s*=(.*?);", src, flags=re.S)
    assert m, f"could not locate `export type {type_name}` in types.ts"
    return re.findall(r'"([^"]+)"', m.group(1))


def _ts_run_event(src: str) -> dict[str, list[str]]:
    """The RunEvent discriminated union -> {event type: [payload keys besides type]}.

    Members carry an internal `;` (`{ type: "x"; field: T }`), so the alias is
    terminated at the last `}` immediately followed by `;` (`... number };`), not at
    the first `;`."""
    m = re.search(r"export type RunEvent\s*=(.*?\})\s*;", src, flags=re.S)
    assert m, "could not locate `export type RunEvent` in types.ts"
    events: dict[str, list[str]] = {}
    for member in re.findall(r"\{(.*?)\}", m.group(1), flags=re.S):  # members are flat
        tm = re.search(r'type\s*:\s*"([^"]+)"', member)
        if not tm:
            continue
        keys = [k for k in re.findall(r"(\w+)\s*:", member) if k != "type"]
        events[tm.group(1)] = sorted(set(keys))
    return events


def _ts_interface_fields(src: str, name: str) -> tuple[list[str], list[str]]:
    """`export interface NAME { ... }` -> (required fields, optional fields)."""
    m = re.search(rf"export interface {name}\s*\{{(.*?)\n\}}", src, flags=re.S)
    assert m, f"could not locate `export interface {name}` in types.ts"
    required, optional = [], []
    for line in m.group(1).splitlines():
        fm = re.match(r"\s*(\w+)(\??)\s*:", line)
        if not fm:
            continue
        (optional if fm.group(2) == "?" else required).append(fm.group(1))
    return sorted(required), sorted(optional)


def _mock_emitted_event_types(mock_src: str) -> set[str]:
    """Event `type` literals the mock client actually yields. Constrained to
    pure lowercase/underscore names, which excludes Blob mime literals like
    `type: "text/markdown"` (the slash fails the character class)."""
    return set(re.findall(r'type:\s*"([a-z_]+)"', _strip_ts_comments(mock_src)))


def _frontend_contract() -> dict:
    """The live frontend contract parsed from the TypeScript source."""
    types_src = _strip_ts_comments(_TYPES_TS.read_text(encoding="utf-8"))
    dle_req, dle_opt = _ts_interface_fields(types_src, "DecisionLogEntry")
    exp_req, exp_opt = _ts_interface_fields(types_src, "ExpertState")
    src_req, src_opt = _ts_interface_fields(types_src, "Source")
    return {
        "stream_events": _ts_run_event(types_src),
        "nested_shapes": {
            "DecisionLogEntry": {"required_keys": dle_req, "optional_keys": dle_opt},
            "ExpertState": {"required_keys": exp_req, "optional_keys": exp_opt},
            "Source": {"required_keys": src_req, "optional_keys": src_opt},
        },
        "decision_kinds": _ts_union_values(types_src, "DecisionKind"),
        "run_statuses": _ts_union_values(types_src, "RunStatus"),
        "expert_statuses": _ts_union_values(types_src, "ExpertStatus"),
        "mock_emitted": _mock_emitted_event_types(_MOCK_TS.read_text(encoding="utf-8")),
    }


# ---------------------------------------------------------------------------
# Backend extraction (RUN the real mappers; scan only what cannot be run)
# ---------------------------------------------------------------------------

def _emit_literals(path: Path) -> dict[str, list[str]]:
    """`run.emit({"type": "X", "k": ...})` literals in a backend module ->
    {X: [other string keys]}. Used for the driver close event, which has no
    isolated mapper to drive."""
    src = path.read_text(encoding="utf-8")
    out: dict[str, list[str]] = {}
    for m in re.finditer(r'\{"type":\s*"(\w+)"([^}]*)\}', src):
        keys = [k for k in re.findall(r'"(\w+)"\s*:', m.group(2))]
        out[m.group(1)] = sorted(set(keys))
    return out


def _backend_contract() -> dict:
    """Extract the backend's emitted SSE contract by exercising the real code."""
    from api.run_state import RunState, TERMINAL_STATUSES
    from core.pipeline import ACTIVE_STAGES
    from core.orchestrator.schemas import DecisionLogEntry, DecisionLogKind

    events: dict[str, set[str]] = {}        # event type -> top-level keys (besides `type`)
    nested: dict[str, set[str]] = {}        # "entry"/"expert" -> keys produced by the mapper
    log_kinds: set[str] = set()             # decision kinds that land in a `log` entry
    expert_statuses: set[str] = set()       # expert statuses the backend actually emits

    def _new() -> RunState:
        return RunState(id="r", user_id="u", title="t", brief="b")

    def _harvest(run: RunState) -> None:
        for ev in run.events:
            t = ev["type"]
            events.setdefault(t, set()).update(k for k in ev if k != "type")
            if t == "log":
                nested.setdefault("entry", set()).update(ev["entry"].keys())
                log_kinds.add(ev["entry"]["kind"])
            if t == "expert":
                nested.setdefault("expert", set()).update(ev["expert"].keys())
                expert_statuses.add(ev["expert"]["status"])

    # status event
    r = _new()
    r.on_status("delivered")
    _harvest(r)

    # verification event (CB5 earned seal)
    r = _new()
    r.on_verification("grounded")
    _harvest(r)

    # every decision-log kind through the real mapper -- this also pins which kinds
    # become `log` entries vs the `message` channel (kind="message" -> message_delta)
    for kind in get_args(DecisionLogKind):
        r = _new()
        detail = (
            {"expert": "web.research", "domain": "Market"}
            if kind == "expert_spawn"
            else {"k": "v"}
        )
        r.on_log_entry(DecisionLogEntry(kind=kind, message="m", detail=detail))
        _harvest(r)

    # experts reconciled after orchestration: success -> done (+summary), fail -> failed
    r = _new()
    r.on_experts_settled([
        SimpleNamespace(expert_name="web.research", arguments={"domain": "Market"},
                        sub_tool_calls=[1, 2], success=True, result={"summary": "s"}),
        SimpleNamespace(expert_name="web.research", arguments={"domain": "Reg"},
                        sub_tool_calls=[], success=False, result=None),
    ])
    _harvest(r)

    # report streaming (async mapper)
    import asyncio
    r = _new()
    asyncio.run(r.stream_report("one two three four five six seven eight nine ten"))
    _harvest(r)

    # grounded-search sources (api.run_driver._collect_sources): not a RunState
    # mapper, but still the real code building the `sources` event's payload -- RUN
    # it for real (like every other nested shape above) rather than leaving it to the
    # shallow emit-literal scan below, which only ever sees the outer "sources" key
    # and would stay silent if a Source field were ever renamed or dropped.
    from api.run_driver import _collect_sources
    fake_call = SimpleNamespace(success=True, result={"sources": ["https://example.com/some-page"]})
    srcs = _collect_sources(SimpleNamespace(tool_calls=[fake_call], expert_calls=[]))
    if srcs:
        nested["source"] = set(srcs[0].keys())

    # event types the harness actually OBSERVED by running run_state's mappers above;
    # their payload shapes are therefore real, not guessed. Captured BEFORE the
    # source-scan merge so the scan-vs-run reconciliation can compare the two.
    run_observed = set(events)

    # Authoritative event-NAME universe: source-scan EVERY emit site. The set of event
    # names the backend can put on the wire must NOT depend on which mappers this
    # harness happens to drive -- otherwise a newly added mapper emitting a new event
    # type would be invisible here, and material-drift check #1 ("the backend emits an
    # event the frontend silently drops") could never fire for it (the C6 failure mode).
    # The scan is authoritative for NAMES; the run above stays authoritative for payload
    # SHAPES. Where a name is both scanned and run-observed the shapes agree (asserted by
    # test_run_state_emit_sites_are_all_exercised); run_driver's two events
    # (`message_delta` on the final-answer path, the `message_done` close) have no
    # isolated mapper, so the scan is the only way to see them.
    state_scan = _emit_literals(_RUN_STATE_PY)
    driver_scan = _emit_literals(_RUN_DRIVER_PY)
    for etype, keys in {**state_scan, **driver_scan}.items():
        events.setdefault(etype, set()).update(keys)

    # backend run-status vocabulary: pipeline stage statuses + terminal + initial
    statuses = {s.status for s in ACTIVE_STAGES} | set(TERMINAL_STATUSES) | {"queued"}

    return {
        "events": {k: sorted(v) for k, v in events.items()},
        "nested": {k: sorted(v) for k, v in nested.items()},
        "decision_kinds": sorted(log_kinds),
        "run_statuses": sorted(statuses),
        "expert_statuses": sorted(expert_statuses),
        # the full backend kind enum, for the escalation note (includes "message",
        # which is translated to a message_delta and never reaches a `log` entry)
        "all_decision_kinds": sorted(get_args(DecisionLogKind)),
        # scan-vs-run reconciliation inputs (C6 safety net): every event the run_state
        # SOURCE emits must be exercised by a mapper this harness drives. run_driver's
        # events are scan-only (no isolated mapper) and so are excluded from this check.
        "run_state_scanned_events": sorted(state_scan),
        "run_observed_events": sorted(run_observed),
    }


# ---------------------------------------------------------------------------
# Drift classification + needs-reviewer escalation
# ---------------------------------------------------------------------------

def _classify_drift(fixture: dict, backend: dict) -> tuple[list[str], list[str]]:
    """Compare the backend reality against the frontend fixture.

    Returns (material, informational). MATERIAL = a real break the maintainer must
    reconcile. INFORMATIONAL = a forward-compatible gap (frontend ahead of backend),
    which is safe and expected.
    """
    material: list[str] = []
    info: list[str] = []

    fe_events = fixture["stream_events"]
    be_events = backend["events"]

    # 1. backend emits an event the frontend does not know -> silent data loss
    for etype in sorted(set(be_events) - set(fe_events)):
        material.append(
            f"stream event `{etype}`: emitted by the backend but ABSENT from the "
            f"frontend RunEvent union -> the UI silently drops it (data loss)."
        )

    # 2. a backend-required event the backend no longer emits -> regression;
    #    a forward-compat (non-required) event the frontend has but the backend
    #    does not stream -> informational.
    for etype, spec in fe_events.items():
        emitted = etype in be_events
        if spec.get("backend_required", False) and not emitted:
            material.append(
                f"stream event `{etype}`: marked backend_required in the contract but "
                f"the backend no longer emits it -> the UI never receives it."
            )
        elif not spec.get("backend_required", False) and not emitted:
            info.append(
                f"stream event `{etype}`: declared by the frontend, not yet streamed by "
                f"the backend (forward-compatible; frontend handles it if/when sent)."
            )
        elif not spec.get("backend_required", False) and emitted:
            info.append(
                f"stream event `{etype}`: the backend now streams a previously "
                f"forward-compat-only event -> consider flipping backend_required to true."
            )

    # 3. shared events: every required payload key the frontend reads must be present
    for etype, spec in fe_events.items():
        if etype not in be_events:
            continue
        be_keys = set(be_events[etype])
        # the frontend reads nested shapes via the `entry`/`expert` keys; resolve the
        # required keys to the nested shape where the contract nests them.
        missing = set(spec["required_keys"]) - be_keys
        if missing:
            material.append(
                f"stream event `{etype}`: backend payload is missing required key(s) "
                f"{sorted(missing)} the frontend reads (backend sends {sorted(be_keys)})."
            )

    # 3b. nested shapes the backend builds (log entry, expert state, source)
    nested_map = {"entry": "DecisionLogEntry", "expert": "ExpertState", "source": "Source"}
    for be_key, shape_name in nested_map.items():
        if be_key not in backend["nested"]:
            continue
        be_keys = set(backend["nested"][be_key])
        req = set(fixture["nested_shapes"][shape_name]["required_keys"])
        missing = req - be_keys
        if missing:
            material.append(
                f"{shape_name}: backend-built payload is missing required key(s) "
                f"{sorted(missing)} (backend builds {sorted(be_keys)})."
            )

    # 4. enum vocabularies: every backend value must be known to the frontend
    for label, fe_key, be_key in (
        ("decision-log kind", "decision_kinds", "decision_kinds"),
        ("run status", "run_statuses", "run_statuses"),
        ("expert status", "expert_statuses", "expert_statuses"),
    ):
        unknown = set(backend[be_key]) - set(fixture[fe_key])
        for value in sorted(unknown):
            material.append(
                f"{label} `{value}`: produced by the backend but not in the frontend "
                f"{label} union -> the UI cannot render/route it."
            )

    return material, info


def _needs_reviewer_report(material: list[str], info: list[str],
                           fixture: dict, backend: dict) -> str:
    lines = [
        _ESCALATION_BANNER,
        "",
        "The frontend SSE contract (frontend/src/lib/api/types.ts + mock.ts, pinned in",
        "backend/tests/benchmarks/fixtures/sse_contract.json) and the backend's emitted",
        "events (api/run_state.py + api/run_driver.py) have MATERIALLY diverged.",
        "",
        "This test does NOT edit either side: reconciling the contract is a maintainer",
        "decision (update the frontend, the backend, or the fixture as appropriate).",
        "",
        "## Material divergences",
    ]
    lines += [f"- {d}" for d in material]
    if info:
        lines += ["", "## Forward-compatible notes (not blocking)"]
        lines += [f"- {d}" for d in info]
    lines += [
        "",
        "## Observed (this run)",
        f"- backend stream events: {sorted(backend['events'])}",
        f"- backend decision kinds (reach a log entry): {backend['decision_kinds']}",
        f"- backend decision kinds (all, incl. translated): {backend['all_decision_kinds']}",
        f"- backend run statuses: {backend['run_statuses']}",
        f"- backend expert statuses: {backend['expert_statuses']}",
        f"- frontend stream events: {sorted(fixture['stream_events'])}",
        "",
        "Label the issue `needs-reviewer`.",
    ]
    return "\n".join(lines)


def _escalate(report: str) -> None:
    """Surface a needs-reviewer escalation. Cannot open the GH issue directly (no
    credentials in CI/loop by design); writes the issue body where the harness can
    pick it up and fails loudly with the banner-marked report."""
    path = os.environ.get("SSE_CONTRACT_DRIFT_REPORT")
    if path:
        Path(path).write_text(report + "\n", encoding="utf-8")
    pytest.fail("\n" + report, pytrace=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _require_frontend() -> dict:
    if not _TYPES_TS.exists() or not _MOCK_TS.exists():
        pytest.skip("frontend source not present in this checkout")
    return _frontend_contract()


def test_fixture_matches_frontend_source():
    """The committed fixture must still mirror the frontend TypeScript, so it cannot
    rot silently as the frontend evolves. If the frontend moved, refresh the fixture
    AND re-check backend alignment."""
    fe = _require_frontend()
    fx = _load_fixture()

    assert set(fx["stream_events"]) == set(fe["stream_events"]), (
        "RunEvent type names drifted from the fixture: "
        f"fixture={sorted(fx['stream_events'])} frontend={sorted(fe['stream_events'])}. "
        "Refresh fixtures/sse_contract.json from types.ts."
    )
    for etype, keys in fe["stream_events"].items():
        assert set(fx["stream_events"][etype]["required_keys"]) == set(keys), (
            f"payload keys for `{etype}` drifted: "
            f"fixture={fx['stream_events'][etype]['required_keys']} frontend={keys}."
        )
    for shape in ("DecisionLogEntry", "ExpertState", "Source"):
        assert set(fx["nested_shapes"][shape]["required_keys"]) == set(fe["nested_shapes"][shape]["required_keys"]), (
            f"{shape} required keys drifted from the frontend interface: "
            f"fixture={fx['nested_shapes'][shape]['required_keys']} "
            f"frontend={fe['nested_shapes'][shape]['required_keys']}."
        )
        assert set(fx["nested_shapes"][shape]["optional_keys"]) == set(fe["nested_shapes"][shape]["optional_keys"]), (
            f"{shape} optional keys drifted from the frontend interface: "
            f"fixture={fx['nested_shapes'][shape]['optional_keys']} "
            f"frontend={fe['nested_shapes'][shape]['optional_keys']}."
        )
    for enum in ("decision_kinds", "run_statuses", "expert_statuses"):
        assert set(fx[enum]) == set(fe[enum]), (
            f"{enum} drifted from the frontend union: "
            f"fixture={sorted(fx[enum])} frontend={sorted(fe[enum])}."
        )
    # the mock client must only yield events declared in the RunEvent union
    assert fe["mock_emitted"] <= set(fe["stream_events"]), (
        f"mock.ts yields event(s) not in the RunEvent union: "
        f"{sorted(fe['mock_emitted'] - set(fe['stream_events']))}."
    )


def test_backend_emitted_events_are_known_to_the_frontend():
    """Every event the backend emits must be one the frontend can handle; shared
    events must carry the required payload keys."""
    fx = _load_fixture()
    be = _backend_contract()
    unknown = set(be["events"]) - set(fx["stream_events"])
    assert not unknown, f"backend emits event(s) the frontend does not know: {sorted(unknown)}"
    for etype, keys in be["events"].items():
        required = set(fx["stream_events"][etype]["required_keys"])
        assert required <= set(keys), (
            f"`{etype}` payload missing required key(s) {sorted(required - set(keys))}"
        )


def test_backend_required_events_are_all_emitted():
    """Every event the contract marks backend_required must actually be emitted."""
    fx = _load_fixture()
    be = _backend_contract()
    for etype, spec in fx["stream_events"].items():
        if spec.get("backend_required", False):
            assert etype in be["events"], f"backend_required event `{etype}` is not emitted"


def test_backend_nested_shapes_satisfy_the_frontend():
    """The backend-built log entry, expert, and source payloads must carry every
    required key."""
    fx = _load_fixture()
    be = _backend_contract()
    for be_key, shape in (("entry", "DecisionLogEntry"), ("expert", "ExpertState"), ("source", "Source")):
        required = set(fx["nested_shapes"][shape]["required_keys"])
        built = set(be["nested"].get(be_key, []))
        assert required <= built, (
            f"{shape}: backend missing required key(s) {sorted(required - built)} (built {sorted(built)})"
        )


def test_backend_enums_are_known_to_the_frontend():
    """Backend decision kinds (that reach a log entry), run statuses, and expert
    statuses must all be values the frontend declares."""
    fx = _load_fixture()
    be = _backend_contract()
    assert set(be["decision_kinds"]) <= set(fx["decision_kinds"]), (
        f"backend decision kinds not in frontend union: "
        f"{sorted(set(be['decision_kinds']) - set(fx['decision_kinds']))}"
    )
    assert set(be["run_statuses"]) <= set(fx["run_statuses"]), (
        f"backend run statuses not in frontend union: "
        f"{sorted(set(be['run_statuses']) - set(fx['run_statuses']))}"
    )
    assert set(be["expert_statuses"]) <= set(fx["expert_statuses"]), (
        f"backend expert statuses not in frontend union: "
        f"{sorted(set(be['expert_statuses']) - set(fx['expert_statuses']))}"
    )
    # the internal "message" kind must NOT surface as a decision-log entry kind --
    # it is translated to a `message_delta` stream event. If it ever appears as a
    # log kind, the frontend (which has no "message" DecisionKind) would mis-render.
    assert "message" not in be["decision_kinds"], (
        "backend leaked the internal `message` kind into a log entry; it must become "
        "a message_delta event, not a decision-log entry."
    )


def test_run_state_emit_sites_are_all_exercised():
    """C6 safety net: backend event DISCOVERY must not be execution-bound. Every event
    type emitted from the `api/run_state.py` SOURCE must also be produced by RUNNING a
    mapper in `_backend_contract`. If a future change adds a new emit site (a new mapper
    emitting a new event type) without wiring a call into the harness, the run-based
    shape extraction -- and the material-drift check that catches "the backend emits an
    event the frontend silently drops" -- would never see it, so the protection would be
    illusory. The source scan is the authoritative event-name set; this asserts the run
    harness actually covers all of it, converting that protection from illusory to real."""
    be = _backend_contract()
    scanned = set(be["run_state_scanned_events"])
    observed = set(be["run_observed_events"])
    unexercised = scanned - observed
    assert not unexercised, (
        f"new backend emit site(s) {sorted(unexercised)} in api/run_state.py are not "
        "exercised by the contract harness -- wire a mapper call into _backend_contract() "
        "so the new event's payload shape is checked against the frontend contract (C6)."
    )
    # The converse cannot happen unless the emit-literal scan silently missed a literal
    # the mappers actually emit (e.g. a multi-line literal the regex skips). Guard it so
    # the scan can never quietly fall behind the running code.
    phantom = observed - scanned
    assert not phantom, (
        f"harness observed event(s) {sorted(phantom)} not found by the run_state source "
        "scan -- the emit-literal scan is out of sync with the mappers (fix _emit_literals)."
    )


def _readme_sse_frames() -> set[str]:
    """The SSE frame names declared in api/README.md's `/runs/:id/stream` row."""
    src = _README_MD.read_text(encoding="utf-8")
    row = next((ln for ln in src.splitlines() if "/runs/:id/stream" in ln), "")
    m = re.search(r"RunEvent`:\s*(.*?)\.\s", row)
    assert m, "could not locate the SSE frame enumeration in api/README.md"
    return set(re.findall(r"`([a-z_]+)`", m.group(1)))


def test_readme_frame_list_matches_the_code():
    """The fixture cites api/README.md as the backend's DECLARED contract; assert code
    and doc cannot drift apart unnoticed. Every event the backend actually emits must be
    documented, and every documented frame must be real -- either emitted, or at least a
    frontend-declared forward-compatible event. This keeps `usage` (declared by the
    frontend, not yet streamed) honest while catching an invented frame or an
    emitted-but-undocumented event."""
    if not _README_MD.exists():
        pytest.skip("api/README.md not present in this checkout")
    fx = _load_fixture()
    be = _backend_contract()
    frames = _readme_sse_frames()
    emitted = set(be["events"])
    undocumented = emitted - frames
    assert not undocumented, (
        f"backend emits event(s) {sorted(undocumented)} not documented in api/README.md's "
        "SSE frame list -- update the README so the declared contract matches the code."
    )
    declared = set(fx["stream_events"])
    invented = frames - emitted - declared
    assert not invented, (
        f"api/README.md declares SSE frame(s) {sorted(invented)} the backend does not emit "
        "and the frontend contract does not declare -- the doc is out of date."
    )


def test_no_material_contract_drift():
    """The canonical C6 drift gate. Passes when the contract is aligned; on material
    drift it emits a needs-reviewer escalation and fails without editing either side.
    Forward-compatible gaps are reported but do not fail the test."""
    fx = _load_fixture()
    be = _backend_contract()
    material, info = _classify_drift(fx, be)
    if material:
        _escalate(_needs_reviewer_report(material, info, fx, be))
    # aligned: surface the forward-compat notes for visibility, then pass.
    if info:
        print("SSE contract aligned. Forward-compatible notes:")
        for note in info:
            print(f"  - {note}")
