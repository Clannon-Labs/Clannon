"""Deploy-time prompt overlay: resolution, auto-discovery, fail-closed boot, and
the expert-side wiring.

The production prompts for every LLM call (verifier/filter/orchestrator/memory +
each expert's system.md and skills) live outside git in one overlay folder; the
committed prompts/ and experts/*/ files are dev/CI baselines. These tests pin the
contract: overlay wins, missing entries fall back, the folder auto-discovers, a
locked prompt can be forced to come from the overlay, the overlay can never
weaken the manifest, and the overlay can harden an expert skill but not add one.
"""

import pytest

from foundation import ConfigError
import registry.config.prompts as P
import registry.capabilities.handler.support as S
from registry.config.prompts import PromptRegistry, get_prompt, load_prompt_registry


def _make_base(tmp_path):
    base = tmp_path / "prompts"
    for name in ("verifier", "filter", "orchestrator"):
        (base / name).mkdir(parents=True)
        (base / name / "system.md").write_text(f"BASELINE {name}", encoding="utf-8")
    (base / "registry.yaml").write_text(
        "verifier:\n  version: 1\n  file: verifier/system.md\n  locked: true\n"
        "filter:\n  version: 1\n  file: filter/system.md\n  locked: true\n"
        "orchestrator:\n  version: 1\n  file: orchestrator/system.md\n  locked: false\n",
        encoding="utf-8",
    )
    return base


def _overlay(tmp_path, **files):
    overlay = tmp_path / "safe"
    overlay.mkdir(exist_ok=True)
    for name, text in files.items():
        (overlay / name).mkdir(parents=True, exist_ok=True)
        (overlay / name / "system.md").write_text(text, encoding="utf-8")
    return overlay


def test_no_overlay_uses_committed_baseline(tmp_path):
    reg = PromptRegistry.from_dir(_make_base(tmp_path))
    assert reg.get("verifier").text == "BASELINE verifier"
    assert reg.get("verifier").source == "baseline"


def test_overlay_content_wins_partial_falls_back(tmp_path):
    base = _make_base(tmp_path)
    overlay = _overlay(tmp_path, verifier="HARDENED verifier")
    reg = PromptRegistry.from_dir(base, overlay_dir=overlay)
    assert reg.get("verifier").text == "HARDENED verifier"
    assert reg.get("verifier").source == "overlay"
    # a prompt absent from the overlay still rides the baseline
    assert reg.get("filter").text == "BASELINE filter"
    assert reg.get("filter").source == "baseline"


def test_require_prod_fails_closed_when_locked_on_baseline(tmp_path):
    base = _make_base(tmp_path)
    # overlay supplies the unlocked orchestrator but NOT the locked verifier/filter
    overlay = _overlay(tmp_path, orchestrator="HARDENED orch")
    with pytest.raises(ConfigError) as exc:
        PromptRegistry.from_dir(base, overlay_dir=overlay, require_overlay_for_locked=True)
    assert "locked" in str(exc.value)
    assert "verifier" in str(exc.value)


def test_require_prod_passes_when_locked_overlaid(tmp_path):
    base = _make_base(tmp_path)
    overlay = _overlay(tmp_path, verifier="HARDENED v", filter="HARDENED f")
    reg = PromptRegistry.from_dir(base, overlay_dir=overlay, require_overlay_for_locked=True)
    assert reg.get("verifier").source == "overlay"
    assert reg.get("filter").source == "overlay"
    # an unlocked prompt may still ride the baseline under require mode
    assert reg.get("orchestrator").source == "baseline"


def test_overlay_cannot_unlock_or_reversion_a_prompt(tmp_path):
    # the manifest (and its locked flags + versions) is read ONLY from base; a
    # rogue overlay registry.yaml is ignored entirely.
    base = _make_base(tmp_path)
    overlay = _overlay(tmp_path, verifier="HARDENED verifier")
    (overlay / "registry.yaml").write_text(
        "verifier:\n  version: 99\n  file: verifier/system.md\n  locked: false\n",
        encoding="utf-8",
    )
    v = PromptRegistry.from_dir(base, overlay_dir=overlay).get("verifier")
    assert v.locked is True   # base manifest wins
    assert v.version == 1
    assert v.text == "HARDENED verifier"  # but overlay content still applies


def test_env_driven_load_reads_overlay(tmp_path, monkeypatch):
    base = _make_base(tmp_path)
    overlay = _overlay(tmp_path, verifier="ENV verifier")
    monkeypatch.setenv("VRAKSHA_PROMPTS_DIR", str(overlay))
    load_prompt_registry.cache_clear()
    try:
        assert get_prompt("verifier", base_dir=base).text == "ENV verifier"
    finally:
        load_prompt_registry.cache_clear()


def test_env_require_flag_fails_closed(tmp_path, monkeypatch):
    base = _make_base(tmp_path)
    overlay = _overlay(tmp_path)  # empty: no locked prompts present
    monkeypatch.setenv("VRAKSHA_PROMPTS_DIR", str(overlay))
    monkeypatch.setenv("VRAKSHA_REQUIRE_PROD_PROMPTS", "1")
    load_prompt_registry.cache_clear()
    try:
        with pytest.raises(ConfigError):
            get_prompt("verifier", base_dir=base)
    finally:
        load_prompt_registry.cache_clear()


# --------------------------------------------------------------------------
# overlay_root() / resolve_overlay() — the shared resolver (registry + experts)
# --------------------------------------------------------------------------

def test_overlay_root_env_then_autodiscover_cwd_then_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir()
    cwd = tmp_path / "cwd"; cwd.mkdir()
    monkeypatch.setattr(P, "REPO_ROOT", repo)
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("VRAKSHA_PROMPTS_DIR", raising=False)

    # nothing present -> baselines
    assert P.overlay_root() is None
    # drop the folder beside the code (repo root) -> auto-discovered
    (repo / P.PROD_DIRNAME).mkdir()
    assert P.overlay_root() == repo / P.PROD_DIRNAME
    # one where the agent runs (CWD) is checked first
    (cwd / P.PROD_DIRNAME).mkdir()
    assert P.overlay_root() == cwd / P.PROD_DIRNAME
    # an explicit env var beats auto-discovery
    monkeypatch.setenv("VRAKSHA_PROMPTS_DIR", str(tmp_path / "explicit"))
    assert P.overlay_root() == tmp_path / "explicit"


def test_resolve_overlay_overlay_first_then_baseline(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir()
    monkeypatch.setattr(P, "REPO_ROOT", repo)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("VRAKSHA_PROMPTS_DIR", raising=False)
    baseline = tmp_path / "base.md"; baseline.write_text("BASE", encoding="utf-8")

    path, src = P.resolve_overlay("verifier/system.md", baseline)
    assert path == baseline and src == "baseline"

    ov = repo / P.PROD_DIRNAME / "verifier"; ov.mkdir(parents=True)
    (ov / "system.md").write_text("OVER", encoding="utf-8")
    path, src = P.resolve_overlay("verifier/system.md", baseline)
    assert src == "overlay" and path.read_text(encoding="utf-8") == "OVER"


def test_read_overlay_text_raises_on_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VRAKSHA_PROMPTS_DIR", raising=False)
    with pytest.raises(ConfigError):
        P.read_overlay_text("x/system.md", tmp_path / "nope.md")


# --------------------------------------------------------------------------
# Characterization: _load_one resolves content with its own inline overlay-first
# precedence (it predates and duplicates resolve_overlay). These pin that the two
# code paths agree today — the inline path's (source, resolved file) matches what
# the canonical resolve_overlay() returns for the same overlay root. Pure
# characterization: assert current behavior, change neither path. If someone later
# folds _load_one onto resolve_overlay, these should keep passing unchanged.
# --------------------------------------------------------------------------

def _assert_inline_matches_resolve_overlay(monkeypatch, base, overlay, relative):
    """_load_one's inline overlay precedence resolves to the same (source, file
    content) as resolve_overlay(relative, base/relative).

    overlay_root() (which resolve_overlay consults) is pinned to the SAME overlay
    _load_one is handed explicitly, so the comparison isolates the precedence rule
    from overlay *discovery* (env/CWD/repo auto-detect, covered by other tests)."""
    monkeypatch.setattr(P, "overlay_root", lambda: overlay)

    expected_path, expected_source = P.resolve_overlay(relative, base / relative)
    expected_text = expected_path.read_text(encoding="utf-8").strip()

    # locked + require=False so only the precedence branch runs (no fail-closed
    # raise); about is omitted so text equals the raw resolved file content.
    entry = {"version": 1, "file": relative, "locked": True}
    prompt = PromptRegistry._load_one(
        "verifier", entry, base, overlay, base / "registry.yaml",
        require_overlay_for_locked=False,
    )

    assert prompt.source == expected_source
    assert prompt.text == expected_text


def test_load_one_inline_precedence_no_overlay_matches_resolver(tmp_path, monkeypatch):
    # overlay is None -> both paths take the committed baseline.
    base = _make_base(tmp_path)
    _assert_inline_matches_resolve_overlay(monkeypatch, base, None, "verifier/system.md")


def test_load_one_inline_precedence_overlay_hit_matches_resolver(tmp_path, monkeypatch):
    # overlay supplies the file -> both paths take the overlay content.
    base = _make_base(tmp_path)
    overlay = _overlay(tmp_path, verifier="HARDENED verifier")
    _assert_inline_matches_resolve_overlay(monkeypatch, base, overlay, "verifier/system.md")


def test_load_one_inline_precedence_overlay_miss_matches_resolver(tmp_path, monkeypatch):
    # overlay exists but lacks this prompt -> both paths fall back to the baseline.
    base = _make_base(tmp_path)
    overlay = _overlay(tmp_path, filter="HARDENED filter")  # has filter, not verifier
    _assert_inline_matches_resolve_overlay(monkeypatch, base, overlay, "verifier/system.md")


# --------------------------------------------------------------------------
# Expert-side wiring (support.py): system.md + skills ride the same overlay
# --------------------------------------------------------------------------

def test_expert_overlay_rel_mirrors_repo_layout(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "REPO_ROOT", tmp_path)
    module_dir = tmp_path / "experts" / "web_research"
    module_dir.mkdir(parents=True)
    assert S._expert_overlay_rel(module_dir, "system.md") == "experts/web_research/system.md"
    assert S._expert_overlay_rel(module_dir, "skills", "x.md") == "experts/web_research/skills/x.md"


def test_overlaid_resolves_expert_system_md(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VRAKSHA_PROMPTS_DIR", raising=False)
    module_dir = tmp_path / "experts" / "web_research"
    module_dir.mkdir(parents=True)
    baseline = module_dir / "system.md"; baseline.write_text("BASE", encoding="utf-8")

    assert S._overlaid(module_dir, baseline) == baseline   # no overlay -> baseline
    ov = tmp_path / P.PROD_DIRNAME / "experts" / "web_research"; ov.mkdir(parents=True)
    (ov / "system.md").write_text("HARDENED", encoding="utf-8")
    assert S._overlaid(module_dir, baseline).read_text(encoding="utf-8") == "HARDENED"


def test_skillbook_hardens_via_overlay_but_cannot_add_a_skill(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VRAKSHA_PROMPTS_DIR", raising=False)
    module_dir = tmp_path / "experts" / "writer"
    (module_dir / "skills").mkdir(parents=True)
    (module_dir / "skills" / "client_report.md").write_text("BASE skill", encoding="utf-8")

    assert S.SkillBook(module_dir, ("skills",)).load("client_report") == "BASE skill"

    ov = tmp_path / P.PROD_DIRNAME / "experts" / "writer" / "skills"; ov.mkdir(parents=True)
    (ov / "client_report.md").write_text("HARDENED skill", encoding="utf-8")
    (ov / "ghost.md").write_text("ghost", encoding="utf-8")   # not in baseline
    book = S.SkillBook(module_dir, ("skills",))
    assert book.load("client_report") == "HARDENED skill"   # overlay hardens
    assert "ghost" not in book.names()                       # but cannot add


def test_skillbook_surfaces_description_and_strips_frontmatter(tmp_path, monkeypatch):
    # progressive disclosure: name + frontmatter description up front, body on load
    monkeypatch.setattr(P, "REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VRAKSHA_PROMPTS_DIR", raising=False)
    module_dir = tmp_path / "experts" / "writer"
    (module_dir / "skills").mkdir(parents=True)
    (module_dir / "skills" / "brief.md").write_text(
        "---\ndescription: When to use the brief skill.\n---\n\n# Skill: brief\nBody line.",
        encoding="utf-8")
    (module_dir / "skills" / "plain.md").write_text("# Plain\nstuff", encoding="utf-8")

    book = S.SkillBook(module_dir, ("skills",))
    cat = dict(book.catalog())
    assert cat["brief"] == "When to use the brief skill."   # description surfaced
    assert cat["plain"] == ""                                # no frontmatter -> empty desc

    body = book.load("brief")
    assert not body.startswith("---")                        # frontmatter stripped from body
    assert body.startswith("# Skill: brief")                 # body intact
    assert book.load("plain") == "# Plain\nstuff"            # frontmatter-less file is its own body

    hint = S.skills_hint(book)
    assert "brief: When to use the brief skill." in hint      # name: description in the hint
    assert "Body line." not in hint                           # body NOT dumped into context
