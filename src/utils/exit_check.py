import re

def check_exit(response: str) -> tuple[bool, str]:
    match = re.search(r'<WANTS_TO_EXIT>(.*?)</WANTS_TO_EXIT>', response, re.DOTALL)
    if match:
        return True, match.group(1).strip()
    return False, ""

