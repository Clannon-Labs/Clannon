from __future__ import annotations

from typing import Any, Dict

from registry.register import expert
from tools.schemas.output import STANDARD_OUTPUT_SCHEMA


@expert(enabled=True, domain="architecture", tags=["smoke", "diagnostic"])
class ArchitectureSmokeExpert:
    name = "smoke_check"
    description = "Diagnose whether the expert capability path is callable."
    input_schema = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Architecture area to diagnose.",
                "default": "capability architecture",
            }
        },
        "required": [],
    }
    output_schema = STANDARD_OUTPUT_SCHEMA
    instruction_files = ["experts/architecture_smoke/SKILL.md"]

    def call(self, tool_input: dict) -> Dict[str, Any]:
        subject = str(
            tool_input.get("subject") or "capability architecture"
        ).strip()

        return {
            "success": True,
            "data": {
                "subject": subject,
                "diagnosis": "expert path reachable",
                "instruction_files": self.instruction_files,
            },
            "error": None,
        }
