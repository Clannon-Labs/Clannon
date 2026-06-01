from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import logging
from typing import TYPE_CHECKING

# Vraksha Core Imports
from src.memory.coordinator import memory_coordinator
from src.factory.build.system_prompt import DEFAULT_SOUL, BASELINE_RULES  # single source

if TYPE_CHECKING:
    from src.memory.coordinator import MemoryCoordinator

logger = logging.getLogger(__name__)


@dataclass
class VrakshaDeps:
    """Services injected into the PydanticAI Engine per session."""
    memory: MemoryCoordinator
    soul: str
    rules: str
    session_id: str
    user_id: str


def bootstrap_vraksha(
    memory_path: Path | str = "memory",
    session_id: str = "default_session",
    user_id: str = "default_user",
) -> VrakshaDeps:
    """
    Pre-flight loader for the Vraksha Agent.
    Loads Identity (soul.md) and Governance (rules.md) with safe fallbacks.
    All prompt strings originate from factory.build.system_prompt — never here.
    """
    base_path = Path(memory_path)

    # 1. Load Soul (Identity)
    soul_content = _load_file(
        candidates=[base_path / "SOUL.md", base_path / "soul.md"],
        fallback=DEFAULT_SOUL,
        label="Soul",
        log_key="memory/SOUL.md",
    )

    # 2. Load Rules (Governance)
    rules_content = _load_file(
        candidates=[base_path / "RULES.md", base_path / "rules.md"],
        fallback=BASELINE_RULES,
        label="Rules",
        log_key="memory/RULES.md",
    )

    return VrakshaDeps(
        memory=memory_coordinator,
        soul=soul_content,
        rules=rules_content,
        session_id=session_id,
        user_id=user_id,
    )


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_file(
    candidates: list[Path],
    fallback: str,
    label: str,
    log_key: str,
) -> str:
    """Try each candidate path in order; return fallback if none exist."""
    for path in candidates:
        if path.exists():
            content = path.read_text(encoding="utf-8")
            logger.info("✅ %s loaded from %s", label, path)
            return content

    logger.warning("⚠️  %s not found at %s — using built-in default.", label, log_key)
    return fallback
