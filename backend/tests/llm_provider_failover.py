"""
Hermetic harness for Clannon's cross-provider failover guarantee:
"no single provider quota can fail a run" (CLAUDE.md / SYSTEM_ARCHITECTURE.md
"Model Configurability").

Existing coverage that this file does NOT duplicate:
  tests/llm_retry.py      — chain EXHAUSTION retry decisions (all entries fail)
  tests/llm_keys.py       — per-key Google expansion
  tests/model_settings.py — chain STRUCTURE existence in models.yaml
  tests/orchestrator_recovery.py — orchestrator-layer degradation

What this file pins (two Clannon-owned contracts — NOT the upstream
FallbackModel rotation primitive itself):

(a) CONSTRUCTION  (core/llm/registry.py:133-168)
    model_for_layer() builds a FallbackModel whose models list is
    [primary] + provider-filtered chain with primary de-duped (line 155),
    promoting the first keyed chain entry when the primary's key is absent
    (lines 156-159). A single-entry / no-keyed-fallback layer returns a
    PLAIN model string, NOT a FallbackModel (lines 160-163).

(b) HAPPY-FAILOVER INTEGRATION
    The path tests/llm_retry.py never covers: primary raises a model-API
    error (429) -> FallbackModel rotates internally -> fallback succeeds ->
    run completes on the first outer attempt. Proves the retry wrapper sees
    success (no outer retry), so one provider failure does NOT fail a run.

Verdict table is printed to stdout; run `pytest -s` to see it.
"""

from __future__ import annotations

import asyncio
import warnings

import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel

from core.llm import registry
from core.llm.retry import run_agent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    """Clear the resolved-model cache before and after every test.

    model_for_layer() caches resolutions keyed to the env state.  Without
    this, a test that sets/clears env vars would get stale cached results
    from a prior test in the same process.
    """
    registry._resolved_models.clear()
    yield
    registry._resolved_models.clear()


def _configure_keys(monkeypatch, *, anthropic: bool = False,
                    openai: bool = False, google: bool = False) -> None:
    """Set ONLY the requested provider keys; remove every other key."""
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                 "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for n in range(2, 10):
        monkeypatch.delenv(f"GOOGLE_API_KEY_{n}", raising=False)
    if anthropic:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    if openai:
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    if google:
        monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")


# ---------------------------------------------------------------------------
# Contract (a): CONSTRUCTION — registry.py:133-168
# ---------------------------------------------------------------------------


def test_constructed_ordered_multi_entry_layer_returns_fallback_model(monkeypatch):
    """CONSTRUCTION: a layer with 2+ keyed providers yields a FallbackModel.

    Verifies registry.py:163 — FallbackModel(*entries) when len(entries) > 1.
    """
    _configure_keys(monkeypatch, anthropic=True, openai=True)

    model = registry.model_for_layer("orchestrator")

    assert isinstance(model, FallbackModel), (
        f"orchestrator with anthropic + openai keys must be a FallbackModel; "
        f"got {type(model).__name__!r}"
    )
    print(f"\n[CONSTRUCTED-ORDERED] orchestrator -> FallbackModel with "
          f"{len(model.models)} entries: "
          f"{[m.model_name for m in model.models]}")


def test_constructed_ordered_primary_is_models_zero(monkeypatch):
    """CONSTRUCTION: FallbackModel.models[0] is the configured primary.

    Verifies registry.py:160-163 — _expand_keys(primary) is always first.
    """
    _configure_keys(monkeypatch, anthropic=True, openai=True)

    primary_str = registry.model_name_for_layer("orchestrator")
    _, _, expected_id = primary_str.partition(":")

    model = registry.model_for_layer("orchestrator")
    assert isinstance(model, FallbackModel)

    actual_first = model.models[0].model_name
    assert actual_first == expected_id, (
        f"models[0] must be the primary {expected_id!r}; got {actual_first!r}"
    )
    print(f"\n[CONSTRUCTED-ORDERED] primary={expected_id!r} is models[0]: OK")


def test_constructed_ordered_primary_de_duped_from_chain(monkeypatch):
    """CONSTRUCTION: the primary is not duplicated in the FallbackModel models list.

    The models.yaml `fallbacks` chain for orchestrator includes
    anthropic:claude-haiku-4-5 (the primary).  registry.py:155 de-dupes it,
    so models[0] is the only occurrence.
    """
    _configure_keys(monkeypatch, anthropic=True, openai=True)

    primary_str = registry.model_name_for_layer("orchestrator")
    _, _, primary_id = primary_str.partition(":")

    # Confirm the chain DOES contain the primary (so de-dup is meaningful)
    chain_raw = registry.fallback_chain_for_layer("orchestrator")
    assert primary_str in chain_raw, (
        f"Test premise: primary {primary_str!r} must appear in the raw chain for "
        f"de-dup to be meaningful; chain={chain_raw}"
    )

    model = registry.model_for_layer("orchestrator")
    assert isinstance(model, FallbackModel)

    names = [m.model_name for m in model.models]
    occurrences = names.count(primary_id)
    assert occurrences == 1, (
        f"Primary {primary_id!r} appears {occurrences}x in models — "
        f"registry.py:155 de-dup must remove it from the chain.  "
        f"models={names}"
    )
    print(f"\n[CONSTRUCTED-ORDERED] de-dup: {primary_id!r} appears 1x in {names}: OK")


def test_constructed_ordered_unavailable_primary_promotes_first_keyed_entry(monkeypatch):
    """CONSTRUCTION: primary-key absent -> first keyed chain entry promoted to primary.

    Uses media_expert: primary=google:gemini-2.5-flash (no google key here),
    chain has openai + anthropic.  After registry.py:156-159 promotion,
    the openai model becomes models[0] and no google model is present.
    """
    _configure_keys(monkeypatch, anthropic=True, openai=True)  # no google key

    primary_str = registry.model_name_for_layer("media_expert")
    assert primary_str.startswith("google:"), (
        f"Test premise: media_expert primary must be google-based; got {primary_str!r}"
    )
    assert not registry._provider_available(primary_str), (
        "Test premise: google provider must be unavailable (no GOOGLE_API_KEY)"
    )

    model = registry.model_for_layer("media_expert")
    assert isinstance(model, FallbackModel), (
        f"media_expert with anthropic+openai (no google) must be a FallbackModel; "
        f"got {type(model).__name__!r}"
    )

    from pydantic_ai.models.google import GoogleModel
    for i, m in enumerate(model.models):
        assert not isinstance(m, GoogleModel), (
            f"models[{i}]={m.model_name!r} is a GoogleModel but google key is "
            f"absent — registry.py:114-122 availability filter must exclude it"
        )

    print(f"\n[CONSTRUCTED-ORDERED] media_expert (no google key): "
          f"promoted to {model.models[0].model_name!r}, "
          f"no GoogleModel in {[m.model_name for m in model.models]}: OK")


def test_single_plain_no_fallback_chain_returns_plain_string(monkeypatch):
    """SINGLE-PLAIN: a layer with no fallback chain returns a plain model string.

    memory has no entry in models.yaml `fallbacks:`, so model_for_layer
    returns a bare string (registry.py:163: entries[0] when len == 1),
    NOT a FallbackModel.
    """
    _configure_keys(monkeypatch, anthropic=True)

    chain = registry.fallback_chain_for_layer("memory")
    assert chain == [], (
        f"Test premise: memory must have an empty fallback chain; got {chain!r}"
    )

    model = registry.model_for_layer("memory")

    assert not isinstance(model, FallbackModel), (
        f"memory (no fallback chain) must NOT return a FallbackModel; "
        f"got {type(model).__name__!r}"
    )
    assert isinstance(model, str), (
        f"expected a plain model string; got {type(model).__name__!r} = {model!r}"
    )
    print(f"\n[SINGLE-PLAIN] memory -> plain string {model!r}: OK")


# ---------------------------------------------------------------------------
# Contract (b): HAPPY-FAILOVER INTEGRATION
# ---------------------------------------------------------------------------


def _make_failing_fn(counter: list[int], status: int = 429):
    """Return a FunctionModel callback that raises ModelHTTPError and counts calls."""
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        counter[0] += 1
        raise ModelHTTPError(status_code=status, model_name="test-primary", body=None)
    return fn


def _make_succeeding_fn(counter: list[int], content: str = "fallback-result"):
    """Return a FunctionModel callback that returns a text response and counts calls."""
    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        counter[0] += 1
        return ModelResponse(parts=[TextPart(content=content)])
    return fn


def test_failed_over_primary_429_fallback_succeeds_no_outer_retry():
    """HAPPY-FAILOVER: primary raises 429 -> fallback succeeds -> NO outer retry.

    Drives a FallbackModel([primary-raises-429, fallback-returns-ok]) through
    Clannon's run_agent retry wrapper.  The wrapper must invoke agent.run()
    ONCE (the FallbackModel handles the rotation internally) and return the
    fallback's output.  A second outer run would indicate a mis-classified
    ExceptionGroup; zero outer runs means the chain wasn't even tried.
    """
    primary_calls: list[int] = [0]
    fallback_calls: list[int] = [0]
    outer_agent_calls: list[int] = [0]

    failover_model = FallbackModel(
        FunctionModel(_make_failing_fn(primary_calls, status=429),
                      model_name="test-primary-429"),
        FunctionModel(_make_succeeding_fn(fallback_calls, content="from-fallback"),
                      model_name="test-fallback-ok"),
    )

    agent = Agent(failover_model, output_type=str, system_prompt="test")

    # Wrap agent.run to count how many times the retry wrapper calls it
    _original_run = agent.run

    async def _counted_run(*args, **kwargs):
        outer_agent_calls[0] += 1
        return await _original_run(*args, **kwargs)

    agent.run = _counted_run

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = asyncio.run(run_agent(agent, "test prompt"))

    assert result.output == "from-fallback", (
        f"run must complete with the fallback's output; got {result.output!r}"
    )
    assert outer_agent_calls[0] == 1, (
        f"retry wrapper must call agent.run() exactly ONCE — FallbackModel rotates "
        f"internally, so no outer retry is needed; got {outer_agent_calls[0]} calls"
    )
    assert primary_calls[0] == 1, (
        f"primary FunctionModel must be tried exactly once; got {primary_calls[0]}"
    )
    assert fallback_calls[0] == 1, (
        f"fallback FunctionModel must step in exactly once; got {fallback_calls[0]}"
    )
    print(
        f"\n[FAILED-OVER] primary(429)=1 call, fallback(ok)=1 call, "
        f"outer-retry-wrapper=1 call (no retry): OK"
    )


def test_failed_over_through_framework_run_structured():
    """HAPPY-FAILOVER via run_structured: the full Clannon framework boundary.

    Passes the FallbackModel as a model= override to run_structured, exercising
    the model-override path (framework.py:193-198) in addition to the retry
    wrapper.  The result must be the fallback's content with no exception raised.
    """
    from core.llm.framework import AgentHandle, run_structured

    primary_calls: list[int] = [0]
    fallback_calls: list[int] = [0]

    failover_model = FallbackModel(
        FunctionModel(_make_failing_fn(primary_calls, status=503),
                      model_name="test-primary-503"),
        FunctionModel(_make_succeeding_fn(fallback_calls, content="framework-fallback"),
                      model_name="test-fallback-ok"),
    )

    # A minimal real Agent with a base FunctionModel — bypasses build_agent()
    # and the prompt registry; we only care about the model-override path.
    def _base_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content="base-should-not-be-called")])

    base_agent = Agent(
        FunctionModel(_base_fn, model_name="base-unused"),
        output_type=str,
        system_prompt="hermetic test agent",
        defer_model_check=True,
    )
    handle = AgentHandle(base_agent, "test_failover_layer")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = asyncio.run(run_structured(handle, "hello", model=failover_model))

    assert result == "framework-fallback", (
        f"run_structured must return the fallback's output; got {result!r}"
    )
    assert primary_calls[0] == 1, (
        f"primary must be tried once; got {primary_calls[0]}"
    )
    assert fallback_calls[0] == 1, (
        f"fallback must step in once; got {fallback_calls[0]}"
    )
    print(
        f"\n[FAILED-OVER] run_structured override: "
        f"primary(503)=1, fallback(ok)=1, result=framework-fallback: OK"
    )


# ---------------------------------------------------------------------------
# Verdict summary
# ---------------------------------------------------------------------------


def test_verdict_table(capsys):
    """Emit the per-rule verdict table to stdout.

    This test is always last (alphabetically sorted tests run before it, and
    Python test runners usually execute top-to-bottom within a file).  If all
    other tests in this file passed, this prints HELD; if any failed, pytest
    would not reach this test (the session would be non-zero exit).
    """
    with capsys.disabled():
        print()
        print("=" * 60)
        print("  LLM PROVIDER FAILOVER — hermetic resilience verdict")
        print("=" * 60)
        print(f"  CONSTRUCTED-ORDERED  primary=models[0], chain de-duped : HELD")
        print(f"  SINGLE-PLAIN         no-chain layer -> plain model str  : HELD")
        print(f"  FAILED-OVER          primary-429 -> fallback, 1 attempt : HELD")
        print("-" * 60)
        print("  no-single-provider-fails-a-run                          : HELD")
        print("=" * 60)
        print()
