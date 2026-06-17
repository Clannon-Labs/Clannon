"""
API contract smoke test — exercises the live FastAPI surface end to end to prove
the api/ refactor preserved the frontend contract (auth, runs + SSE, memory CRUD,
model settings, usage). Run against a server started separately:

    PYTHONPATH=. .venv/bin/uvicorn api.app:app --port 8077 &
    .venv/bin/python scripts/api_smoke.py --base http://localhost:8077
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8077")
    args = ap.parse_args()
    base = args.base.rstrip("/")
    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {('— ' + detail) if detail else ''}", flush=True)

    c = httpx.Client(base_url=base, timeout=120.0)

    # config (public)
    r = c.get("/config")
    cfg = r.json() if r.status_code == 200 else {}
    check("GET /config", r.status_code == 200 and "plans" in cfg and "limits" in cfg,
          f"plans={len(cfg.get('plans', []))} limits={list(cfg.get('limits', {}))}")

    # signup -> session cookie
    email = f"smoke_{int(time.time())}@clannon.dev"
    r = c.post("/auth/signup", json={"name": "Smoke Tester", "email": email, "password": "smoke-pass-123"})
    check("POST /auth/signup", r.status_code == 200 and r.json().get("email") == email)

    r = c.get("/auth/me")
    check("GET /auth/me", r.status_code == 200 and r.json().get("email") == email,
          f"plan={r.json().get('plan')}")

    # memory CRUD (wiki)
    r = c.post("/memory", json={"tier": "wiki", "title": "Client X", "content": "Prefers terse reports."})
    mem = r.json() if r.status_code == 201 else {}
    check("POST /memory (wiki create)", r.status_code == 201 and mem.get("tier") == "wiki", f"id={mem.get('id')}")
    entry_id = mem.get("id", "")

    r = c.get("/memory")
    check("GET /memory", r.status_code == 200 and any(m.get("id") == entry_id for m in r.json()))

    r = c.put(f"/memory/{entry_id}", json={"tier": "wiki", "title": "Client X", "content": "Updated note."})
    check("PUT /memory/{id}", r.status_code == 200 and r.json().get("content") == "Updated note.")

    # model settings
    r = c.get("/settings/models")
    cat = r.json() if r.status_code == 200 else []
    locked = [e for e in cat if e.get("locked")]
    check("GET /settings/models", r.status_code == 200 and len(cat) >= 5 and len(locked) >= 1,
          f"roles={len(cat)} locked={len(locked)}")
    # set an unlocked role; locked roles must 403
    unlocked = next((e for e in cat if not e["locked"] and e["options"]), None)
    if unlocked:
        r = c.put("/settings/models", json={"layer": unlocked["layer"], "model": unlocked["options"][0]})
        check("PUT /settings/models (unlocked)", r.status_code == 204)
    if locked:
        r = c.put("/settings/models", json={"layer": locked[0]["layer"], "model": "claude-haiku-4-5"})
        check("PUT /settings/models (locked -> 403)", r.status_code == 403)

    # usage
    r = c.get("/usage")
    check("GET /usage", r.status_code == 200 and "budget" in r.json(), f"budget={r.json().get('budget')}")

    # a real run end to end + SSE
    r = c.post("/runs", data={"brief": "In one sentence, what is a deadlock in concurrency?"})
    rid = r.json().get("id", "") if r.status_code == 201 else ""
    check("POST /runs", r.status_code == 201 and bool(rid), f"id={rid}")

    if rid:
        seen_types: set[str] = set()
        report_done = False
        status_final = None
        with c.stream("GET", f"/runs/{rid}/stream") as s:
            for line in s.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                evt = json.loads(line[6:])
                seen_types.add(evt.get("type"))
                if evt.get("type") == "status":
                    status_final = evt.get("status")
                if evt.get("type") == "report_done":
                    report_done = True
                    break
                if evt.get("type") == "status" and evt.get("status") in ("blocked", "failed"):
                    break
        check("GET /runs/{id}/stream (SSE)", report_done or status_final in ("delivered", "blocked", "failed"),
              f"events={sorted(seen_types)} status={status_final}")

        r = c.get(f"/runs/{rid}")
        full = r.json() if r.status_code == 200 else {}
        check("GET /runs/{id} (full_json)", r.status_code == 200 and full.get("id") == rid
              and "decisionLog" in full and "report" in full,
              f"status={full.get('status')} reportLen={len(full.get('report') or '')}")

    # delete the wiki entry
    r = c.delete(f"/memory/{entry_id}")
    check("DELETE /memory/{id}", r.status_code == 204)

    c.close()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n=== {passed}/{len(results)} API checks passed ===")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
