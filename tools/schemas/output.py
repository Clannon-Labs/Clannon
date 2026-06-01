

STANDARD_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "data": {"type": ["object", "null"]},
        "error": {"type": ["string", "null"]}
    },
    "required": ["success"]
}


RICH_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "data": {
            "type": "object",
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": "integer"}
            }
        },
        "error": {"type": ["string", "null"]}
    },
    "required": ["success"]
}

