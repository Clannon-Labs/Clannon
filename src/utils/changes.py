from pathlib import Path
import re
from typing import Optional

import logging

from get_root import root
from src.utils.immutables import is_immutable

logger = logging.getLogger(__name__)


def apply_changes(response_text: str, role: str, base=Path("memory")):
    """
    Parses LLM response for file update instructions and applies them
    to the target directory specified by `base`.

    Handles multiple response formats:
      - XML tags:   <file_update name="file.yaml">content</file_update>
      - Markdown:   **file.yaml:**  ```yaml\ncontent\n```
      - Labels:     Updated file.yaml:\n```yaml\ncontent\n```

    Args:
        response_text: The raw LLM response text.
        role: Target skill directory inside base
        base: Target base directory where changes are applied. Defaults to "memory".

    Returns:
        Number of files successfully updated.
    """

    # NOTE: arbitrary-path writes are handled by the
    # `write_file` tool in src/utils/file_tools.py, not by this parser.
    # `apply_changes` stays scoped to memory writes only.

    base = Path(base)
    base.mkdir(parents=True, exist_ok=True)

    if role != "agent":
        # role = Path(f"skills/{role}")
        raise ValueError("Sub agents/skills don't have memory")

    role = Path(base)/role
    role.mkdir(parents=True, exist_ok=True)

    if not response_text:
        return None

    matched_files = {}
    detected_block = []

    # XML-like <file_update> tags 
    xml_pattern = r'<file_update\s+name="([^"]+?)">(.*?)</file_update>'

    for m in re.finditer(xml_pattern, response_text, re.DOTALL):
        name = m.group(1).strip()

        if _is_hardcoded(role, name):
            continue

        if _is_valid_filename(name):
            matched_files[name] = m.group(2).strip()
            detected_block = m.group().strip()

    # <write_to_file><path>filename</path>content
    if not matched_files:
        # This pattern captures the path inside <path> tags and the following content
        wt_pattern = r'<write_to_file>\s*<path>(.*?)</path>(.*?)</write_to_file>'

        for m in re.finditer(wt_pattern, response_text, re.DOTALL):
            name = m.group(1).strip()

            if _is_hardcoded(role, name):
                continue

            if _is_valid_filename(name):
                matched_files[name] = m.group(2).strip()
                detected_block = m.group().strip()


    # Filename label + fenced code block
    if not matched_files:
        block_pattern = r'```[\w]*\n(.*?)```'

        for block in re.finditer(block_pattern, response_text, re.DOTALL):
            # Grab a chunk of text before the code block to look for a filename
            start = max(0, block.start() - 300)
            preceding = response_text[start : block.start()]
            filename = _extract_filename(preceding, base)

            if _is_hardcoded(role, filename):
                continue
            
            if filename and filename not in matched_files:
                matched_files[filename] = block.group(1).strip()
                detected_block = block.group().strip()

        if not matched_files:
            return 0

    updates_applied = 0

    for (filename, content), block_to_remove in zip(matched_files.items(), detected_block):
        filepath = role / filename

        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
                return response_text.replace(detected_block, "").strip()

            logger.info(f"✅ Updated: {filepath}")
            updates_applied += 1

        except Exception as e:
            logger.error(f"❌ Failed to write {filename}: {e}")

    if updates_applied == 0:
        logger.warning("⚠️ Matches found but all failed validation or writing.")

    return updates_applied


def _is_valid_filename(name: str) -> bool:
    """Check if a string looks like a valid filename."""
    return (
        bool(name)
        and " " not in name
        and len(name) <= 120
        and "\n" not in name
        and "." in name
    )


def _extract_filename(preceding_text: str, base: Path) -> Optional[str]:
    """
    Search text preceding a code block for a filename reference.
    Prefers filenames that match existing files in `base`.
    """
    # Collect known files from the target directory
    known_files = set()

    for f in base.rglob("*"):
        if f.is_file() and f.name != ".gitkeep":
            known_files.add(f.relative_to(base).as_posix())

    # Only look at the last few lines (closest to the code block)
    lines = preceding_text.rstrip().split("\n")
    search_area = "\n".join(lines[-4:])

    # Find all filename-like tokens (word.ext) in the search area
    fname_pattern = r'([a-zA-Z0-9_/.:-]+\.\w{1,10})'
    all_candidates = re.findall(fname_pattern, search_area)

    # Clean up each candidate (strip markdown bold markers, colons, etc.)
    cleaned = []
    for raw in all_candidates:
        c = raw.strip(":").strip("*").strip()
        if _is_valid_filename(c):
            cleaned.append(c)

    # Prefer a known file, take the last (closest) match
    for candidate in reversed(cleaned):
        if candidate in known_files:
            return candidate

    # Fallback: return the last valid filename-like candidate
    if cleaned:
        return cleaned[-1]

    return None

def _is_hardcoded(role: Path, filename: Optional[str]) -> bool:
    """Reject writes to immutable files.

    `role` is the resolved memory directory (e.g. memory/agent) and
    `filename` is the candidate target inside it. We resolve the full
    project-relative path and defer the decision to the shared
    `is_immutable` rule set in memory/IMMUTABLE.yaml.
    """
    if not filename:
        return False

    full = role / filename
    if not full.is_absolute():
        full = root.project / full

    if is_immutable(full):
        logger.warning(f"⚠️ Changes can't be made in protected file '{filename}'.")
        return True
        
    return False

