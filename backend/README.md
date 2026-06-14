# Clannon backend (Vraksha engine)

The Python pipeline + FastAPI API. **Railway deploys this directory** (set the
service Root Directory to `backend/`). Everything here runs with `backend/` as the
working directory.

## Layout

```
foundation/   shared primitives — Flow transport, vocab, contracts, coercion (imports nothing else)
core/         pipeline internals — intake, normalizer, verifier, llm adapter, orchestrator, memory, artifacts
registry/     capability registration — config loaders, @tool/@expert decorators, the Capabilities door
tools/        tool impls (web_search, fetch_url, calculator, python_exec, fs.read/write, code.run)
experts/      expert packages (each = system.md + skills/ + a uniform run())
security/     sanitizers (ClamAV/YARA pre-gate + modality workers; upload admission) + output filter
delivery/     terminal/CLI adapter
prompts/      versioned baseline prompts (the hardened text lives out-of-git in prompts.secure/)
api/          FastAPI delivery adapter (app/auth/runs/config); runtime data in api/data/ (gitignored)
main.py       CLI entry (one-shot or TUI)
models.yaml   model/provider routing
```

`foundation.get_root()` resolves to this directory (it holds `pyproject.toml` /
`requirements.txt` / `main.py`), so config like `models.yaml`, `rules/`, the
`prompts.secure/` overlay, and `api/data/` are all found relative to here.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt   # runtime + test deps
cp .env.example .env.local          # add provider keys

# from the repo root: bring up the service deps
docker compose up -d clamav qdrant

uvicorn api.app:app --port 8000     # the API the frontend talks to
python main.py "your brief"         # or the CLI
pytest                              # the test suite (skips qdrant/clamav-only tests)
```

## Deploy (Railway)

- Root Directory: `backend/`. Railway builds `Dockerfile` (the default `CMD` runs
  `uvicorn api.app:app` on `$PORT`).
- Set provider keys + service URLs as Railway env vars (see `.env.example`); never
  commit `.env.local`.
- The hardened `prompts.secure/` overlay is provided at deploy time (not baked into
  the image); set `VRAKSHA_REQUIRE_PROD_PROMPTS=1` so boot fails closed if a locked
  prompt (verifier/filter) is still on its baseline.

The full HTTP contract is documented in [`api/README.md`](api/README.md).
