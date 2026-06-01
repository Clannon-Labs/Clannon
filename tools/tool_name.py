#=====================================================
# DEPRECATED
#=====================================================

import logging
from pathlib import Path
from typing import Union, Literal

logger = logging.getLogger(__name__)


def get_tool_name(
    filepath: Union[str, Path],
    target_dir: str,
    mode: Literal["nearest", "nearer", "farther", "farthest"] = "nearest",
) -> str:
    """
    Generates a deterministic tool name derived from a file path, starting from a
    chosen occurrence of a target directory in the path hierarchy.

    The function converts a file path into a flattened, underscore-separated tool
    identifier, preserving the relative directory structure starting from a selected
    `target_dir` ancestor.

    Selection behavior when multiple matching directories exist:
        - "nearest": uses the closest (lowest-level) matching directory
        - "farthest": uses the highest-level matching directory

    Example:
        Path: /src/tools/core/tools/math.py
        target_dir: "tools"

        nearest: tools_math
        farthest: tools_core_tools_math

    Args:
        filepath (str | Path):
            Absolute or relative path to the tool file.

        target_dir (str):
            Directory name used as the anchor point in the hierarchy.

        mode (Literal["nearest", "farthest"], optional):
            Controls which occurrence of `target_dir` is used.
            Defaults to "nearest".

    Returns:
        str:
            Underscore-joined tool name derived from the relative path.

    Raises:
        FileNotFoundError:
            If the provided path does not exist or is not a file.

        ValueError:
            If `target_dir` is not found anywhere in the file's ancestry.
    """

    # Normalize input into a resolved Path object for consistency across OSes
    path = filepath.resolve() if isinstance(filepath, Path) else Path(filepath).resolve()

    # Ensure we are working with a real file
    if not path.is_file():
        error_msg = f"Invalid file path (does not exist or is not a file): {filepath}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    # Collect all ancestor directories that match the target directory name
    matching_parents = []
    for parent in path.parents:
        if parent.name == target_dir:
            matching_parents.append(parent)

    # Fail fast if no valid anchor directory is found
    if not matching_parents:
        error_msg = (
            f"target_dir='{target_dir}' not found in path hierarchy for file: {filepath}"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Select deterministic anchor based on requested strategy
    if mode == "nearest" or mode == "nearer":
        chosen_parent = matching_parents[0]
        logger.debug(
            "Selected NEAREST target_dir match: %s for file %s",
            chosen_parent,
            filepath,
        )
    elif mode == "farthest" or mode == "farther":
        chosen_parent = matching_parents[-1]
        logger.debug(
            "Selected FARTHEST target_dir match: %s for file %s",
            chosen_parent,
            filepath,
        )

    else:
        logger.error("Invalid mode given! Select from ('nearest', 'farthest')")

    # Remove file extension safely (handles single suffix only, per pathlib semantics)
    clean_path = path.with_suffix("")

    # Build relative structure starting from the directory above target_dir
    relative_path = clean_path.relative_to(chosen_parent.parent)

    # Flatten path segments into a deterministic tool name
    tool_name = "_".join(relative_path.parts)

    logger.debug(
        "Generated tool name='%s' from file='%s' using target_dir='%s' (mode=%s)",
        tool_name,
        filepath,
        target_dir,
        mode,
    )

    return tool_name

