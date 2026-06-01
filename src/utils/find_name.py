# ========================================================
# Note: This file is redundant and kept just for testing,
# Will replace it soon with a robust name finder/updater
# ========================================================

import re
from pathlib import Path

# def _find(entity: str, base="memory", filename="rules.md") -> str:
#     file = Path(base)/filename

#     with open(Path(file), "r") as f:
#         content = f.read()

#         match = re.search(fr'{entity}:\s*(.*)', content)

#         if match:
#             return match.group(1).strip()

#         return None
"""
    Just hardcoded values until the name logic is locked in
"""
def agent_name():
    return "vraksha"

def user_name():
    return "cybro"

