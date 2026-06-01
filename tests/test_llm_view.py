import json
from pathlib import Path

import pytest
from pydantic_ai import capture_run_messages
from pydantic_ai.models.test import TestModel
from pydantic_core import to_jsonable_python

from src.agent.bootstrap import bootstrap_vraksha
from src.agent.runtime import vraksha_agent


@pytest.mark.anyio
async def test_dump_what_llm_sees():
    model = TestModel(call_tools=[], custom_output_text="ok")

    with capture_run_messages() as messages:
        result = await vraksha_agent.run(
            "What files should you inspect first?",
            deps=bootstrap_vraksha(),
            model=model,
        )

    params = model.last_model_request_parameters

    snapshot = {
        "output": result.output,
        "messages": to_jsonable_python(messages),
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "schema": tool.parameters_json_schema,
            }
            for tool in params.function_tools
        ],
        "output_tools": to_jsonable_python(params.output_tools),
        "allow_text_output": params.allow_text_output,
    }

    Path("llm_view_snapshot.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    assert snapshot["messages"]

    
