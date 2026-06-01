from get_root import root

PROJECT_ROOT = root.project

def extract_content(filename: str = None, role: str = None, base_dir: str = "memory") -> str | dict:
    """Read memory files at system-prompt-build time.

    NOTE: This function is intentionally memory-scoped. Reads of arbitrary
    project files are handled by the `read_file` tool in src/utils/file_tools.py,
    which the agent calls explicitly when it needs to inspect code, configs, or docs.
    """
    base = PROJECT_ROOT / base_dir

    if not base.exists():
        raise FileNotFoundError(f"Base folder '{base}' not found!")

    if role == "skill":
        raise ValueError("No memory for sub agents/skills")

    if role == "agent":
        target_dir = base / "agent"
    else:
        target_dir = base

    if not target_dir.exists():
        raise FileNotFoundError(f"Path '{target_dir}' does not exist.")

    contents = {}
    for file in target_dir.iterdir():
        if file.is_file():
            with open(file, "r", encoding="utf-8") as f:
                file_content = f.read()

                contents[file.name] = file_content # With extension
                contents[file.stem] = file_content # Without extension

    if filename:
        return contents.get(filename, f"File '{filename}' not found in {target_dir}")
    
    return contents

