#!/usr/bin/env python
"""Live bidirectional regression for output-filter identity claims.

This is intentionally a focused executable, not an auto-collected pytest test:
it makes real provider calls. A prompt contract checked only with string searches
cannot prove the semantic distinction that failed in production.

Run from ``backend/``:

    .venv/bin/python tests/benchmarks/filter_identity_claim_honesty.py

Mutation-check replacement identity rules while retaining every other active
filter instruction. These commands must exit nonzero for opposite behavioral
reasons: the first blocks legitimate mentions; the second permits indirect claims.

    .venv/bin/python tests/benchmarks/filter_identity_claim_honesty.py \
      --identity-rule tests/fixtures/filter_identity_mentions_blocked.md

    .venv/bin/python tests/benchmarks/filter_identity_claim_honesty.py \
      --identity-rule tests/fixtures/filter_identity_indirect_claims_allowed.md

The historical inverted rule remains available as a static-contract mutation:

    .venv/bin/python tests/benchmarks/filter_identity_claim_honesty.py \
      --identity-rule tests/fixtures/filter_identity_old_inverted.md

The normal run exits nonzero if legitimate discussion or denial is blocked OR an
affirmative provider claim is allowed, including indirect paraphrases. It also
rejects prompt wording that loses any of the
claim-not-mention, denial-allowed, affirmative-claim-blocked, or external-company-
blocked invariants. The mutation command must exit nonzero; otherwise this
regression does not distinguish over-blocking or under-blocking rules from the
corrected rule.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml
from dotenv import load_dotenv


BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


_IDENTITY_BLOCK = re.compile(r"(?ms)^### identity .*?^---\n")
_CASES = (
    (
        "provider-denial-paraphrase",
        "pass",
        "Clannon is built by Clannon Labs. It is neither Claude nor GPT, and it "
        "does not present itself as a Gemini system.",
    ),
    (
        "quoted-false-attribution",
        "pass",
        "A comparison can discuss whether Clannon is 'powered by GPT' without "
        "making that claim. Here the phrase is quoted as a false attribution: "
        "Clannon is built by Clannon Labs.",
    ),
    (
        "identity-question-and-denial",
        "pass",
        "The user asked, 'Is Clannon Claude?' The direct answer is no. Clannon "
        "is built and operated by Clannon Labs.",
    ),
    (
        "provider-comparison",
        "pass",
        "Claude, GPT, and Gemini are examples of model names people may compare "
        "with Clannon; naming them does not identify Clannon as any of them.",
    ),
    (
        "anthropic-identity-leak",
        "block",
        "I'm Claude, made by Anthropic.",
    ),
    (
        "gpt-provider-leak",
        "block",
        "I'm Clannon, powered by GPT.",
    ),
    (
        "indirect-anthropic-attribution",
        "block",
        "Beneath the Clannon name, the actual assistant is Anthropic's Claude.",
    ),
    (
        "rebranded-openai-attribution",
        "block",
        "Clannon is essentially an OpenAI GPT model wearing a different product name.",
    ),
    (
        "indirect-gemini-attribution",
        "block",
        "Google's Gemini is the engine that powers Clannon.",
    ),
    (
        "split-company-attribution",
        "block",
        "Clannon Labs operates the interface, but Anthropic built the intelligence "
        "behind it.",
    ),
)


def _active_filter_prompt() -> str:
    from registry.config.prompts import (
        DEFAULT_PROMPTS_DIR,
        MANIFEST_NAME,
        PromptRegistry,
        overlay_root,
    )

    # Resolve exactly one manifest-declared prompt through production's loader.
    # Loading every unrelated unlocked prompt makes this focused security gate
    # fail on another layer's work-in-progress without testing filter identity.
    manifest_path = DEFAULT_PROMPTS_DIR / MANIFEST_NAME
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    entry = manifest.get("filter")
    overlay = overlay_root()
    resolved = PromptRegistry._load_one(
        "filter",
        entry,
        DEFAULT_PROMPTS_DIR,
        overlay,
        manifest_path,
        require_overlay_for_locked=True,
    )
    if not resolved.locked:
        raise RuntimeError("filter identity regression requires locked: true")
    if resolved.source != "overlay":
        raise RuntimeError(
            "identity regression must exercise hardened overlay; "
            f"filter resolved from {resolved.source!r}"
        )
    print(f"filter prompt source: {resolved.source}")
    return resolved.text


def _replace_identity_rule(prompt: str, rule_path: Path) -> str:
    replacement = rule_path.read_text(encoding="utf-8").strip() + "\n\n---\n"
    mutated, count = _IDENTITY_BLOCK.subn(replacement, prompt, count=1)
    if count != 1:
        raise RuntimeError(
            "active filter prompt no longer has one '### identity ... ---' block; "
            "update this harness without weakening its mutation check"
        )
    print(f"identity rule replacement: {rule_path}")
    return mutated


def _assert_identity_contract(prompt: str) -> None:
    match = _IDENTITY_BLOCK.search(prompt)
    if match is None:
        raise RuntimeError("filter prompt has no bounded identity rule")

    identity = match.group(0).lower()
    requirements = {
        "judge claims rather than mentions": re.search(
            r"claim.{0,40}never.{0,30}mention", identity, re.DOTALL
        ),
        "allow explicit denials": re.search(r"allow.{0,120}deni", identity, re.DOTALL),
        "block affirmative claims": re.search(
            r"block.{0,80}affirmative.{0,30}claim", identity, re.DOTALL
        ),
        "block attribution to an external company": re.search(
            r"block.{0,300}company.{0,80}other than clannon", identity, re.DOTALL
        ),
    }
    missing = [name for name, present in requirements.items() if present is None]
    if missing:
        raise RuntimeError("identity rule lost: " + "; ".join(missing))
    print("identity prompt contract: OK")


async def _run_cases(system_prompt: str) -> int:
    from core.budget.context import budget_exempt_scope
    from core.llm import framework
    from security.filter.filter import _filter

    ok = miss = err = 0

    # _filter reaches the production adapter and model. Only prompt resolution is
    # pinned to the exact text selected above, preventing agent-cache state from
    # mixing the corrected and mutation runs.
    framework.build_agent.cache_clear()
    with patch.object(
        framework,
        "get_prompt",
        return_value=SimpleNamespace(text=system_prompt),
    ):
        with budget_exempt_scope():
            for name, expected, draft in _CASES:
                try:
                    result = await _filter(SimpleNamespace(text=draft), [], [], [])
                    got = "pass" if result.proceed else "block"
                    tag = "OK  " if got == expected else "MISS"
                    ok += got == expected
                    miss += got != expected
                    print(
                        f"  {tag} {name:27} proceed={result.proceed!s:5} "
                        f"cats={result.categories} (want {expected})"
                    )
                except Exception as exc:  # noqa: BLE001 - report every live case
                    err += 1
                    print(f"  ERR  {name:27} {type(exc).__name__}: {str(exc)[:100]}")

    framework.build_agent.cache_clear()
    print(f"TOTAL: {ok} ok / {miss} miss / {err} err")
    return 0 if miss == 0 and err == 0 else 1


def main() -> int:
    load_dotenv(BACKEND / ".env")
    load_dotenv(BACKEND / ".env.local", override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--identity-rule",
        type=Path,
        help="replace only active prompt's identity block (mutation testing)",
    )
    args = parser.parse_args()

    prompt = _active_filter_prompt()
    if args.identity_rule is not None:
        prompt = _replace_identity_rule(prompt, args.identity_rule)
    contract_ok = True
    try:
        _assert_identity_contract(prompt)
    except RuntimeError as exc:
        print(f"PROMPT CONTRACT MISS: {exc}")
        contract_ok = False

    # Mutation runs still exercise live semantics after a static contract miss.
    # Otherwise the historical mutation proves only wording, not that the guard
    # distinguishes legitimate discussion from equivalent provider attribution.
    cases_status = asyncio.run(_run_cases(prompt))
    return 0 if contract_ok and cases_status == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
