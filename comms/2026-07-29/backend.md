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
- Preserve unrelated owner edits: root/frontend private-alpha notes and
  `assets/Clannon Labs.png`.

## dispatched workers
- `21:10` **orchestration** worker via **codex** — 2026-07-29_chat_report_routing.md — exit 0, 588s — output: `.agents/runs/20260729-210100-orchestration.out`
- `21:15` **api** worker via **codex** — 2026-07-29_chat_report_delivery.md — exit 0, 674s — output: `.agents/runs/20260729-210349-api.out`
- `21:20` **api** worker via **codex** — 2026-07-29_chat_report_review.md — exit 0, 275s — output: `.agents/runs/20260729-211555-api.out`
- `21:41` **orchestration** worker via **codex** — 2026-07-29_owner_prompt_structure.md — exit 0, 1059s — output: `.agents/runs/20260729-212417-orchestration.out`
