# Relocating the agent workspace to a dedicated `clannon-bot` profile

**The model:** the whole agent workspace lives in the `clannon-bot` profile — repo,
`proposals/`, `drafts/`, `achievements/`, comms, tmux sessions, `.venv`, `node_modules`.
The owner logs into that profile whenever they want to work with agents and drives
everything exactly as before. Their personal profile is where they act as a separate
developer writing Rust, and needs none of this.

**Nothing about the agent channels changes** — the channels and the agents stay in the
same place.

---

## 0. The easy way — copy the folder, rebuild one thing

If you can copy files between profiles directly, **do that instead of cloning.** One
copy brings tracked files, gitignored files, and `.git` (history, branches, remotes)
together, and you cannot forget an item off a checklist.

**Sizes, measured:** everything that git ignores and matters is **~104 MB**, and 58 MB
of that is `.agents/runs` worker logs you can skip. The real payload is under 50 MB.
This is a twenty-minute job, most of it waiting on dependency installs.

```bash
# 1. Stop the agents first — copying a live SQLite database can tear it
./scripts/crew.sh stop backend; ./scripts/crew.sh stop frontend   # + any others running

# 2. Copy the whole project directory across profiles
#    (skip the two big regenerable trees)
rsync -a --exclude backend/.venv --exclude frontend/node_modules \
      /home/cybro/Vault/projects/Clannon/  ~/Vault/projects/Clannon/

# 3. Rebuild the virtualenv — it is NOT relocatable, see below
cd ~/Vault/projects/Clannon/backend && rm -rf .venv && uv venv && uv pip install -r requirements.txt

# 4. Frontend deps
cd ../frontend && npm install
```

**Why `.venv` must be rebuilt rather than copied:** its `pyvenv.cfg` hard-codes
`home = /home/cybro/.local/share/uv/python/...`, an absolute path into the *old*
profile, and every script in `.venv/bin/` carries a matching shebang. Copied, it points
at an interpreter the new profile cannot rely on. Verified, not assumed.

**Still do §3** — `~/.claude` agent memory and `gh auth` live outside the project
directory and no amount of copying the repo will bring them.

Then verify with §5 before deleting anything.

---

## 1. The clean-clone alternative

Use this if you would rather start from the remote than copy a working directory.

### Git carries almost everything

Every tracked file moves with a `git clone`. **No tracked file contains an absolute
`/home/cybro` path** (verified), so nothing needs rewriting after the move.

```bash
# in the clannon-bot profile
git clone https://github.com/Clannon-Labs/Clannon.git ~/Vault/projects/Clannon
```

Keeping the same `~/Vault/projects/Clannon` suffix is worth doing — several habits and
docs reference that shape.

## 2. What git does NOT carry — copy these by hand

Ordered by what hurts most if forgotten.

| Path | Why it matters |
|---|---|
| `backend/api/data/clannon.db` | **The live database.** Real accounts, runs, waitlist rows. Lose it and the alpha starts empty |
| `backend/.env.local`, `backend/.env.prod` | **Provider API keys.** Copy directly; never paste into a terminal or a file that gets committed |
| `frontend/.env.local`, `frontend/.env.prod` | Frontend environment |
| `proposals/` | The agent channel — 335 files of decisions and their history |
| `drafts/` | `owner_thoughts/` — agents are instructed to read these |
| `achievements/` | The only record of what Clannon actually produced for a user |
| `backend/core/memory/data/` | Local memory store data |
| `frontend/HANDOFF.md` | Gitignored, and it is the frontend agent's continuity |
| `.agents/runs/` | Worker output history. Useful, not critical |
| `.claude/settings.local.json` | Local Claude Code settings for this repo |

```bash
# from the clannon-bot profile, adjust source path as needed
SRC=/home/cybro/Vault/projects/Clannon
DST=~/Vault/projects/Clannon
for p in backend/api/data backend/.env.local backend/.env.prod \
         frontend/.env.local frontend/.env.prod \
         proposals drafts achievements backend/core/memory/data \
         frontend/HANDOFF.md .agents/runs .claude/settings.local.json; do
  [ -e "$SRC/$p" ] && mkdir -p "$(dirname "$DST/$p")" && cp -r "$SRC/$p" "$DST/$p"
done
```

Regenerate rather than copy: `backend/.venv` (1.4 G) and `frontend/node_modules`
(777 M).

## 3. Two things outside the repo — easy to miss, expensive to lose

**Agent memory is keyed by the project's absolute path.** It lives at
`~/.claude/projects/<path-with-slashes-as-dashes>/memory/` — currently
`-home-cybro-Vault-projects-Clannon`, holding 16 files. In the new profile the key
becomes `-home-clannon-bot-Vault-projects-Clannon`. Copy the directory across under the
new name or **every agent starts amnesiac**:

```bash
cp -r /home/cybro/.claude/projects/-home-cybro-Vault-projects-Clannon/memory \
      ~/.claude/projects/-home-clannon-bot-Vault-projects-Clannon/memory
```

**`gh` must be re-authenticated as clannon-bot** in the new profile — the token lives in
that profile's keyring, not in the repo:

```bash
gh auth login    # as clannon-bot
```

## 4. Identity becomes intrinsic — and one thing gets simpler

In the bot profile, set the global identity directly:

```bash
git config --global user.name  "clannon-bot"
git config --global user.email "293251899+clannon-bot@users.noreply.github.com"
```

Once that is true, `crew.sh`'s `GIT_AUTHOR_*` env vars and the `GIT_*` entries in
`~/.claude/settings.json` become belt-and-braces rather than the mechanism. **Leave them
in** — they cost nothing and they keep a headless worker correct even if the profile's
config is ever wrong.

The `origin` / `bot` remote split can also collapse in that profile: with `gh`
authenticated as clannon-bot, plain `origin` works unprompted. Verify before removing
the `bot` remote.

## 5. Verify before deleting anything from the old profile

```bash
cd ~/Vault/projects/Clannon/backend
.venv/bin/python -m pytest -q          # expect ~1670 passed
git log -1 --format='%an'              # expect clannon-bot
git push bot main --dry-run            # or origin, per §4
```

Confirm the database came across — the waitlist and any real accounts should still be
there. **Only then** remove anything from the old location.
