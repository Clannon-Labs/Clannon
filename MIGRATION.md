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

**Profiles on this machine:** `cybro` (the owner's personal profile, where the workspace
lives today) and `chillguy` (the second profile, becoming clannon-bot's home).

**Sizes, measured:** everything git ignores that matters is ~104 MB, and 58 MB of that
is `.agents/runs` worker logs you can skip. Real payload under 50 MB. Twenty minutes,
most of it waiting on dependency installs.

### The permission wall — read before you start

Both home directories are mode **700** (`drwx------`), so neither user can read the
other's home. **A plain `rsync` or a GUI copy-paste fails in both directions.** The copy
needs `sudo`, followed by `chown`. This is the step that silently wastes an afternoon
if you miss it.

### ① Run these AS `cybro`

```bash
cd ~/Vault/projects/Clannon
./scripts/crew.sh stop backend      # a live SQLite copy can tear; stop agents first
./scripts/crew.sh stop frontend

# rsync creates the FINAL directory but not its parents — make them first, and own
# them, because parents created by --mkpath would land owned by root
sudo mkdir -p /home/chillguy/Vault/projects
sudo chown chillguy:chillguy /home/chillguy/Vault /home/chillguy/Vault/projects

sudo rsync -a --chown=chillguy:chillguy --exclude backend/.venv --exclude frontend/node_modules /home/cybro/Vault/projects/Clannon/ /home/chillguy/Vault/projects/Clannon/

# agent memory is keyed by ABSOLUTE project path, so the directory name changes
sudo mkdir -p /home/chillguy/.claude/projects/-home-chillguy-Vault-projects-Clannon
sudo rsync -a --chown=chillguy:chillguy /home/cybro/.claude/projects/-home-cybro-Vault-projects-Clannon/memory/ /home/chillguy/.claude/projects/-home-chillguy-Vault-projects-Clannon/memory/

# Claude Code settings — carries the GIT_AUTHOR_*/GIT_COMMITTER_* identity vars
sudo rsync -a --chown=chillguy:chillguy /home/cybro/.claude/settings.json /home/chillguy/.claude/settings.json

sudo chown -R chillguy:chillguy /home/chillguy/Vault /home/chillguy/.claude   # belt-and-braces
```

**Why `--chown` and not a bare `sudo cp`/`mv`:** run as root, those PRESERVE the source
owner. The file lands in the destination home still owned by `cybro`, and the new
profile cannot write to its own workspace. The failures that follow do not look like
permission problems — git cannot write `.git/index`, pytest cannot create caches, and
SQLite reports a readonly database on a file you can plainly see. `--chown` sets
ownership during the copy so the mistake is impossible rather than remembered.

`sudo -iu chillguy` is the convenient way to work in that profile without logging out.
It still cannot read `/home/cybro` — home directories are mode 700 with no ACLs — which
is exactly why the copy itself runs as root.

The rsync is **one line**. A `\` continues a line only at end-of-line; pasted mid-line
it escapes the following space and mangles the source path.

`~` expands to the home of whoever is running the command — that is why every path here
is absolute. Running the original relative form as `cybro` made source and destination
the same directory, which is a silent no-op.

> **If you put the repo somewhere other than `~/Vault/projects/Clannon`**, the agent
> memory directory name must match the new absolute path exactly — Claude Code derives
> it by replacing `/` with `-`. `~/projects/Clannon` means
> `-home-chillguy-projects-Clannon`. Get it wrong and the agents start with no memory,
> silently, because a missing directory is indistinguishable from a fresh project.

### ② Then log in as `chillguy`

```bash
cd ~/Vault/projects/Clannon/backend
rm -rf .venv && uv venv && uv pip install -r requirements.txt
cd ../frontend && npm install

gh auth login                       # as clannon-bot
git config --global user.name  "clannon-bot"
git config --global user.email "293251899+clannon-bot@users.noreply.github.com"
```

**Why `.venv` is rebuilt, never copied:** its `pyvenv.cfg` hard-codes
`home = /home/cybro/.local/share/uv/python/...`, an absolute path into the old profile,
and every `.venv/bin/` shebang matches. Verified by reading the file.

### ③ Verify as `chillguy` BEFORE deleting anything from `cybro`

```bash
cd ~/Vault/projects/Clannon/backend && .venv/bin/python -m pytest -q    # ~1670 passed
sqlite3 api/data/clannon.db "select count(*) from waitlist;"            # db came across
cd .. && git log -1 --format='%an'                                      # clannon-bot
```

---

## 0b. Moving the Claude Code and Codex sessions

**A running session cannot be moved.** What moves is its history, and Claude Code
resumes from that (`claude --resume`). So do this **last, after the agent sessions have
stopped** — a live transcript is still being written, and copying mid-conversation
snapshots a partial file.

### What holds session state

| Path | Size | Holds |
|---|---|---|
| `~/.claude/projects/<key>/*.jsonl` | 145 M | **The conversation transcripts.** One `<key>` per working directory |
| `~/.claude/projects/<key>/memory/` | small | Agent memory. Lives INSIDE the project dir, so it travels with it |
| `~/.claude/plugins/` | 871 M | Installed plugins. Copying beats reinstalling |
| `~/.claude/settings.json` | tiny | The `GIT_AUTHOR_*` / `GIT_COMMITTER_*` identity vars |
| `~/.claude/history.jsonl`, `file-history/` | 16 M | Prompt history, edit history |
| `~/.codex/` | 929 M | `auth.json`, `config.toml`, history, sqlite state |

### The rekey — this is where "nothing lost" is won or lost

`<key>` is the working directory's absolute path with `/` replaced by `-`. Eight
directories are Clannon's, one per agent working dir:

```
-home-cybro-Vault-projects-Clannon                          the coordinator
-home-cybro-Vault-projects-Clannon-backend-api              api specialist
-home-cybro-Vault-projects-Clannon-backend-core-memory      memory specialist
-home-cybro-Vault-projects-Clannon-backend-core-orchestrator
-home-cybro-Vault-projects-Clannon-backend-registry
-home-cybro-Vault-projects-Clannon-backend-security
-home-cybro-Vault-projects-Clannon-frontend
-home-cybro-Vault-projects-Clannon-drafts
```

Copy them unrenamed and the new profile finds nothing — **silently**, because a missing
key is indistinguishable from a project that has never been opened.

### Run as `cybro`, after stopping the agents

```bash
tmux kill-server        # or crew.sh stop <role> for each

sudo rsync -a --chown=chillguy:chillguy /home/cybro/.claude/ /home/chillguy/.claude/
sudo rsync -a --chown=chillguy:chillguy /home/cybro/.codex/  /home/chillguy/.codex/

sudo bash -c 'cd /home/chillguy/.claude/projects && for d in -home-cybro-Vault-projects-Clannon*; do mv -- "$d" "${d/-home-cybro-/-home-chillguy-}"; done'
sudo chown -R chillguy:chillguy /home/chillguy/.claude /home/chillguy/.codex
```

The glob excludes other projects (e.g. GhostLayer) by design. `rsync` copies rather than
moves, so the originals remain under `cybro` as a fallback until you have verified.

**The `--` is load-bearing.** These directory names begin with `-`, so without it `mv`
reads `-home-cybro-...` as a bundle of options and fails with `invalid option -- 'h'`
once per directory. The copy still succeeds, so the result is eight correctly-copied
directories under names the new profile will never look for.

Verify the rename actually happened before trusting it:

```bash
sudo ls /home/chillguy/.claude/projects/     # expect -home-chillguy-* , no leftover Clannon -home-cybro-*
```

**Refresh the live transcript last.** Any session still running while you copy is still
appending to its `.jsonl`, so the copy is a snapshot. After the final session ends,
re-sync just that directory into the already-renamed destination:

```bash
sudo rsync -a --chown=chillguy:chillguy --delete /home/cybro/.claude/projects/-home-cybro-Vault-projects-Clannon/ /home/chillguy/.claude/projects/-home-chillguy-Vault-projects-Clannon/
```

### Then, as `chillguy`

```bash
cd ~/Vault/projects/Clannon && claude --resume
```

**Expect to re-authenticate.** `~/.claude/.credentials.json` and `~/.codex/auth.json`
are commonly machine- or keyring-bound. Re-logging in costs nothing: transcripts,
memory and settings are separate files and are unaffected by it.

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
