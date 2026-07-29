# Shared provider handoff — backend

Transfers live backend-coordinator work between Claude Code and Codex.

**If you are a fresh Codex session: read this whole file, then the boot sequence
at the top of `AGENTS.md`.** Nothing is injected into your session at launch —
`crew.sh start backend --codex` runs plain `codex` in the repo root, so what you
know is exactly what you read. This file is written for that.

---

## THE MENTAL MODEL — read this even if you skip the rest

Durable framing. It does not change week to week, and it is what makes the
detailed docs make sense.

**What Clannon is.** A production monorepo: a Python backend (pipeline →
orchestrator → experts/tools, with memory, security and an API/SSE surface) and a
Next.js frontend. Not a prototype — it is built to production standards
throughout, which is why `LAW/README.md` exists and outranks every other doc.

**Where we are.** V1 is **not done and has never faced a real user.** That single
fact decides most arguments. It is why new work stays in Python (no second
toolchain tax on an unfinished product), why "ship it to users" is a live open
question, and why stability outranks new surface area.

**The bar we are building to.** Six Critical + three Exceptional benchmarks in
`docs/benchmarks/CLANNON_V1_ATTENTION_THRESHOLD.md` (the owner's spec of the bar
— it carries no status, deliberately). Honest verdicts live in exactly one place:
`docs/benchmarks/V1_GAP_ANALYSIS.md`. As of 2026-07-28: **CB6 PASS, five
PARTIAL.** The outreach gate is all six Critical passing plus one Exceptional.

**Your role.** You are the **coordinator**, not a labour agent. The owner has
been explicit: *"you are a DICTATOR, not a labor!"* Your context is the scarce
resource. You own `foundation/`, `core/pipeline.py`, `delivery/`, `config/`,
`scripts/`, `docs/`, and final integration + merge authority. You are the **sole
committer and pusher** — specialists produce scoped diffs; you review, test,
commit, and push.

**How work actually gets done.** Five specialists own disjoint trees
(memory, orchestration, security, api, frontend) and coordinate hub-and-spoke
through you, never with each other. You delegate through **headless workers**
(`./scripts/crew.sh run <role> --brief <file> --dir <paths>`); workers never
commit or push. You review the diff, run the suite, commit, and push. Finding
work outside your tree is the START of a task, not the end of it — file the
proposal AND dispatch AND push it. See the
"THAT'S X'S JOB" section in `CLAUDE.md`.

**Messaging is PULL, never push.** Nothing injects into a running session. You
check `comms/<today>/` and `proposals/to-backend/` yourself, at session start and
after each unit of work. **Idle is a legitimate state** — the "never sit idle"
policy is retired and was the most expensive bad instruction we ever followed.

**You are expected to disagree.** Before acting on any instruction — the owner's
included — confirm it actually helps. Say so BEFORE the work, never after as an
excuse. The owner writes their thinking into `drafts/owner_thoughts/` expecting
pushback.

**Honesty is load-bearing.** PARTIAL means PARTIAL. A verdict you cannot
substantiate stays unchanged. Tests never fake a pass. This is LAW 7 and it is
the thing most worth protecting when you are tired or the work "should" have
finished something.

---

## Current checkpoint — private-alpha environment split (2026-07-29)

Owner requested separate local and production environment files for backend and
frontend. Frontend already had correct ignored `.env.local` / `.env.prod`; it
was inspected but not changed.

Backend now has:

- ignored `.env.local`, with existing secrets preserved and explicit
  development/lenient prompt profile appended;
- ignored `.env.prod`, a Railway RAW Editor template with fail-closed production
  mode, all three routed provider keys, exact `clannon.com` CORS/cookie contract,
  persistent `/data` paths, private ClamAV/Qdrant placeholders, hardened prompt
  overlay path, and code execution disabled;
- `.dockerignore` excludes every `.env*` except `.env.example`, closing local
  Docker-context secret leakage;
- synchronized root/backend/API docs. Raw `*.up.railway.app` browser API advice
  is removed; `api.clannon.com` is required by current SameSite=Lax topology.

Production template parses with 27 keys. Strict config smoke reports all four
checks OK with fake credentials and temporary writable storage. API specialist
ran `tests/config_validation.py`: 15 passed. Frontend proposal
`production-cookie-domain-contract` accepted and archived; actual DNS/browser
acceptance remains a deploy-time checklist, not falsely claimed.

Important deployment caveat: Railway mounts volumes as root while Docker image
runs as uid 10001. `/data` ownership must be fixed before testers.
`RAILWAY_RUN_UID=0` is documented only as temporary fallback. Upload
`backend/prompts.secure` to `/data/prompts.secure`; `.env.prod` is not
auto-loaded by Python.

Preserve unrelated owner changes in `CLAUDE.md`, `frontend/CLAUDE.md`, and
untracked `assets/Clannon Labs.png`.

## Change note

Environment files existed but production backend template was missing and
deployment docs recommended a cross-site Railway origin incompatible with
cookie auth. New split keeps secrets ignored, makes production assumptions
explicit, and leaves browser proof for real deployment.

## Previous checkpoint — revise edits same chat in place (2026-07-29)

Owner rejected initial non-destructive branch behavior. Correct behavior is now
implemented and verified:

- `POST /runs/{id}/revise` keeps target `sessionId` and `projectId`.
- Target's old prompt/response and every later effective turn become
  user-inaccessible (`404`) and disappear from `/runs`, `/thread`, model
  conversation, recall transcript, and inherited-file reseeding.
- Revised turn's parent is last retained turn, or null when root was edited.
- No discarded-turn hint reaches model. Only separately persisted project/account
  memory remains eligible.
- Superseded rows remain internal solely for already-spent token accounting, saved
  memory, and security/decision audit provenance. Marker never enters public JSON.
- Live descendants cancel and persist hidden. Atomic registration/write failure
  leaves original chat unchanged.
- Frontend copy explicitly warns response and later turns will be removed from same
  conversation. Mock and cache invalidation match backend.
- Initial accidental branch rows are left as legacy compatibility data; no unsafe
  mass migration guesses which original root they replaced.

Proof:

- backend full suite: `1571 passed, 1 existing RestrictedPython warning`;
- backend focused API suite: `143 passed`;
- frontend full suite: `93 passed`; correction-focused: `20 passed`;
- frontend typecheck, lint, production build passed;
- invariant checker: 7 PASS, one existing network-permission WARN.

All three active proposals (API correction, frontend correction, owner critique)
are completed and archived. Preserve unrelated owner changes in `CLAUDE.md`,
`frontend/CLAUDE.md`, and untracked logo asset.

## Change note

Initial implementation followed frontend proposal's “new branch, keep original”
wording too literally. Owner meant destructive conversation truncation. Soft
supersession delivers that user/model behavior without erasing billed usage,
saved memory, or security provenance.

## Previous checkpoint — rejected safe revise-turn branching (2026-07-29)

Frontend's high-priority proposal is implemented and verified:

- `POST /runs/{id}/revise` accepts edited `brief`, optional `models`, replacement
  `files`, and `reuseInputs` (default true).
- Revised run gets a new session plus persisted owner/project-scoped lineage
  prefix. No historical rows are cloned or mutated.
- One effective-thread resolver drives `/thread`, model conversation, recall
  transcript, and inherited-file reseeding. Old target and later descendants do
  not enter revised context.
- Follow-ups on revised branch retain inherited prefix. Original branch remains
  readable.
- Target input reuse reads only target-owned server artifact namespace. New
  inputs carry SHA-256; legacy inputs remain reusable through namespace + size
  validation. Missing, malformed, redirected, or hash-mismatched inputs return
  actionable 409 before run creation.
- Revision route/request helpers live in focused modules. `app.py` is still
  pre-existing LAW 2 debt at 748 lines, but this change reduced it from baseline
  777 rather than growing it to worker draft's 834.

Proof:

- backend full suite: `1566 passed, 1 existing RestrictedPython warning`;
- focused revision/lifecycle/API suite: `96 passed`;
- frontend revision UI tests: `19 passed`; TypeScript check passed;
- invariant checker: 7 PASS, one existing network-permission WARN;
- live proxied `/api/health` OK and OpenAPI contains revise route.

Pending integration only: review final status, commit API/tests/comms/handoff,
push. Preserve unrelated owner changes in `CLAUDE.md`, `frontend/CLAUDE.md`, and
untracked assets.

## Change note

Existing follow-up was linear and would leak descendants after edited turn into
model and file context. New persisted lineage fixes branch semantics without
duplicating usage/audit rows. Coordinator review preserved legacy file reuse and
reduced oversized route file.

## Previous checkpoint — chat/report intent + orchestrator prompts (2026-07-29)

Owner-confirmed behavior is implemented, tested, and committed locally:

- `900e2cc` routes accepted API answers by typed presentation.
- `b842ad8` points API development docs at root launcher.
- `dfcd212` adds required `chat | report` intent to orchestrator contracts,
  removes length/tool/Markdown/`say()` heuristics, keeps filtered delivery in both
  modes, and resolves buffered artifact content only for report presentation.
- `e53bb29` lands canonical root `dev.sh`, same-origin `/api` proxy, dependency
  startup/readiness, component-launcher removal, and synchronized run docs.
- `217f7eb` rebuilds central orchestrator prompt v5 from owner's 1603-line
  structural reference and adds registry-backed batch prompt v1. Engineering
  batch no longer uses hardcoded two-sentence fallback.

Product semantics now:

- Direct, casual, ordinary, long technical, tool-assisted, and research-summary
  answers render as open filtered chat.
- Inline report sheet appears only when user explicitly requested/needed an
  inline report.
- Generated files/documents/charts remain artifacts, never automatic reports.
- `say()` is sparse live commentary for genuinely long expert/batch work. Quick
  answers do not call it. Long work final may be chat or report by output intent.
- Weak-model accidental trivial `say()` cannot create second report.

Proof:

- Full backend: `1551 passed, 1 existing RestrictedPython warning`.
- Chat/report combined focused suite: `92 passed`.
- Prompt/orchestration/batch focused suite: `225 passed`.
- Frontend: `npm run lint` and `npm run typecheck` passed.
- Live Claude Haiku 4.5 identity regression:
  `run_7722d656692a` delivered
  `"I'm Clannon, a memory-native research and workflow assistant built by the Clannon team."`
  as `message`; `report=null`; no experts; no `say()`.
- Live stack healthy: `http://192.168.18.84:3000`,
  `/api/health` through Next returns 200.

Active ignored overlay files were updated byte-identically with committed
baselines:
`backend/prompts.secure/orchestrator/system.md` and
`backend/prompts.secure/batch_orchestrator/system.md`.

Integration is ready to push. Do not include unrelated owner edits:
`CLAUDE.md`, `frontend/CLAUDE.md`, or `assets/Clannon Labs.png`.

## Change note

Old UI defect was deterministic backend routing, not a frontend styling failure:
any `say()` forced final answer into report. Typed intent now owns presentation,
and live Haiku verifies simple identity stays one casual chat reply. Owner prompt
guide changed prompt organization and examples, but incompatible Claude identity,
unavailable tools, provider policy, and environment-specific machinery were
deliberately excluded.

## Previous checkpoint — unified local launcher (2026-07-29)

**Pending owner confirmation:** casual `Who are you?` run
`run_f0c991d05200` exposed deterministic message/deliverable misrouting. Haiku
called `say()` with one introduction, then returned a second introduction as
`answer_text`; `_split_message_and_deliverable()` treats presence of any
`say()` as reason to route final answer into `report`. Filed linked pending
proposals to orchestration and frontend:
`2026-07-29_casual_answer_channel_routing.md` and
`2026-07-29_chat_vs_report_presentation.md`. Owner clarified: `say()` is final
voice for trivial conversation and progress/commentary for report work; both
channels are valid when jobs differ. Proposal now recommends explicit
presentation intent plus a security distinction for unfiltered `say()`. Owner
has not authorized implementation; do not dispatch before reply.

Owner asked for one root development launcher and synchronized run docs after a
real UI run failed before any model call. Diagnosis was ClamAV absent at
`127.0.0.1:3310`; persisted run log said `ClamAV scanner was unavailable during
the security scan`. Embeddings also pointed at stale `/mnt/win_c`.

Implemented, uncommitted:

- Added executable root `dev.sh`, canonical full-stack entry point.
- Removed duplicate `backend/dev.sh` and `frontend/dev.sh`;
  `frontend/package.json`'s `npm run lan` now calls `../dev.sh`.
- Root launcher starts/reuses persistent ClamAV + Qdrant containers through
  Docker or Podman, waits for real protocol readiness, uses local embedding
  cache, replaces only repo-owned stale app listeners, starts FastAPI privately
  on `127.0.0.1:8000`, starts Next on LAN `:3000`, and owns cleanup.
- `frontend/next.config.ts` proxies dev-only `/api/*` to private FastAPI when
  `CLANNON_DEV_BACKEND_URL` is set. Browser now sees one origin/port.
- Synchronized local-run instructions in `README.md`, `RELEASE.md`,
  `backend/README.md`, `backend/api/README.md`, `frontend/README.md`, and
  `frontend/BACKEND_INTEGRATION.md`.

Live proof:

- Root launcher cold-started Podman containers `clannon-dev-clamav` and
  `clannon-dev-qdrant`; second start reused them.
- `http://192.168.18.84:3000/api/health` returned OK through Next proxy.
- `/api/ready` returned Qdrant, embeddings, DB all `up`.
- `/api/auth/me` returned expected 401 without cookie through proxy; existing
  browser session returned 200, proving cookie forwarding.
- Direct real `ClamScanner` clean probe passed.
- `npm run typecheck`, `bash -n dev.sh`, and `git diff --check` passed.
- Cleanup test closed ports 3000/8000 while retaining warm service containers.
- Stack restarted and remains running at `http://192.168.18.84:3000`.

No commit/push requested. Worktree also contains concurrent changes NOT made by
backend: `.agents/provider-handoffs/frontend.md`, `frontend/CLAUDE.md`, and one
line in `frontend/BACKEND_INTEGRATION.md` changing “Claude Code” to “Claude
Code/codex”. Preserve them.

## Previous change note

Local startup previously required two scripts plus separately managed services.
That let frontend appear healthy while every run failed closed at absent ClamAV,
and direct LAN API wiring created two browser origins. Root launcher now owns
complete dependency/application startup while FastAPI remains on its required
distinct internal TCP port.

## Previous checkpoint — PAUSED FOR A WEEK (2026-07-28 evening)

**The owner is taking a week off. Everything is committed and pushed; the tree is
clean apart from the frontend session's own uncommitted work, which is theirs and
must be left alone.** Nothing is half-finished. Start by re-reading this file and
`docs/ROADMAP.md`; do not resume from memory of what was "in progress", because
nothing is.

**Provider budgets at pause:** Codex is usage-limited until **Aug 4**. Claude's
weekly limit was nearly exhausted. `crew.sh run` now dispatches Claude workers on
`claude-sonnet-5`, matching the interactive specialist default — the quality net
is coordinator review of every diff, not the model tier.

### The one thing to carry forward

**CB5's PASS was claimed and reverted on the same day, and that is the lesson of
this whole session.** Five regex rules were added that matched the adversarial
battery's exact wording; the benchmark was tightened to "every attack flagged";
the row went green and was marked PASS. It was fitted to the fixture. The same
attack intent, mildly reworded, evades — verified by hand against live
`scan_text_risk`: the fixture string returns `['memory_poisoning']`, the
paraphrase returns `[]`.

Removing a rule *does* turn the suite red, so the test is not vacuous. It is
simply sensitive to frozen strings rather than to the attack class. That is a
subtler failure than a vacuous test and the ordinary mutation check does not
catch it — **the discriminating question is not "does the test fail when I break
the code", it is "does the test still pass when I change the input in a way the
threat model says should still be caught."**

Two comments had also drifted into asserting things that were not true
(`c5_security.py` claimed live certification that does not exist for those
payloads; `payloads.py` still called them "regex-evading" after rules were fitted
to catch them). Both corrected in `db6be4c`.

### What shipped today, after the earlier tranche

- **Honest completion** (`1e650e9`): `completionState` / `completionReason` on
  the run REST shape. A degraded run — timeout, rate-limit storm, fault — used to
  read as an unqualified `delivered` while its report said "couldn't finish in
  the time allowed". The orchestrator already tagged the response
  `{"degraded": True, "cause": kind}`; nothing read it. Three axes now, kept
  deliberately separate: `status` (lifecycle), `verificationState` (filter
  groundedness), `completionState` (did the loop finish). A degraded run is
  routinely all of `delivered` + `grounded` + `partial`, and all three are true.
- **CB5 reverted** (`db6be4c`) in four places that had each drifted separately.
- **Stranded Codex work landed** (`58a55f8`): `--no-alt-screen`, the owner's own
  prose in `BATCH_ARCHITECTURE.md` committed verbatim.

### Open when work resumes — nothing is blocked

**Every proposal inbox in the repo is empty.** The completion-state loop closed
before the pause: frontend shipped the UI (`9dc4d84`) — badge, reason-coded
banner, "Continue this run" — holding `completionState` as a genuinely separate
axis from `status`/`verificationState`, which was the part most likely to get
quietly collapsed. They asked whether to add a live `completion` SSE event;
**answered no.** The value only exists once a run is terminal and their live-run
hook already refetches on stream close, so the event would fire at the same
instant as the terminal `status` and carry nothing new — speculative surface
(LAW 1). Add it only if a real mid-run case appears, e.g. a long batch reporting
degradation before it terminates.

Still true and worth keeping in mind: `sse_contract_drift.py:479` fails on any
SSE event the frontend has not declared, and `:518` closes the "new terminal
`partial` status" option the same way. **Do not edit `types.ts` to unblock
yourself** — propose it and let frontend land it.

1. **CB5 detect** — prove the three C5-native families live in
   `scripts/prompt_regression.py`. Adding another regex shaped like the fixture
   would re-create exactly the failure that was just reverted.
2. Remaining benchmark gaps: `docs/ROADMAP.md` §2. Owner-gated: §5 (all answered
   as of today; `proposals/to-owner/` is empty).

### Previous state of this checkpoint

- Provider: Codex (interactive backend coordinator)
- Updated: **2026-07-28**
- Current integration tip includes the proposal-freshness sweep, ClamAV
  transport hardening, and live-Qdrant test-isolation repair. Full
  service-absent and live-Qdrant suites are recorded below.

### What this session did

**1. Reconciled benchmark + phase status with reality** (`b3ed4fb`, `00737ee`).
The status docs had drifted weeks behind the code, which is worse than having
none — agents follow them and work on finished things.
- **CB6 → PASS.** First Critical benchmark to pass. Verified directly, not on a
  worker's report: 8 tests, zero skips, and a deliberately mutated fixture (a
  bogus run_status) IS caught. Frontend tree clean, so the green reproduces from
  committed state.
- CB2/CB4/CB5 held at PARTIAL with named reasons. Only CB6 moved.
- Phases 0/3/4 → `docs/benchmarks/reached/`; phases 1/5 → in progress.
- Fixed a contradiction I had shipped myself: ROADMAP still told memory that CB1
  "needs `valid_at` typing" while the gap analysis in the same commit recorded it
  as landed.
- `reports/INTEGRATION_CONTRACT.md` is now **tracked** (it was gitignored while
  CB6's PASS depended on it existing). Note the mechanism: the pattern had to
  become `reports/*`, because git does not descend into an excluded directory and
  a `!` re-include inside one is silently dead.

**2. Corrected the Integration Contract via a dispatched api worker** (`6d31c52`).
It claimed exception/cancellation bypasses audit derivation; `run_driver.py:488`'s
`finally` covers every terminal status. Documented the real limitation instead
(incomplete `participants` on the crash path, `run_driver.py:498-505`) — still an
open CB4 gap.

**3. Tidied `reports/`** (`dbd8a31`). One folder per role, coordinator included —
`reports/backend/` now holds report_v1..v18, which had been sitting loose at the
root.

**4. Rewrote the old owner-decision docket** (`9a75de1`). This was later
superseded: live owner decisions now use one file each under
`proposals/to-owner/`; reports are information-only.

**5. Fixed `crew.sh` leaking its lock.** The EXIT trap was single-quoted, so
`$lock` expanded after the function returned and `local lock` was gone; under
`set -u` it aborted and the trap never fired. Symptom was only a stray error line
after successful runs, because a stale lock self-heals.

**6. Ran first existing-system hardening tranche** (`0b40607`, `13686e3`,
`60504c9`).
- CB5 was moved to PASS here — **that was wrong and has been reverted**
  (`db6be4c`). See the last checkpoint entry below; do not restore this claim.
- API cancellation/exception audit now preserves authoritative participants;
  foreign/unknown decision-run IDs share non-disclosing 404 proof.
- Same user/mission/expert workspace calls serialize restore → run → snapshot;
  unrelated keys stay concurrent; failure releases locks; idle locks disappear.
- Law-2 cleanup split workspace transactions and API source projection:
  production files now 481/41 and 498/39 lines.
- Central-config inventory reconciled: D1–D12 settled, Phase 3 substantially
  wired, D5 model centralization is next safe engineering work.
- Worker identities/routing corrected (`2f91e89`): backend-worker proposals go
  to `proposals/to-backend/from_workers/`; specialist workers use
  `<role>-worker` → `backend-coordinator` in `to-backend/`; dispatch briefs now
  live under `.agents/briefs/<role>/`.
- Owner decision routing migrated: reports are information-only; four live
  owner gates are individual standard proposals in `proposals/to-owner/`; all
  earlier owner archives live in `proposals/archive/to-owner/`.
- Three full suites passed during integration; latest: 1498 passed, 13 skipped.

**7. Swept every proposal inbox and executed genuine work.**
- Owner inbox was checked first with four unresolved decisions and no padding.
  Owner answered all four during the sweep; questions/replies are archived and
  ROADMAP §5 now truthfully says no actionable owner decision remains.
- Seven implemented specialist proposals and four settled owner work briefs
  were moved under `proposals/archive/`; archived headers now say `done`.
- API worker proved a real isolated PNG journey: real Anthropic + Gemini calls,
  53-second delivered run, SSE, media/docs experts, artifact, usage, audit,
  decisions, thread, CORS, and restart continuity.
- A healthy isolated backend remains available at `http://localhost:8000` for
  the context-holding frontend session's desktop + 390px browser pass. Frontend
  task is `proposals/to-frontend/2026-07-28_real-backend-browser-pass.md`; pull
  rules forbid injecting into its already-running interactive session.
- Live journey exposed ClamAV reset leakage. Security worker normalized socket
  refusal/reset/timeout/broken-pipe into fail-closed `SanitizationError`;
  regression lives in normal `backend/tests/`.
- A live-Qdrant full suite exposed test pollution, not product failure:
  `memory_store_concurrency.py` left `_SlowFakeClient` in module state. Memory
  workers reproduced exact predecessor failure and repaired globals with
  teardown-aware `monkeypatch`. A second exact failure proved
  `memory_supersession.py` leaked its deliberate fault's circuit-breaker
  deadline; it now restores the prior value too. Full isolated live-Qdrant
  suite: 1518 passed, 1 existing ClamAV skip.
- `crew.sh` worker-header examples used Markdown backticks inside an unquoted
  heredoc, executing `From:`/`To:` as shell commands. Literal quoting fixed it;
  a real security dispatch proved full worker identity survived.
- Owner ratified shared archive cap, parallel small-cohort feedback while
  engineering continues, and Python-first deferred Rust with a service-first /
  bounded-FFI boundary. One stale security comment was corrected; 35 focused
  tests passed.
- Provider-pricing audit rejected blind reference-copy. Current settlement
  loses cache/audio/per-request provider detail, charges fallback use against
  configured primary, cannot model tiers/effective dates/tools, and has 26
  routed IDs absent from pricing. `enforcement_enabled` stays false. This is
  engineering work in ROADMAP §2; owner gets a fresh go-live proposal only
  after evidence is green.
- Final clean service-absent suite: 1506 passed, 13 expected dependency skips,
  2 warnings. Isolated live-Qdrant suite: 1518 passed, 1 expected ClamAV skip.

### What is open, and who owns it

- **Owner-gated:** none actionable; `proposals/to-owner/` contains only its
  README. Final budget-enforcement go-live remains owner authority, but
  engineering gates are not green enough to ask yet.
- **Frontend action:** existing non-headless frontend session owns
  `proposals/to-frontend/2026-07-28_real-backend-browser-pass.md`. Backend is
  healthy and waiting; session must pull it at its next natural boundary.
- **Proposal inventory:** frontend browser pass above is the only live
  non-archive proposal. Owner and backend-specialist inboxes are empty.
- **Benchmark work** is per-specialist and listed in `docs/ROADMAP.md` §2/§4.
- **Known stale:** none. `docs/RESUME.md`'s config snapshot was the last one and
  is fixed — it now points at `docs/config/CONFIG_INVENTORY.md` rather than
  keeping a second copy, since the duplication was the defect.

### Traps this session actually hit — do not relearn them

- **A targeted test run is not a suite run.** A loop-guard change touching
  `run_agent` broke CI because I verified with 7 files. Run the full suite before
  every commit; it takes ~3.5 minutes and the OOM norm that once justified
  skipping it no longer applies.
- **Section-boundary replaces eat content between anchors.** One deleted four
  numbered steps from `RUST_MIGRATION_STRATEGY.md` while leaving the heading.
  Re-read the rendered file after any structural edit.
- **A worker's summary is not verification.** Check its claims against source and
  cite `file:line`. Two workers this week were correct; one was killed before
  writing anything and its "conclusions" existed only in a log.
- **Fixing a config does not fix a session already running under it.** The
  release agent looked broken; its Codex session had simply booted under the old
  `.codex/config.toml` sandbox.
- **Never sweep another agent's files.** Always `git commit -- <explicit paths>`.
  The tree is shared and frontend/release files are routinely dirty.
- **Unquoted heredocs execute backticks.** Worker prompt prose is still shell
  input while `full_brief` is constructed. Use literal quotes, then prove the
  rendered prompt through a real dispatch.
- **Service-dependent suites change collection.** A live Qdrant turns 12 skips
  into integration tests. Run it on a test-owned port/data set and watch for
  leaked module globals; do not dismiss order-only failures as infrastructure.

## Change note

Updated 2026-07-28 after proposal-freshness/execution sweep. Current checkpoint
adds owner archive normalization, real frontend-backend readiness, ClamAV
transport hardening, worker-prompt quoting, and two proven live-Qdrant test
isolation repairs.
Previous checkpoint remains history; current one supersedes its HEAD/suite/open
inbox details.

Rewritten 2026-07-28 to add the MENTAL MODEL section at the top, on the owner's
instruction: Claude's weekly usage limit is nearly exhausted, so the backend role
will run on Codex, and a fresh Codex session must acquire the long-term picture
from files alone. The previous checkpoint documented the crew-workflow rewrite;
that work is done and canonical in `docs/architecture/CREW_WORKFLOW.md`.

Two claims in the previous checkpoint are now **obsolete**: the CB4 decision-mirror
gap (cancelled/crashed runs writing zero records) is FIXED, and the frontend's
uncommitted WIP has been committed — the tree is clean there.

## Previous checkpoint (2026-07-27)

- Provider: Claude Code (standalone, not in tmux)
- Task: **DONE — full crew-workflow redesign**, on the owner's instruction to
  rebuild from scratch rather than bolt fixes on a weak base. Canonical result:
  **`docs/architecture/CREW_WORKFLOW.md`**, which supersedes every older
  description of agent coordination.
- What changed:
  - **All push-based messaging deleted.** systemd wake path units + heartbeat
    timers disabled, unenabled, and removed from `~/.config/systemd/user/` AND
    the repo (the standup script silently reinstalled them; it is gone too).
  - **Seven scripts deleted, replaced by one: `scripts/crew.sh`**
    (`start|status|attach|stop|run`). No send-keys anywhere in it.
  - **New tracked channel `comms/YYYY-MM-DD/<role>.md`** — one file per role per
    day, sharded so concurrent appends cannot clobber.
  - **No automatic provider failover.** Provider chosen at launch.
  - **"Never sits idle" RETIRED** — the most expensive bad instruction we ever
    followed (busywork, git churn, agents trampling each other).
  - **Challenge-the-owner mandate added** to `CLAUDE.md` + `AGENTS.md`.
- Verification: `crew.sh` syntax-checked and smoke-tested with no live agents.
  No backend/ or frontend/ source touched by that pass.
