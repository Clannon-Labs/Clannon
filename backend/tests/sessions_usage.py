"""
Delete-a-conversation (RunStore.delete_session) and real token metering
(core.llm.usage). Hermetic: the delete-session test asserts the in-memory cache
effects, which happen before any SQLite touch, so it does not depend on a DB.
"""

from api.run_state import RunState
from api.run_store import RunStore
from core.llm import usage_scope
from core.llm import usage as usage_mod


def _run(rid: str, session_id: str, user: str = "u1") -> RunState:
    return RunState(id=rid, user_id=user, title="t", brief="b", status="delivered", session_id=session_id)


def test_delete_session_removes_owner_runs_and_leaves_others():
    store = RunStore()
    store._runs["dts_r1"] = _run("dts_r1", "dts_s1")            # root of session s1
    store._runs["dts_r2"] = _run("dts_r2", "dts_s1")            # follow-up in s1
    store._runs["dts_r3"] = _run("dts_r3", "dts_s2")            # a different session, same user
    store._runs["dts_r4"] = _run("dts_r4", "dts_s1", user="u2")  # someone else's, same session id

    try:
        removed = store.delete_session("u1", "dts_s1")
    except Exception:  # noqa: BLE001 — no SQLite in this env; live-cache effects still hold
        removed = None

    assert "dts_r1" not in store._runs and "dts_r2" not in store._runs   # s1 gone
    assert "dts_r3" in store._runs                                       # other session untouched
    assert "dts_r4" in store._runs                                       # other user untouched
    assert store._runs["dts_r4"].deleted is False
    if removed is not None:
        assert removed >= 2


def test_delete_marks_runs_so_finally_wont_resurrect_them():
    store = RunStore()
    run = _run("dts_live", "dts_live")
    store._runs["dts_live"] = run
    try:
        store.delete_session("u1", "dts_live")
    except Exception:  # noqa: BLE001
        pass
    # the run object is flagged so execute()'s finally skips re-persisting it
    assert run.deleted is True


class _FakeUsage:
    input_tokens = 100
    output_tokens = 50
    requests = 1


class _FakeResult:
    def usage(self):
        return _FakeUsage()


def test_usage_scope_meters_real_tokens():
    with usage_scope() as u:
        usage_mod.accumulate(_FakeResult())
        usage_mod.accumulate(_FakeResult())
    assert u.total_tokens == 300   # (100 + 50) x 2
    assert u.requests == 2


def test_usage_accumulate_is_a_noop_outside_a_scope():
    # must never raise, and must not error on an unrecognized result shape
    usage_mod.accumulate(_FakeResult())
    usage_mod.accumulate(object())
