"""
Web delivery adapter — the FastAPI surface the Clannon frontend talks to.

This package wraps the existing pipeline (core.pipeline ACTIVE_STAGES) without
modifying it: runs.py drives the same stage chain and observes ctx.decision_log
to stream live events. Serves the exact contract documented in
clannon/frontend/README.md ("The contract the backend must serve").

Run:  .venv/bin/uvicorn server.app:app --port 8000 --reload
"""
