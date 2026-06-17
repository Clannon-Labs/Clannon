"""
Expert skills — loaded on demand, never dumped into context.

Each entry in an expert's `skills=(...)` is a `.md` file or a folder beside the
expert. Progressive disclosure: only each skill's name + short description is
surfaced up front (see `skills_hint`); the full body is handed over only when the
expert calls `load_skill`. This keeps context lean as the skill set grows. Each
skill file is resolved through the prompt overlay (prod text wins, the committed
file is the fallback), so the overlay can harden a skill but never introduce one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .overlay import overlaid


@dataclass
class _Skill:
    """One resolved skill: its name, a short when-to-use description (from the
    file's optional frontmatter), and its body (the full guide, handed over on
    demand)."""
    name: str
    description: str
    body: str


def _parse_skill(path: Path) -> tuple[str, str]:
    """Split a skill file into (description, body).

    The description comes from an optional `---`-delimited frontmatter
    `description:` line; it is surfaced up front so the expert can pick a skill
    WITHOUT loading its body. The body is the full guide handed over only on
    load_skill(). A file with no frontmatter has an empty description and is its
    own body.
    """
    text = path.read_text(encoding="utf-8").strip()
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    frontmatter, body = text[3:end], text[end + 4:].strip()
    description = ""
    for line in frontmatter.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("description:"):
            description = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            break
    return description, body


class SkillBook:
    """
    The skills available to an expert, resolved beside its module.

    Each entry in the expert's `skills=(...)` is a `.md` file or a folder (whose
    `.md` files are all offered), located beside the expert. Progressive
    disclosure: only each skill's name + short description is surfaced to the
    expert up front (see skills_hint); the full body is handed over only when the
    expert calls `load()`. This keeps context lean as the skill set grows.
    """

    def __init__(self, base_dir: Path, entries: tuple[str, ...]) -> None:
        # The SET of skills is defined by the committed files beside the expert;
        # each is then resolved through the prompt overlay (prod text wins, the
        # committed file is the fallback), so the overlay can harden a skill but
        # never introduce one. Each file is read once here to split its up-front
        # description from its on-demand body — the body is NOT put in context now.
        self._skills: dict[str, _Skill] = {}
        for entry in entries:
            path = base_dir / entry
            if path.is_dir():
                files = sorted(path.glob("*.md"))
            elif path.is_file():
                files = [path]
            else:
                files = []
            for md in files:
                description, body = _parse_skill(overlaid(base_dir, md))
                self._skills[md.stem] = _Skill(md.stem, description, body)

    def names(self) -> list[str]:
        """Skill names this expert may load."""
        return sorted(self._skills)

    def catalog(self) -> list[tuple[str, str]]:
        """(name, description) per skill — what's surfaced up front so the expert
        can choose a skill to load without seeing its body."""
        return [(name, self._skills[name].description) for name in sorted(self._skills)]

    def load(self, name: str) -> str:
        """Return one skill's full body by name, or a clear not-found note."""
        skill = self._skills.get(name)
        if skill is None:
            return f"[no skill named {name!r}; available: {', '.join(self.names()) or 'none'}]"
        return skill.body


def skills_hint(skills: SkillBook) -> str:
    """A short instruction appended to the system prompt so the expert knows which
    skills exist and WHEN to pull each one. Only names + descriptions go here; the
    full skill body is handed over on demand via load_skill (progressive
    disclosure), so this stays small as the skill set grows."""
    catalog = skills.catalog()
    if not catalog:
        return ""
    listing = "\n".join(
        f"- {name}: {desc}" if desc else f"- {name}" for name, desc in catalog
    )
    return (
        "\n\nYou have loadable skills — reference guides that are NOT yet in your "
        "context. Each is listed below as `name: when to use it`. Call "
        "load_skill(name) to read a skill's full guide ONLY when it is relevant to "
        "the current step; do not assume its contents otherwise:\n" + listing
    )
