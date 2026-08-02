# `specification/` — what any implementation must be true to

This directory is **the contract**, not the documentation. Everything here describes
what the system must *do*; nothing here describes how today's code happens to do it.

That distinction is the whole point. The backend is being rewritten from Python into
Rust (`rust/`). A document tied to the Python implementation dies at the rewrite. A
document tied to the contract survives it, and is what the Rust is checked against.

| | `specification/` | `docs/` |
|---|---|---|
| Answers | *what must be true* | *how it works, and why* |
| Survives the Rust rewrite | yes — it is the target | mostly no |
| Frontend reads it | **yes, this is the one** | no |
| Frontend writes to it | yes — `api/requests/` only | no |

---

## 1. Precedence — read this before building anything frontend-facing

**`specification/api/` wins over every other description of the HTTP surface.**

`frontend/BACKEND_INTEGRATION.md` says of itself: *"complete, authoritative,
self-contained... Build entirely from this doc."* That was true when written and is
**superseded for route, method, auth and response-shape questions.** It remains the
right doc for frontend-internal architecture — the `ClannonClient` interface, the
mock/http split, the config layout. It is the frontend agent's file; the backend does
not edit it.

Order of authority, highest first:

| Rank | Source | Why |
|---|---|---|
| 1 | `backend/tests/benchmarks/sse_contract_drift.py` + its fixture | **executable.** Fails the suite on real divergence |
| 2 | `backend/api/README.md` | cross-checked against emitted events by that same test |
| 3 | `specification/api/` | reviewed prose, verified against code by date |
| 4 | `frontend/BACKEND_INTEGRATION.md` | older, superseded for routes and shapes |

A machine-checked source always beats a written one. Where this directory would
duplicate something the suite already checks, it **links instead of copying** — an
unchecked copy of a checked thing rots silently while the suite stays green.

---

## 2. Why this is at the root and tracked

`proposals/` is **gitignored** (`.gitignore:83`). It is a good local channel between
agents on one machine, and it cannot carry a contract: it never reaches the remote,
so a request filed there is invisible to any session that did not create it.

A frontend↔backend contract has to be tracked, versioned, and diffable, or it is not
a contract. Hence root, hence committed.

---

## 3. Ownership — who may write what

| Path | Written by | Rule |
|---|---|---|
| `api/ROUTES.md` and the rest of `api/` | **backend** | the surface as it actually exists, or as it is committed to exist |
| `api/requests/` | **frontend** | the only place frontend writes. One file per needed route |
| `rust/` | **backend + owner** | the build guide for the Rust core |

**Frontend never edits a route table.** A route appears there when the backend has
committed to it — not when someone wants it. Otherwise the specification becomes a
wishlist that the code does not match, which is worse than no specification, because
it is trusted.

**Backend never edits `frontend/`.** A request is answered by building the route and
writing it into `api/ROUTES.md`, then replying in the request file.

---

## 4. Contents

| Path | What |
|---|---|
| [`api/`](api/) | The frontend-facing HTTP + SSE surface. **Start here if you are the frontend.** |
| [`api/requests/`](api/requests/) | Frontend's channel for asking the backend to build a route |
| [`rust/`](rust/) | The Rust core: wire protocol, build order, conformance harness, decisions, idioms |

---

## 5. The migration does not change the surface

Owner ruling 2026-08-02 (`rust/DECISIONS.md` D6): **Rust serves the identical
HTTP/SSE surface.** The frontend contract does not change.

This is not politeness — it is what keeps CB6, our only passing Critical benchmark,
green straight through the rewrite. `sse_contract_drift.py` will check the Rust
implementation exactly as it checks the Python one, for free.

**So the frontend is not blocked by the migration and should not wait for it.** Build
against `api/`. If a route you need is missing, file it in `api/requests/`.
