"""Critical Benchmark 4 — Institutional Decision Memory: decision-recall harness.

Ingests the repo's OWN Architecture Decision Records (``docs/decisions/*/000*.md``)
into the episodic store through the REAL ``MemoryPort`` write door, then opens a
brand-new session and asks each decision's institutional-memory questions —

    "why was decision X made / what alternatives / what risks / who proposed it"

— and reports how much of the *reasoning* survives retrieval. It maps a structured
PASS / PARTIAL / FAIL read onto C4's five "must preserve" requirements:

    decision · reasoning · tradeoffs · participants · historical-context

The point of C4 is that *reasoning* persists, not merely the final outcome. Each
ADR carries Context (why), a Decision, Alternatives considered, and Consequences &
risks; this harness proves those fields can be written as ordinary episodic memory
and recalled together when a later session asks about the decision — with no
conversation history and no manual context injection.

What is hermetic, and what is honestly NOT-YET
----------------------------------------------
The harness runs the actual ``core.memory.manager.MemoryManager`` write
(``record_write_proposals``) and read (``hydrate``) paths unchanged. Only the two
external seams the manager calls are doubled, with the shape production uses:

  * the Qdrant store -> an in-memory, ``user_id``-scoped ``_FakeStore`` (it enforces
    the tenant filter exactly like ``core.memory.store.search``, so a scope leak is
    observable, not silently impossible).
  * the nomic embedder -> a deterministic lexical ``_lex_embed`` (a text maps to the
    L2-normalized indicator over its distinctive tokens, so cosine is the shared
    distinctive-vocabulary overlap — a controllable relevance signal that exercises
    the manager's real 0.30 floor and ranking without a model download).

It therefore HERMETICALLY certifies the decision-memory PLUMBING: an ADR's full
reasoning is stored in the EXISTING ``content`` field (no new EntryType, no schema
change — that typed-record work is gated on issue #16), survives the write/read
path, is scoped to its ``user_id``, and is recalled as the top hit when its
decision is asked about. The real nomic embedder's semantic recall quality is a
live concern, not certified here.

Two of the five requirements are reported honestly below PASS:

  * PARTICIPANTS is NOT-YET: ADRs record an *Authority* tier and a *Source*, but no
    proposer/author/discussion participants — "who proposed it" cannot be answered
    from the record. That is the typed-provenance capability gated on issue #16.
  * TRADEOFFS and HISTORICAL-CONTEXT are PARTIAL: the alternatives, risks, status,
    and supersession text are recalled as prose inside one episodic blob, but they
    are NOT first-class, separately-queryable typed records, and no supersession /
    temporal-validity LINK connects a deprecated decision to the one that replaced
    it. That structuring is gated on issue #16 (and Exceptional Benchmark 1).

This harness MEASURES those gaps; it does not implement them, and it never fakes a
pass.

Run:
    pytest tests/benchmarks/c4_decision_memory.py -q          # acceptance tests
    PYTHONPATH=tests python -m benchmarks.c4_decision_memory  # from backend/, prints report

``run()`` returns the ``BenchmarkReport`` for the consolidated scoreboard harness.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import re
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

from foundation import HydrationRequest, MemoryStore, MemoryWriteProposal, NormalizedInput
from core.memory import MemoryManager
from core.memory import embeddings as embeddings_mod
from core.memory import store as store_mod
from core.memory.embeddings import DIMS
# The manager truncates stored content to this many chars; importing it (rather than
# hardcoding 2000) keeps the cap in sync. NB: `from core.memory import manager` would
# give the singleton INSTANCE (re-exported in __init__), so we import the constant
# straight from the module instead.
from core.memory.manager import _MAX_CONTENT_CHARS

try:  # package context (pytest collects this as benchmarks.c4_decision_memory)
    from .report import BenchmarkReport, Verdict
except ImportError:  # direct-path context (backend/tests/benchmarks on sys.path[0])
    from report import BenchmarkReport, Verdict


ARCHITECT = "c4-architect"   # the synthetic maintainer whose ADRs we ingest + recall
RIVAL = "c4-rival"           # a second tenant; their ADR must never leak into ARCHITECT's recall
SESSION = "adr-ingest-session"
# A marker only the rival tenant's record carries, so a scope leak is observable in
# the recalled package rather than silently impossible.
_RIVAL_SENTINEL = "tenant-marker-rival-do-not-leak"

# The repo's ADR corpus. The task ingests docs/decisions/*/000*.md across the four
# lifecycle folders. A query later asks each decision's why/alternatives/risks.
_ADR_GLOB = "000*.md"
_LIFECYCLE_FOLDERS = ("accepted", "proposed", "rejected", "deprecated")

# >= this many ADRs must be ingested for the harness to be meaningful (task floor).
_MIN_ADRS = 3
# How many distinct decisions to probe with recall questions (a representative set
# spanning lifecycle states; capped so the report stays readable).
_PROBE_COUNT = 5
# Generous read budget so the relevance floor (not the budget) is what filters
# recall — one ADR record is a few hundred tokens.
_READ_BUDGET = 6000


# --------------------------------------------------------------------------
# Deterministic lexical embedder (hermetic stand-in for the nomic model).
#
# A text maps to the L2-normalized indicator over its DISTINCTIVE tokens: each such
# token lights one dimension (stable-hashed into the 768-dim space, so the mapping
# is identical across processes — unlike the salted builtin hash). Cosine then
# reduces to |shared distinctive tokens| / sqrt(|q| * |d|): a question that names a
# decision's subject overlaps its own ADR strongly and unrelated ADRs weakly, which
# is exactly the relevance signal the real manager floors and ranks on. Stopwords
# and ADR scaffolding ("decision", "status", "alternatives", "why", "what", ...) are
# dropped so the vector is dominated by each decision's own subject matter.
# --------------------------------------------------------------------------
_STOPWORDS = frozenset("""
a an and any are as at be been but by can could did do does for from had has have
how if in into is it its may might must no nor not of on or our over per so than
that the their them then there these this those to too via was were what when
where which who whom why will with would you your we us
adr adrs decision decisions decided decide status state context reasoning reason
rationale alternative alternatives considered consequence consequences risk risks
risked source sources tier authority proposed accepted rejected deprecated option
options selected select made make project projects record recorded records
argument arguments supported support identified identify proposer propose
clannon vraksha system systems
""".split())

_TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{2,}")


def _distinctive_tokens(text: str) -> frozenset[str]:
    """The content-bearing tokens of a text: lowercased words >= 3 chars, minus
    stopwords and ADR scaffolding. This is the vocabulary cosine is measured over."""
    return frozenset(t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS)


def _dim(token: str) -> int:
    """Stable, process-independent hash of a token into the embedding space."""
    return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big") % DIMS


def _lex_embed(text: str) -> list[float]:
    vec = [0.0] * DIMS
    tokens = _distinctive_tokens(text)
    if not tokens:
        vec[0] = 1.0  # a non-empty unit vector for text with no distinctive token
        return vec
    for t in tokens:
        vec[_dim(t)] = 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def _fake_embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [_lex_embed(t) for t in texts]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# --------------------------------------------------------------------------
# In-memory, user_id-scoped store double (stands in for Qdrant).
#
# Mirrors core.memory.store: search applies the tenant filter HERE (so a leak is
# observable), upsert stamps created_at like the real store, is_down stays False
# (the store is up; "no memory" is genuine emptiness, not degradation).
# --------------------------------------------------------------------------
class _FakeStore:
    def __init__(self) -> None:
        self.points: dict[MemoryStore, list[dict]] = {t: [] for t in MemoryStore}
        self._seq = 0

    def is_down(self) -> bool:
        return False

    def upsert(
        self, tier, user_id, session_id, trace_id, vector, content,
        rationale, confidence, trust, point_id=None, **_typed_kw,
    ) -> str:  # _typed_kw absorbs CB1's kind/valid_at/source/superseded_by (unused here)
        bucket = self.points[tier]
        if point_id is not None:  # refresh path (real store replaces in place)
            for p in bucket:
                if p["id"] == point_id and p["user_id"] == user_id:
                    p.update(content=content, rationale=rationale,
                             confidence=confidence, vector=vector)
                    return point_id
        self._seq += 1
        pid = f"pt-{self._seq}"
        bucket.append({
            "id": pid, "user_id": user_id, "session_id": session_id,
            "trace_id": trace_id, "tier": tier.value, "content": content,
            "rationale": rationale, "confidence": confidence, "trust": trust,
            "created_at": _NOW, "vector": vector,
        })
        return pid

    def search(self, tier, user_id, vector, limit=8) -> list[dict]:
        hits = []
        for p in self.points[tier]:
            if p["user_id"] != user_id:  # THE scope — enforced here, like Qdrant
                continue
            score = _cosine(vector, p["vector"])
            hits.append({"id": p["id"], "score": score,
                         **{k: v for k, v in p.items() if k != "vector"}})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:limit]


# A fixed "now" so created_at is deterministic and recency weighting is uniform
# across every ingested ADR (recency is exercised in the C1 harness, not here).
_NOW = 1_750_000_000.0


# --------------------------------------------------------------------------
# ADR parsing — pull the structured fields out of each docs/decisions ADR.
# --------------------------------------------------------------------------
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_STATUS_RE = re.compile(r"\*\*Status:\*\*\s*([^\n|<]+)", re.IGNORECASE)
_SUPERSEDE_RE = re.compile(r"\*\*Supersedes / superseded by:\*\*\s*(.+)", re.IGNORECASE)


def _collapse(text: str) -> str:
    """Flatten an ADR section to one whitespace-normalized line (bullets, links and
    line breaks become spaces) so it stores compactly and matches as a substring."""
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class Adr:
    id: str
    title: str
    status: str            # lifecycle, taken from the folder (the README's truth)
    header_status: str     # the status line text inside the file (cross-check)
    reasoning: str         # ## Context — the forces / why
    decision: str          # ## Decision (also "Decision (proposed/now deprecated)")
    alternatives: str      # ## Alternatives considered (or "Why rejected" for rejected ADRs)
    risks: str             # ## Consequences & risks (or "Consequences")
    evolution: str         # ## Why deprecated — the historical reasoning for a retirement
    supersede: str         # supersedes / superseded-by line (historical link)
    path: str

    def history_text(self) -> str:
        """The historical-context narrative: the supersession link plus, for a
        retired decision, why it was deprecated."""
        parts = []
        if self.supersede and self.supersede not in {"—", "-"}:
            parts.append(self.supersede)
        if self.evolution:
            parts.append(self.evolution)
        return " ".join(parts).strip()

    def record_text(self) -> str:
        """The episodic memory content for this ADR: its reasoning rendered into the
        EXISTING content field as plain structured text (no new schema). Fields are
        ordered by importance so that if the manager's 2000-char cap bites, it drops
        the least-critical tail last, never the decision or reasoning."""
        parts = [f"ADR {self.id} [{self.status}] {self.title}"]
        if self.decision:
            parts.append(f"Decision: {self.decision}")
        if self.reasoning:
            parts.append(f"Reasoning: {self.reasoning}")
        if self.alternatives:
            parts.append(f"Alternatives considered: {self.alternatives}")
        if self.risks:
            parts.append(f"Risks and consequences: {self.risks}")
        history = self.history_text()
        if history:
            parts.append(f"History: {history}")
        return "\n".join(parts)


def _parse_adr(path: Path, status_folder: str) -> Adr | None:
    raw = path.read_text(encoding="utf-8")
    first = raw.splitlines()[0] if raw.splitlines() else ""
    m = re.match(r"#\s*([0-9]{3,})\s*[—-]\s*(.+)", first)
    if not m:
        return None
    adr_id, title = m.group(1), m.group(2).strip()

    # split the body into ## sections
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(raw))
    for i, sm in enumerate(matches):
        head = sm.group(1).strip().lower()
        body_start = sm.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        sections[head] = _collapse(raw[body_start:body_end])

    def section(*needles: str) -> str:
        for head, body in sections.items():
            if any(n in head for n in needles):
                return body
        return ""

    status_m = _STATUS_RE.search(raw)
    supersede_m = _SUPERSEDE_RE.search(raw)
    return Adr(
        id=adr_id,
        title=title,
        status=status_folder,
        header_status=_collapse(status_m.group(1)) if status_m else "",
        reasoning=section("context"),
        decision=section("decision"),
        # "Alternatives considered" on template ADRs; a rejected ADR frames the same
        # tradeoff analysis as "Why rejected" / "Why not".
        alternatives=section("alternative", "why rejected", "why not"),
        risks=section("consequence", "risk"),
        # a deprecated ADR records its retirement reasoning under "Why deprecated" —
        # historical context, not an alternative.
        evolution=section("why deprecated"),
        supersede=_collapse(supersede_m.group(1)) if supersede_m else "",
        path=str(path),
    )


def _repo_root() -> Path:
    """Walk up from this file to the repo root (the ancestor holding docs/decisions).

    foundation.paths.get_root() anchors on backend/ (its pyproject marker), so it
    points one level below the monorepo root where docs/ lives — hence this local
    walk instead.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / "docs" / "decisions").is_dir():
            return parent
    raise FileNotFoundError("could not locate docs/decisions from the harness path")


def _load_adrs() -> list[Adr]:
    root = _repo_root() / "docs" / "decisions"
    adrs: list[Adr] = []
    for folder in _LIFECYCLE_FOLDERS:
        for path in sorted((root / folder).glob(_ADR_GLOB)):
            adr = _parse_adr(path, folder)
            if adr:
                adrs.append(adr)
    adrs.sort(key=lambda a: a.id)
    return adrs


# --------------------------------------------------------------------------
# Recall question — references the decision's subject (title + decision), then asks
# the institutional-memory questions. It deliberately does NOT contain the
# alternatives/risks text, so recalling those is a genuine retrieval result, not an
# echo of the query.
# --------------------------------------------------------------------------
def _question_for(adr: Adr) -> str:
    return (
        f"For this project, why was the decision '{adr.title}' made? "
        f"{adr.decision} "
        "What alternatives were considered, what risks or tradeoffs were "
        "identified, and who proposed it?"
    )


# --------------------------------------------------------------------------
# Outcome of probing one ADR.
# --------------------------------------------------------------------------
@dataclass
class Probe:
    adr: Adr
    degraded: bool = False
    top_id: str = ""           # ADR id of the top-ranked recalled item ("" = none)
    top_is_target: bool = False
    target_recalled: bool = False  # target ADR present anywhere in the package
    leaked_rival: bool = False
    raw_cosine_target: float = 0.0
    raw_cosine_rival: float = 0.0  # the relevance the rival's copy WOULD have had
    # which fields the SOURCE ADR actually records (absent != recall loss)
    src_has_alternatives: bool = False
    src_has_risks: bool = False
    src_has_history: bool = False
    # which fields of the target survived into the recalled content
    has_decision: bool = False
    has_reasoning: bool = False
    has_alternatives: bool = False
    has_risks: bool = False
    has_status: bool = False
    has_history: bool = False
    recalled_chars: int = 0
    truncated: bool = False     # the stored record hit the manager's content cap


@dataclass
class Outcome:
    adrs: list[Adr] = field(default_factory=list)
    probes: list[Probe] = field(default_factory=list)
    ingested_ids: tuple[str, ...] = ()
    rival_id: str = ""


_ADR_ID_RE = re.compile(r"^ADR\s+([0-9]{3,})")


def _adr_id_of(content: str) -> str:
    m = _ADR_ID_RE.match(content)
    return m.group(1) if m else ""


def _snippet(text: str, n: int = 48) -> str:
    return _collapse(text)[:n]


async def _ingest_and_probe() -> Outcome:
    adrs = _load_adrs()
    out = Outcome(adrs=adrs)
    if len(adrs) < _MIN_ADRS:
        return out

    mgr = MemoryManager()  # fresh instance for isolation

    # --- Ingest every ADR for the architect through the REAL write door. Episodic
    # proposals are not gated by the semantic/procedural confidence floor, so each
    # record persists exactly as written.
    for adr in adrs:
        await mgr.record_write_proposals(ARCHITECT, SESSION, [MemoryWriteProposal(
            store=MemoryStore.EPISODIC,
            content=adr.record_text(),
            rationale=f"ADR {adr.id} ({adr.status}) ingested from {Path(adr.path).name}",
            confidence=0.9,
        )])
    out.ingested_ids = tuple(a.id for a in adrs)

    # --- A second tenant records the SAME first ADR (plus a sentinel). It would rank
    # highly for that decision's question, so its exclusion proves the user_id scope,
    # not relevance, keeps it out.
    rival_adr = adrs[0]
    out.rival_id = rival_adr.id
    rival_content = f"{rival_adr.record_text()}\nTenant: {_RIVAL_SENTINEL}"
    await mgr.record_write_proposals(RIVAL, "rival-session", [MemoryWriteProposal(
        store=MemoryStore.EPISODIC, content=rival_content,
        rationale="rival tenant copy", confidence=0.9,
    )])

    # --- Probe a representative set of decisions (capped) with recall questions.
    probed = _select_probes(adrs)
    for adr in probed:
        out.probes.append(await _probe_one(mgr, adr, rival_content))
    return out


def _select_probes(adrs: list[Adr]) -> list[Adr]:
    """Pick up to _PROBE_COUNT decisions, preferring lifecycle spread (one per
    status first) so the report exercises accepted AND superseded/rejected records."""
    by_status: dict[str, list[Adr]] = {}
    for a in adrs:
        by_status.setdefault(a.status, []).append(a)
    picked: list[Adr] = []
    # first pass: one from each lifecycle state present, in folder order
    for folder in _LIFECYCLE_FOLDERS:
        if by_status.get(folder):
            picked.append(by_status[folder][0])
    # second pass: fill remaining slots in id order, skipping already-picked
    for a in adrs:
        if len(picked) >= _PROBE_COUNT:
            break
        if a not in picked:
            picked.append(a)
    picked.sort(key=lambda a: a.id)
    return picked[:_PROBE_COUNT]


async def _probe_one(mgr: MemoryManager, adr: Adr, rival_content: str) -> Probe:
    question = _question_for(adr)
    pkg = await mgr.hydrate(HydrationRequest(
        session_id="recall-session",
        user_id=ARCHITECT,
        normalized=NormalizedInput(modality="text", content_type="text/plain", content=question),
        token_budget=_READ_BUDGET,
    ))
    p = Probe(
        adr=adr, degraded=pkg.degraded,
        src_has_alternatives=bool(adr.alternatives),
        src_has_risks=bool(adr.risks),
        src_has_history=bool(adr.history_text()),
    )

    qvec = _lex_embed(question)
    p.raw_cosine_target = _cosine(qvec, _lex_embed(adr.record_text()))
    p.raw_cosine_rival = _cosine(qvec, _lex_embed(rival_content))
    # the rival tenant's record must NOT appear in this user's recalled package
    p.leaked_rival = any(_RIVAL_SENTINEL in i.content for i in pkg.items)

    items = [i for i in pkg.items if i.store == MemoryStore.EPISODIC]
    if items:
        p.top_id = _adr_id_of(items[0].content)
        p.top_is_target = p.top_id == adr.id
    target_content = ""
    for item in items:
        if _adr_id_of(item.content) == adr.id:
            p.target_recalled = True
            target_content = item.content
    p.recalled_chars = len(target_content)
    # The manager stores content.strip()[:_MAX_CONTENT_CHARS]; a record at the cap
    # was truncated, so a missing tail field is a cap loss, not an authoring gap.
    p.truncated = p.recalled_chars >= _MAX_CONTENT_CHARS

    if target_content:
        p.has_decision = bool(adr.decision) and _snippet(adr.decision) in target_content
        p.has_reasoning = bool(adr.reasoning) and _snippet(adr.reasoning) in target_content
        p.has_alternatives = p.src_has_alternatives and _snippet(adr.alternatives) in target_content
        p.has_risks = p.src_has_risks and _snippet(adr.risks) in target_content
        p.has_history = p.src_has_history and _snippet(adr.history_text()) in target_content
        p.has_status = adr.status in target_content.lower() or f"[{adr.status}]" in target_content

    return p


def _run() -> tuple[Outcome, BenchmarkReport]:
    fake = _FakeStore()
    with ExitStack() as stack:
        stack.enter_context(patch.object(store_mod, "search", fake.search))
        stack.enter_context(patch.object(store_mod, "upsert", fake.upsert))
        stack.enter_context(patch.object(store_mod, "is_down", fake.is_down))
        stack.enter_context(patch.object(embeddings_mod, "embed", _fake_embed))
        outcome = asyncio.run(_ingest_and_probe())
    return outcome, _build_report(outcome)


# --------------------------------------------------------------------------
# Requirement scoring -> structured report.
# --------------------------------------------------------------------------
def _build_report(o: Outcome) -> BenchmarkReport:
    report = BenchmarkReport(
        benchmark_id="C4",
        title="Institutional Decision Memory",
        requirement_summary="decision / reasoning / tradeoffs / participants / historical-context",
    )

    if len(o.adrs) < _MIN_ADRS or not o.probes:
        report.add_requirement(
            "decision", "Preserve the decision", Verdict.FAIL,
            f"only {len(o.adrs)} ADR(s) found under docs/decisions (need >= {_MIN_ADRS}); "
            "cannot exercise decision recall.")
        report.add_note("harness could not locate enough ADRs to ingest — check docs/decisions/.")
        return report

    n = len(o.probes)
    degraded = [p for p in o.probes if p.degraded]
    retrieved_top = [p for p in o.probes if p.top_is_target]
    recalled = [p for p in o.probes if p.target_recalled]
    leaks = [p for p in o.probes if p.leaked_rival]

    def count(attr: str) -> int:
        return sum(1 for p in o.probes if getattr(p, attr))

    # --- decision: the decision itself is recalled as the top hit, scoped --------
    if degraded:
        report.add_requirement(
            "decision", "Preserve the decision", Verdict.FAIL,
            f"{len(degraded)}/{n} probes degraded; memory was unavailable, not recalled.")
    elif len(retrieved_top) == n and count("has_decision") == n and not leaks:
        report.add_requirement(
            "decision", "Preserve the decision", Verdict.PASS,
            f"all {n} probed decisions were recalled as the TOP hit in a fresh "
            "session (no transcript), scoped to the architect's user_id, with the "
            "decision statement intact in the recalled record; a second tenant's "
            "copy of the same decision was scoped out.",
            tuple(f"ADR {p.adr.id}: top hit, decision present (raw cos {p.raw_cosine_target:.2f})"
                  for p in o.probes))
    elif len(recalled) == n and count("has_decision") == n:
        report.add_requirement(
            "decision", "Preserve the decision", Verdict.PARTIAL,
            f"all {n} decisions were recalled with the decision statement intact, but "
            f"only {len(retrieved_top)}/{n} ranked as the TOP hit — retrieval order is "
            "imperfect for topically-close decisions.")
    else:
        report.add_requirement(
            "decision", "Preserve the decision", Verdict.FAIL,
            f"only {len(recalled)}/{n} decisions recalled, {count('has_decision')}/{n} with "
            "the decision text intact — the final outcome is being lost.")

    # --- reasoning: the WHY (Context) rides the recalled record ------------------
    r_ok = count("has_reasoning")
    if r_ok == n and len(recalled) == n:
        report.add_requirement(
            "reasoning", "Preserve the reasoning", Verdict.PASS,
            f"the Context/why-it-was-decided text was recalled for all {n} decisions, "
            "attached to the decision and retrieved by a question that did NOT contain "
            "it — reasoning persists, not just the outcome.",
            tuple(f"ADR {p.adr.id}: reasoning recalled" for p in o.probes if p.has_reasoning))
    elif r_ok:
        report.add_requirement(
            "reasoning", "Preserve the reasoning", Verdict.PARTIAL,
            f"reasoning recalled for {r_ok}/{n} decisions; the rest lost their Context "
            "text (truncated by the 2000-char content cap or not parsed).")
    else:
        report.add_requirement(
            "reasoning", "Preserve the reasoning", Verdict.FAIL,
            "no decision's reasoning survived retrieval — only outcomes remain.")

    # --- tradeoffs: alternatives + risks recalled, but as prose not typed records -
    # Score recall over the decisions that ACTUALLY record each section: an ADR with
    # no "Alternatives considered" (a deprecated retirement note) is an authoring gap,
    # not a recall loss, and is reported as such rather than counted against recall.
    alt_src = [p for p in o.probes if p.src_has_alternatives]
    risk_src = [p for p in o.probes if p.src_has_risks]
    a_ok = sum(1 for p in alt_src if p.has_alternatives)
    k_ok = sum(1 for p in risk_src if p.has_risks)
    a_trunc = sum(1 for p in alt_src if not p.has_alternatives and p.truncated)
    k_trunc = sum(1 for p in risk_src if not p.has_risks and p.truncated)
    no_alt = n - len(alt_src)
    no_risk = n - len(risk_src)
    alt_line = f"alternatives recalled {a_ok}/{len(alt_src)} of decisions that record them"
    risk_line = f"risks recalled {k_ok}/{len(risk_src)} of decisions that record them"
    absence = []
    if no_alt:
        absence.append(f"no alternatives section in {no_alt}/{n}")
    if no_risk:
        absence.append(f"no risks/consequences section in {no_risk}/{n}")
    absence_note = (
        " Authoring variance: " + "; ".join(absence) + " probed decisions (not a recall loss)."
    ) if absence else ""
    trunc_note = ""
    if a_trunc or k_trunc:
        trunc_note = f" {a_trunc + k_trunc} field(s) were lost to the 2000-char content cap."
    if a_ok == len(alt_src) and k_ok == len(risk_src) and (alt_src or risk_src):
        report.add_requirement(
            "tradeoffs", "Preserve tradeoffs (alternatives + risks)", Verdict.PARTIAL,
            f"every recorded tradeoff was recalled ({alt_line}; {risk_line}).{absence_note} "
            "Marked PARTIAL because the alternatives + risks ride as prose inside one "
            "episodic blob, NOT first-class, separately queryable typed tradeoff "
            "records; that structuring is gated on issue #16.",
            (alt_line, risk_line))
    elif a_ok or k_ok:
        report.add_requirement(
            "tradeoffs", "Preserve tradeoffs (alternatives + risks)", Verdict.PARTIAL,
            f"{alt_line}; {risk_line}.{trunc_note}{absence_note} Tradeoffs are prose, not "
            "typed records (gated on #16).",
            (alt_line, risk_line))
    else:
        report.add_requirement(
            "tradeoffs", "Preserve tradeoffs (alternatives + risks)", Verdict.FAIL,
            "no recorded alternatives or risks survived retrieval — the debate is lost.")

    # --- participants: NOT-YET by design (ADRs carry no proposer; gated on #16) --
    report.add_requirement(
        "participants", "Preserve participants (who proposed it)", Verdict.NOT_YET,
        "ADRs record an Authority tier and a Source document, but no proposer / "
        "author / discussion participants, so 'who proposed it' cannot be answered "
        "from the record. First-class provenance (proposer, participants, linkage) "
        "is the typed-knowledge-record capability gated on issue #16; this harness "
        "MEASURES the gap and does not implement it.")

    # --- historical-context: status + supersession recalled as text, not linked ---
    s_ok = count("has_status")
    hist_src = [p for p in o.probes if p.src_has_history]
    h_ok = sum(1 for p in hist_src if p.has_history)
    statuses = sorted({p.adr.status for p in o.probes})
    hist_line = (
        f"supersession/retirement note recalled {h_ok}/{len(hist_src)} of decisions that "
        "carry one" if hist_src else "no probed decision carries a supersession note")
    report.add_requirement(
        "historical_context", "Preserve historical context (status + supersession)",
        Verdict.PARTIAL,
        f"each recalled record carries its lifecycle status ({s_ok}/{n}; probed states: "
        f"{', '.join(statuses)}) and {hist_line}, as text. Marked PARTIAL: there is NO "
        "typed supersession / temporal-validity LINK — a deprecated decision and the one "
        "that replaced it come back as unrelated peers. Temporal linkage is Exceptional "
        "Benchmark 1, gated on issue #16.",
        (f"status recalled {s_ok}/{n}", hist_line))

    # --- per-case rows -------------------------------------------------------
    # field flag legend: UPPER = recalled, x = recorded but not recalled (a loss),
    # · = the ADR records no such section (authoring variance, not a loss).
    def flag(letter: str, recalled: bool, present: bool = True) -> str:
        if recalled:
            return letter
        return "x" if present else "·"
    for p in o.probes:
        flags = "".join((
            flag("D", p.has_decision),
            flag("R", p.has_reasoning),
            flag("A", p.has_alternatives, p.src_has_alternatives),
            flag("K", p.has_risks, p.src_has_risks),
            flag("S", p.has_status),
        ))
        outcome_label = "recalled" if p.top_is_target else ("ranked#?" if p.target_recalled else "MISSING!")
        report.add_case(
            f"ADR-{p.adr.id}", outcome_label,
            f"[{p.adr.status}] fields(DRAKS)={flags} top={p.top_id or '∅'} "
            f"cos={p.raw_cosine_target:.2f} chars={p.recalled_chars}")
    rival_probe = next((p for p in o.probes if p.adr.id == o.rival_id), None)
    rival_cos = rival_probe.raw_cosine_rival if rival_probe else 0.0
    report.add_case(
        f"rival-ADR-{o.rival_id}",
        "excluded" if not leaks else "LEAKED!",
        f"second tenant's copy of the same decision, scoped out by user_id "
        f"(would-rank cos={rival_cos:.2f}, well above the 0.30 floor — excluded by "
        "scope, not relevance)")

    # --- honesty notes -------------------------------------------------------
    report.add_note(
        f"ingested {len(o.ingested_ids)} real ADRs (docs/decisions/*/{_ADR_GLOB}) for "
        f"{ARCHITECT} via the real MemoryPort.record_write_proposals door, storing each "
        "decision's reasoning/alternatives/risks in the EXISTING episodic content "
        "field — NO new EntryType, NO schema change (gated on issue #16).")
    report.add_note(
        f"probed {n} decisions across lifecycle states ({', '.join(statuses)}) with "
        "why/alternatives/risks/who questions through MemoryPort.hydrate in a fresh "
        "session with no transcript; the questions reference each decision's subject "
        "but NOT its alternatives/risks text, so recalling those is genuine retrieval.")
    report.add_note(
        "hermetic doubles: an in-memory user_id-scoped store double (Qdrant) and a "
        "deterministic lexical embedder (nomic) — the exact seams the real manager "
        "calls. The REAL MemoryManager write/read paths, the user_id scope filter, "
        "the 0.30 relevance floor, recency weighting and the water-filling budget all "
        "run unchanged. No network, model download, or Qdrant container.")
    report.add_note(
        "participants is NOT-YET and tradeoffs/historical-context are PARTIAL BY "
        "DESIGN: ADRs carry no proposer, and alternatives/risks/supersession are "
        "recalled as prose, not first-class typed/linked records. Typed decision "
        "records are gated on issue #16; this harness MEASURES the gap.")
    report.add_note("serves Critical Benchmark 4 and Pillar 1 (institutional decision memory).")
    return report


# --------------------------------------------------------------------------
# Cached single run (the ingest+probe is identical across tests).
# --------------------------------------------------------------------------
_CACHE: tuple[Outcome, BenchmarkReport] | None = None


def results() -> tuple[Outcome, BenchmarkReport]:
    global _CACHE
    if _CACHE is None:
        _CACHE = _run()
    return _CACHE


def run() -> BenchmarkReport:
    """Public entry point for the consolidated scoreboard / standalone use."""
    return results()[1]


# --------------------------------------------------------------------------
# pytest acceptance tests.
# --------------------------------------------------------------------------
def test_at_least_three_real_adrs_are_ingested():
    outcome, _ = results()
    assert len(outcome.adrs) >= _MIN_ADRS, (
        f"need >= {_MIN_ADRS} ADRs under docs/decisions; found {len(outcome.adrs)}")
    assert len(outcome.probes) >= _MIN_ADRS, "fewer than three decisions were probed"


def test_each_probed_decision_is_recalled_as_top_hit_scoped_to_user():
    outcome, report = results()
    for p in outcome.probes:
        assert not p.degraded, f"ADR {p.adr.id}: hydration degraded"
        assert p.target_recalled, f"ADR {p.adr.id} was ingested but not recalled\n{report.render()}"
        assert p.top_is_target, (
            f"ADR {p.adr.id} was not the top hit (got {p.top_id})\n{report.render()}")
        assert p.raw_cosine_target >= 0.30, (
            f"ADR {p.adr.id} target cosine {p.raw_cosine_target:.2f} below the 0.30 floor")


def test_a_second_tenant_copy_of_the_same_decision_never_leaks():
    outcome, _ = results()
    rival_probe = next((p for p in outcome.probes if p.adr.id == outcome.rival_id), None)
    assert rival_probe is not None, (
        "the rival's decision should be among the probed set to test scope")
    # the rival's copy is identical content, so it WOULD rank above the floor for its
    # decision's question — exclusion must therefore be the user_id scope, not relevance.
    assert rival_probe.raw_cosine_rival >= 0.30
    for p in outcome.probes:
        assert not p.leaked_rival, f"ADR {p.adr.id}: a second tenant's record leaked into recall"


def test_reasoning_and_alternatives_are_recalled_with_each_decision():
    outcome, report = results()
    # every probed ADR records a Context (reasoning) and a Decision; assert those
    # always survive. Alternatives/risks are asserted only where the source ADR
    # records them (a deprecated retirement note legitimately has neither).
    for p in outcome.probes:
        assert p.has_decision, f"ADR {p.adr.id}: decision statement lost\n{report.render()}"
        assert p.has_reasoning, f"ADR {p.adr.id}: reasoning (Context) lost\n{report.render()}"
        if p.src_has_alternatives:
            assert p.has_alternatives, f"ADR {p.adr.id}: recorded alternatives lost\n{report.render()}"
        if p.src_has_risks:
            assert p.has_risks, f"ADR {p.adr.id}: recorded risks lost\n{report.render()}"
    # the harness must actually exercise alternatives recall on real records
    assert sum(p.src_has_alternatives for p in outcome.probes) >= _MIN_ADRS, (
        "fewer than three probed decisions record an alternatives section")


def test_report_maps_five_c4_requirements_and_marks_reasoning_and_tradeoffs():
    _, report = results()
    keys = {r.key for r in report.requirements}
    assert keys == {"decision", "reasoning", "tradeoffs",
                    "participants", "historical_context"}, keys
    by_key = {r.key: r for r in report.requirements}
    # the task's headline: reasoning + alternatives (tradeoffs) recall is PASS/PARTIAL
    assert by_key["reasoning"].verdict in {Verdict.PASS, Verdict.PARTIAL}, "\n" + report.render()
    assert by_key["tradeoffs"].verdict in {Verdict.PASS, Verdict.PARTIAL}, "\n" + report.render()
    # the decision itself is recalled...
    assert by_key["decision"].verdict in {Verdict.PASS, Verdict.PARTIAL}, "\n" + report.render()
    # ...and the #16-gated capability is honestly NOT-YET, never faked
    assert by_key["participants"].verdict is Verdict.NOT_YET
    # no requirement is a genuine defect; PARTIAL is the honest end-to-end read
    assert not report.has_failure(), "\n" + report.render()
    assert report.overall() is Verdict.PARTIAL


def test_no_new_memory_schema_is_introduced():
    """C4's OWN ADR-ingestion path (this file) must use existing primitives only:
    episodic tier + the documented MemoryWriteProposal fields. Guard against a
    regression that sneaks a new tier or a non-existent proposal field into ITS
    ingest path specifically — not a freeze on the contract forever.

    `participants` is a deliberate, ratified exception: the CB4 storage layer
    (core/memory, 2026-07-05) added it to carry who-was-involved on a
    `kind=DECISION` write. This harness doesn't use DECISION yet (it ingests ADRs
    as plain EPISODIC prose — the orchestrator bridge from a real DecisionRecord
    to a `kind=DECISION` proposal isn't wired here), so the field is listed but
    inert for this path; the assertion is updated to the real contract, not
    loosened to `>=`, so a genuinely accidental future field still fails here."""
    proposal = MemoryWriteProposal(store=MemoryStore.EPISODIC, content="x", confidence=0.9)
    assert set(MemoryStore.__members__) >= {"WIKI", "SEMANTIC", "EPISODIC", "PROCEDURAL", "WORKING"}
    assert {f for f in proposal.__dataclass_fields__} == {
        "store", "content", "rationale", "confidence", "kind", "valid_at", "source", "participants"
    }


def test_report_renders_structured_block(capsys):
    _, report = results()
    print(report.render())
    captured = capsys.readouterr().out
    assert "BENCHMARK C4" in captured
    assert "OVERALL:" in captured
    for key in ("decision", "reasoning", "tradeoffs", "participants", "historical_context"):
        assert key in captured
    assert "NOT-YET" in captured  # the gated requirement is visible as a gap


def main() -> int:
    report = run()
    print(report.render())
    return 1 if report.has_failure() else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
