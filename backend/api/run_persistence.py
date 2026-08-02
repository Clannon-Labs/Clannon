"""Single SQLite row mapping for durable run state."""

from __future__ import annotations

import json
from typing import Any

from .run_lineage import encode_prefix
from .run_state import RunState


def write_run(
    db: Any, run: RunState, *, superseded: bool | None = None
) -> None:
    """Persist one run, optionally overriding its supersession bit."""
    db.execute(
        "INSERT OR REPLACE INTO runs "
        "(id,user_id,title,brief,status,created_at,tokens_used,cache_read_tokens,"
        "cache_write_tokens,log_json,experts_json,"
        "report,message,memory_writes_json,feedback_rating,feedback_comment,"
        "parent_run_id,session_id,lineage_prefix_json,block_stage,artifacts_json,"
        "inputs_json,project_id,sources_json,verification_state,completion_state,"
        "completion_reason,superseded,started_at,first_message_at,completed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            run.id, run.user_id, run.title, run.brief, run.status,
            run.created_at, run.tokens_used, run.cache_read_tokens,
            run.cache_write_tokens, json.dumps(run.log),
            json.dumps(list(run.experts.values())), run.report, run.message,
            json.dumps(run.memory_writes), run.feedback_rating,
            run.feedback_comment, run.parent_run_id, run.session_id or run.id,
            encode_prefix(run.lineage_prefix), run.block_stage,
            json.dumps(run.artifacts), json.dumps(run.inputs), run.project_id,
            json.dumps(run.sources), run.verification_state,
            run.completion_state, run.completion_reason,
            int(run.superseded if superseded is None else superseded),
            run.started_at, run.first_message_at, run.completed_at,
        ),
    )
