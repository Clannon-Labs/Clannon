# Backend — 2026-07-29

- Diagnosed real failed UI run: ClamAV absent; no model call occurred.
- Added canonical root `dev.sh`: starts/checks ClamAV + Qdrant, fixes local
  embedding cache, runs private FastAPI + LAN Next, proxies same-origin `/api`.
- Removed duplicate component launchers; synchronized root/backend/API/frontend
  run docs.
- Live stack healthy at `http://192.168.18.84:3000`; launcher landed in `e53bb29`.
- Typed `chat | report` routing landed across foundation/orchestration/API.
  Ordinary/technical answers now use filtered chat; inline report sheet requires
  explicit report intent; generated files remain separate artifacts.
- Rebuilt Clannon central prompt v5 from owner's structural reference and added
  registry-backed batch prompt v1. Active overlay matches baselines.
- Live Haiku 4.5 `Who are you?`: one 13-word `message`, `report=null`, no expert,
  no `say()`. Full backend suite: 1551 passed; frontend lint/typecheck passed.
- Owner rejected initial revise branching semantics. Corrected to same-chat
  edit-in-place: old target + later turns return 404 and disappear from REST
  history, model conversation, recall, and inherited files.
- Superseded rows remain internal only for billed usage, saved memory, and audit
  provenance. Live descendants cancel; atomic failures preserve original chat.
- Server-side input reuse supports hash-verified new blobs and namespace-bound
  legacy blobs; missing/corrupt/redirected inputs fail 409 before run creation.
- Revision proof: backend 1571 passed; frontend 93 passed (20 focused);
  typecheck/lint/build + invariant checker passed. Proposals archived.
- Added ignored backend `.env.prod` Railway upload template; preserved local
  secrets and explicit local profile in `.env.local`. Frontend env files checked
  and left untouched.
- Production cookie contract now uses `clannon.com` + `api.clannon.com`, exact
  credentialed CORS, Secure shared-domain cookie. Raw Railway browser origin
  removed from docs; frontend proposal accepted and archived.
- Docker build context excludes every real `.env*`. Strict production config
  smoke passed; API config tests 15 passed. `/data` volume ownership and real
  DNS/browser proof remain mandatory deployment actions.
- Preserve unrelated owner edits: root/frontend private-alpha notes and
  uncommitted assets.

## dispatched workers
- `21:10` **orchestration** worker via **codex** — 2026-07-29_chat_report_routing.md — exit 0, 588s — output: `.agents/runs/20260729-210100-orchestration.out`
- `21:15` **api** worker via **codex** — 2026-07-29_chat_report_delivery.md — exit 0, 674s — output: `.agents/runs/20260729-210349-api.out`
- `21:20` **api** worker via **codex** — 2026-07-29_chat_report_review.md — exit 0, 275s — output: `.agents/runs/20260729-211555-api.out`
- `21:41` **orchestration** worker via **codex** — 2026-07-29_owner_prompt_structure.md — exit 0, 1059s — output: `.agents/runs/20260729-212417-orchestration.out`
- `22:44` **api** worker via **codex** — 2026-07-29_revise-turn-branch-endpoint.md — exit 0, 1213s — output: `.agents/runs/20260729-222437-api.out`
- `23:13` **frontend** worker via **codex** — 2026-07-29_revise-in-place-copy-and-mock.md — exit 0, 627s — output: `.agents/runs/20260729-230247-frontend.out`
- `23:20` **api** worker via **codex** — 2026-07-29_revise-in-place-not-branch.md — exit 0, 1039s — output: `.agents/runs/20260729-230242-api.out`
- `23:46` **api** worker via **codex** — 2026-07-29_sync-production-env-docs.md — exit 0, 173s — output: `.agents/runs/20260729-234332-api.out`
