"""web_search tool (key: search.web) — grounded open-web search via core/llm."""

from __future__ import annotations

from pydantic import BaseModel, Field

from foundation import PermissionLevel
from core.llm import grounded_search

from ..registry import tool


class WebSearchIn(BaseModel):
    query: str


class WebSearchOut(BaseModel):
    findings: str
    sources: list[str] = Field(default_factory=list)


@tool(
    name="web",
    domain="search",
    description="Search the open web and return key findings with source URLs.",
    input_schema=WebSearchIn,
    output_schema=WebSearchOut,
    permission=PermissionLevel.NETWORK,
    tags=("internet", "sources", "research"),
)
class WebSearchTool:
    async def run(self, args: WebSearchIn) -> WebSearchOut:
        result = await grounded_search(args.query)
        return WebSearchOut(findings=result.findings, sources=result.sources)
