#!/usr/bin/env bash
#
# Point this clone at the repo's tracked hooks.
#
# `core.hooksPath` is local config, so it cannot itself be tracked — which is the
# usual reason hook-based enforcement quietly fails to exist on somebody's
# machine. Both routine entry points (scripts/crew.sh and dev.sh) call this, so
# a clone becomes enforced by being used rather than by someone remembering.
#
# Idempotent and silent when already correct; safe to call on every launch.

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 0

git rev-parse --git-dir >/dev/null 2>&1 || exit 0

current=$(git config --local --get core.hooksPath || true)
[ "$current" = ".githooks" ] && exit 0

git config --local core.hooksPath .githooks || exit 0
chmod +x .githooks/* 2>/dev/null
echo "✓ git hooks enabled (.githooks) — commit identity is now enforced"
