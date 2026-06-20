# HANDOFF

## This run (test/load-one-overlay-precedence-characterization)

**What I did**
- Added a characterization test pinning that `PromptRegistry._load_one`'s inline
  overlay-precedence path (`backend/registry/config/prompts.py`, the
  `prompt_path`/`source` block) resolves to the same `(source, file content)` as
  the canonical `resolve_overlay()` helper for the same overlay root.
- Test only. Neither `_load_one` nor `resolve_overlay` was changed; the test
  asserts current behavior so a future refactor that folds the inline path onto
  `resolve_overlay` can be verified as behavior-preserving.
- Location: `backend/tests/prompt_overlay.py`, new section after the
  `resolve_overlay()` tests. Three cases via one helper
  (`_assert_inline_matches_resolve_overlay`):
  - no overlay -> both take the committed baseline
  - overlay supplies the file -> both take the overlay content
  - overlay exists but lacks the prompt -> both fall back to the baseline
  The helper pins `overlay_root()` (what `resolve_overlay` consults) to the same
  overlay `_load_one` is handed explicitly, so the comparison isolates the
  precedence rule from overlay *discovery* (env/CWD/repo auto-detect, already
  covered by sibling tests). This also makes the test immune to the real
  `backend/prompts.secure/` folder being auto-discovered.

**Verification**
- `python -m pytest tests/prompt_overlay.py` -> 17 passed (14 prior + 3 new).
- `pyflakes tests/prompt_overlay.py` -> clean.

**Mid-flight / next / risks**
- Nothing mid-flight. Scope was test-only and is complete.
- Note for a future, separate change (NOT done here): `_load_one`'s inline
  precedence duplicates `resolve_overlay`. These tests now exist so that
  dedup, if pursued, can be done as a verified behavior-preserving refactor.
  That refactor touches the prompts loader (registry domain) and is out of this
  test-only task's scope.
