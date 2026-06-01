"""Tests for agent-owned expert communication orchestration."""

from src.agent.orchestration import ExpertMessagePolicy, ExpertMessageRequest, Orchestrator
from src.capabilities import Actor


def test_orchestrator_observes_and_blocks_unknown_expert_routes():
    """Unknown expert-to-expert routes are observed and blocked by default."""
    orchestrator = Orchestrator()
    request = ExpertMessageRequest(
        source=Actor(kind="expert", name="planner"),
        target=Actor(kind="expert", name="review"),
        topic="review_plan",
        payload={"plan": ["inspect", "edit", "test"]},
        reason="planner wants review input",
    )

    decision = orchestrator.review_expert_message(request)

    assert decision.allowed is False
    assert decision.reason == "route is not explicitly allowed"
    assert len(orchestrator.observed_messages) == 1
    assert orchestrator.observed_messages[0].request.request_id == request.request_id
    assert orchestrator.observed_messages[0].decision.request_id == request.request_id


def test_orchestrator_allows_explicit_expert_routes():
    """Explicitly allowed expert routes can pass policy review."""
    orchestrator = Orchestrator(
        policy=ExpertMessagePolicy(allowed_routes={("planner", "review")}),
    )
    request = ExpertMessageRequest(
        source=Actor(kind="expert", name="planner"),
        target=Actor(kind="expert", name="review"),
        topic="review_plan",
        payload={"plan": ["inspect", "edit", "test"]},
        reason="review the proposed plan before execution",
    )

    decision = orchestrator.review_expert_message(request)

    assert decision.allowed is True
    assert decision.reason == "route allowed by orchestrator policy"
    assert orchestrator.observed_messages[0].decision.allowed is True


def test_orchestrator_can_block_allowed_route_by_topic():
    """Blocked topics override otherwise allowed expert routes."""
    orchestrator = Orchestrator(
        policy=ExpertMessagePolicy(
            allowed_routes={("planner", "research")},
            blocked_topics={"unnecessary_chatter"},
        ),
    )
    request = ExpertMessageRequest(
        source=Actor(kind="expert", name="planner"),
        target=Actor(kind="expert", name="research"),
        topic="unnecessary_chatter",
        payload={},
        reason="not useful",
    )

    decision = orchestrator.review_expert_message(request)

    assert decision.allowed is False
    assert decision.reason == "topic is blocked: unnecessary_chatter"
