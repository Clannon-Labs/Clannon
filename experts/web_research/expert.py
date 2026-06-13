"""Web research expert (key: web.research) — searches the open web and returns
findings with sources. All its behavior lives in its system prompt + skills beside
this file; this module just declares what it is and what it needs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel

from registry import expert
from registry.capabilities.handler import Expert


class ResearchIn(BaseModel):
    """What the orchestrator emits to call this expert (structured, not free text)."""
    prompt: str = Field(description="The research question or task to investigate.")


@expert
class WebResearchExpert(Expert):
    name = "research"
    domain = "web"
    description = "Research a question on the open web and return findings with source URLs."
    input_schema = ResearchIn
    skills = ("skills",)                       # baseline skills/ beside this file
    tools = ("search.web", "web.fetch_url")    # REQUESTED; the handler grants them (scoped, guarded)
    model_role = "research"
    permission = PermissionLevel.NETWORK
    tags = ("open-web", "sources", "citations")
    # No run() / render(): the default tool-driving run over its system prompt +
    # skills + granted tools is the whole expert; the task IS the input prompt.
