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
# from backend/
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt   # runtime + test deps
cp .env.example .env.local          # add provider keys

# once per frontend checkout
cd ../frontend && npm install

# canonical full-stack launcher, from repo root
cd ..
./dev.sh
```

The browser uses one origin, `http://<LAN-IP>:3000`; `/api/*` is proxied to
FastAPI on private port 8000. The launcher starts/checks ClamAV and Qdrant and
also pins the embedding cache to `backend/assets/fastembed_cache`.

Backend-only commands such as `python main.py "your brief"` and `pytest` still
run from `backend/`, but they do not replace the full-stack launcher.

## Deploy (Railway)

- Root Directory: `backend/`. Railway builds `Dockerfile` (the default `CMD` runs
  `uvicorn api.app:app` on `$PORT`).
- Copy `backend/.env.prod` into Railway's **Variables → RAW Editor**, replace every
  `REPLACE_*`, review staged changes, then deploy. `.env.prod` is an upload
  template; Python does not load that filename automatically.
- Set `CLANNON_ENV=production`; it is canonical for startup config, YARA, and mail.
  `VRAKSHA_ENV` is a temporary compatibility alias only and must not contradict it.
- Add `api.clannon.com` as the backend custom domain. Configure both DNS records
  Railway provides and wait for HTTPS to become healthy. Do not point the
  browser frontend at the raw `*.up.railway.app` origin: current Lax session
  cookie topology requires frontend and API to remain same-site.
- Attach a persistent volume at `/data` before first signup.
  `SERVER_DB_PATH`, graph memory, and artifacts in `.env.prod` all use it.
  Railway mounts volumes as root while this image runs as uid 10001; resolve
  `/data` ownership before inviting testers. `RAILWAY_RUN_UID=0` is a temporary
  compatibility fallback, not the preferred hardened end state.
- Run ClamAV and Qdrant as private services in the same Railway environment.
  Never expose either service publicly.
- The hardened `prompts.secure/` overlay is provided at deploy time (not baked into
  the image). Upload it to `/data/prompts.secure`; production config fails closed
  if a locked verifier/filter prompt falls back to its baseline.

Before testers:

1. `https://api.clannon.com/health` returns `{"status":"ok"}` over HTTPS.
2. Sign up from `https://clannon.com`; browser stores one Secure, HttpOnly
   `.clannon.com` cookie.
3. Refresh, call `/auth/me`, start a run, reconnect its SSE stream, then restart
   backend. Account, chat, memory, and artifacts must remain.
4. Confirm ClamAV rejects its malware test fixture and Qdrant has no public
   domain.
5. Seal provider keys in Railway after import. Redeploy after any variable
   change.

The full HTTP contract is documented in [`api/README.md`](api/README.md).
