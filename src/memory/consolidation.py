"""
Memory Consolidation Sub-Agent for Vraksha.

This module is responsible for the 'Sleep Cycle' of the agent. It periodically
processes raw conversation transcripts to extract durable, high-signal 
memories (Rules, Facts, Preferences) and commits them to long-term storage.

The extraction is performed by a specialized LLM call that filters out 
ephemeral noise (greetings, debug logs) and focuses on state changes.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai.agent import Agent
from src.memory.local_index import MemoryRecord
from src.memory.coordinator import memory_coordinator

logger = logging.getLogger(__name__)

class ConsolidationResult(BaseModel):
    """
        Structured memories extracted from a session transcript.
    """
    rules: list[str] = Field(default_factory=list, description="Absolute constraints or mandates from the user.")
    preferences: list[str] = Field(default_factory=list, description="User likes/dislikes and coding style preferences.")
    facts: list[str] = Field(default_factory=list, description="Verified project details and architectural decisions.")
    events: list[str] = Field(default_factory=list, description="Significant session milestones.")

from pydantic_ai.models.test import TestModel

# Specialized agent for consolidation tasks
# Initialized with a TestModel to prevent premature API key validation.
consolidation_agent = Agent(
    TestModel(),
    result_type=ConsolidationResult,
    system_prompt=(
        "You are Vraksha's Memory Consolidation Agent. "
        "Analyze the transcript and extract DURABLE, HIGH-SIGNAL information. "
        "Ignore greetings, social filler, or temporary debug logs. "
        "Collapse redundant items into clear, atomic statements."
    )
)

def _message_text(message: dict[str, Any]) -> str:
    """
        Safely extracts text content from various message formats.
    """
    content = message.get("content", "")
    if isinstance(content, str): return content

    if isinstance(content, list):
        return " ".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)

    return str(content)

"""
    A bare asterisk * (without a variable name) acts as a separator in a function's signature.
    It indicates that all parameters following it must be passed as keyword arguments only.

    Example:
    def update_record(id, *, status, notify=False):
        pass

    # Correct:
        update_record(101, status="active", notify=True)

    # Error:
        update_record(101, "active", True)  # TypeError: takes 1 positional argument but 3 were given
"""
def build_transcript(messages: list[dict[str, Any]], *, max_messages: int = 30, max_chars: int = 15_000) -> str:
    """
        Constructs a clean, timestamped transcript for consolidation analysis.
    """
    lines = [f"{str(m.get('role', 'unknown')).upper()}: {_message_text(m)}" for m in messages[-max_messages:]] # Takes and loops over last N messages
    return "\n".join(lines)[-max_chars:]

async def consolidate_session(messages: list[dict[str, Any]]) -> None:
    """The 'Cognitive Sleep Cycle' for distilling chat history into durable memory.
    
    Raw conversation transcripts are extremely high-entropy environments full 
    of social filler, greetings, and ephemeral debug noise. Feeding these 
    transcripts back into the agent directly results in token bloat and a 
    significant drop in reasoning quality.
    
    Consolidation is the process of 'Garbage Collection' for the brain. It 
    uses a specialized sub-agent to analyze the transcript, extract high-signal 
    facts, rules, and preferences, and commit them to their respective 
    Tri-Store layers. This ensures that the agent's long-term memory 
    remains dense, accurate, and relevant.
    """
    if not messages: return
    transcript = build_transcript(messages)
    if not transcript.strip(): return

    from src.providers import get_model_priorities
    model_chain = get_model_priorities("memory")

    if not model_chain:
        logger.error("❌ Consolidation failed: No API keys found.")
        return

    last_error = None
    for model_inst in model_chain:
        try:
            logger.info(f"🌙 Starting consolidation with: {model_inst}")

            # Run the PydanticAI consolidation agent
            result = await consolidation_agent.run(
                f"Transcript:\n{transcript}",
                model=model_inst
            )
            data = result.data
            
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            source_id = f"consolidation:{ts}"
            records = []

            # TRI-STORE CATEGORIZATION
            category_map = {
                "rules": ("rule", 0.95),
                "preferences": ("preference", 0.80),
                "facts": ("fact", 0.75),
                "events": ("episode", 0.60),
            }

            from src.memory.wiki import wiki_layer
            from src.memory.semantic_store import semantic_layer

            for attr, (kind, trust) in category_map.items():
                for item in getattr(data, attr):
                    if not item.strip(): continue
                    
                    # 1. Save to standard SQLite Index (Mid-Term)
                    records.append(MemoryRecord(
                        source_id=source_id,
                        kind=kind,
                        title=f"consolidated {kind}",
                        content=item.strip(),
                        trust=trust,
                        pinned=(kind == "rule"),
                    ))

                    # 2. IF it's a RULE, commit to the Durable Wiki (Long-Term)
                    if kind == "rule":
                        wiki_layer.add(item.strip(), filename="rules.md", trust=trust, pinned=True)
                        logger.info(f"📜 Rule committed to Wiki: {item.strip()[:50]}...")

                    # 3. IF it's a PREFERENCE, commit to the Semantic Layer (Long-Term)
                    if kind == "preference":
                        semantic_layer.add(item.strip(), category="preference", trust=trust, session_id=source_id)
                        logger.info(f"🧠 Preference committed to Semantic Store: {item.strip()[:50]}...")

            if records:
                # 4. Final Batch Commitment to the Engine
                await memory_coordinator.memory.remember_many(records)
                logger.info(f"✅ Consolidated {len(records)} memories (batch: {source_id}) using {model_inst}")

            return # Success!

        except Exception as e:
            last_error = e
            logger.warning(f"⚠️ Consolidation failover: {model_inst} failed: {e}. Trying next...")
            continue

    logger.error(f"❌ Background memory consolidation failed after all attempts: {last_error}")


def run_consolidation(messages: list[dict[str, Any]]) -> None:
    """
        Public entry point for consolidation. Ensures the process runs 
        asynchronously without halting the main interaction loop.
    """
    try:
        loop = asyncio.get_running_loop()
        # Fire-and-forget task in the background
        loop.create_task(consolidate_session(messages))
        
    except RuntimeError:
        # Fallback for environments without a running loop
        asyncio.run(consolidate_session(messages))
