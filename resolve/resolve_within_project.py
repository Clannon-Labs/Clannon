from pathlib import Path

from resolve.resolve_result import ResolveResult
from get_root import root

PROJECT_ROOT = root.project.resolve()

def resolve_path(path_str: str) -> ResolveResult:
    """Resolve `path` and ensure it lives under PROJECT_ROOT.

    Accepts both relative (preferred) and absolute paths.
    Raises ValueError if the resolved path escapes the project root,
    protects against `../`-style traversal and absolute-path escapes alike.
    """
    try:
        requested_path = Path(path_str)

        if not requested_path.is_absolute():
            full_path = (PROJECT_ROOT / requested_path).resolve()
        else:
            full_path = requested_path.resolve()

        full_path.relative_to(PROJECT_ROOT)
        
        return ResolveResult(success=True, result=full_path)

    except (ValueError, RuntimeError):
        return ResolveResult(
            success=False, 
            error=f"Access Denied: '{path_str}' is outside project root."
        )