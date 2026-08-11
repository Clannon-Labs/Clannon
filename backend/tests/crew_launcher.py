"""Hermetic tests for role-scoped interactive session resumption."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CREW = REPO_ROOT / "scripts" / "crew.sh"
ROLE_DIRS = {
    "backend": REPO_ROOT,
    "frontend": REPO_ROOT / "frontend",
    "memory": REPO_ROOT / "backend" / "core" / "memory",
    "orchestration": REPO_ROOT / "backend" / "core" / "orchestrator",
    "security": REPO_ROOT / "backend" / "security",
    "api": REPO_ROOT / "backend" / "api",
    "backend-audit": REPO_ROOT / "backend-audit",
    "frontend-audit": REPO_ROOT / "frontend-audit",
    "release": REPO_ROOT / "release",
}


def _write_session(codex_home: Path, cwd: Path, source: str = "cli") -> None:
    session = codex_home / "sessions" / "2026" / "08" / "09" / f"{cwd.name}.jsonl"
    session.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"type": "session_meta", "payload": {"cwd": str(cwd), "source": source}}
    session.write_text(json.dumps(metadata, separators=(",", ":")) + "\n", encoding="utf-8")


def _write_claude_session(projects_root: Path, cwd: Path) -> None:
    session = projects_root / str(cwd).replace("/", "-") / "session.jsonl"
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text("{}\n", encoding="utf-8")


def _start(
    tmp_path: Path,
    role: str,
    *flags: str,
    with_codex: bool = True,
) -> tuple[subprocess.CompletedProcess[str], str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    tmux_log = tmp_path / "tmux.log"
    fake_tmux = fake_bin / "tmux"
    fake_tmux.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"${1:-}\" = has-session ]; then exit 1; fi\n"
        "printf '%s\\n' \"$@\" > \"$TMUX_LOG\"\n",
        encoding="utf-8",
    )
    fake_tmux.chmod(0o755)

    env = os.environ.copy()
    env.pop("CODEX_HOME", None)
    env.update(
        HOME=str(tmp_path / "home"),
        PATH=f"{fake_bin}:{env['PATH']}",
        TMUX_LOG=str(tmux_log),
        CLANNON_AGENT_RUNTIME=str(tmp_path / "runtime"),
    )
    args = [str(CREW), "start", role]
    if with_codex:
        args.append("--codex")
    args.extend(flags)
    result = subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, tmux_log.read_text(encoding="utf-8")


class CrewLauncherTest(unittest.TestCase):
    def test_frontend_audit_tooling_is_exact_and_separate_from_project(self):
        """Coordinator-owned audit pins must never rewrite frontend dependencies."""
        tooling = REPO_ROOT / "frontend-audit" / "tooling"
        manifest = json.loads((tooling / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((tooling / "package-lock.json").read_text(encoding="utf-8"))
        expected = {
            "@playwright/test": "1.62.0",
            "eslint": "9.39.4",
            "eslint-config-next": "16.2.12",
            "npm": "11.19.0",
            "typescript": "5.9.3",
            "vitest": "4.1.9",
        }

        self.assertEqual(manifest["dependencies"], expected)
        self.assertEqual(lock["packages"][""]["dependencies"], expected)
        for package, version in expected.items():
            self.assertEqual(lock["packages"][f"node_modules/{package}"]["version"], version)

    def test_backend_audit_defaults_to_claude_in_the_sandbox(self):
        """No flag means Claude for every role; the auditor is not an exception."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)

            result, tmux_call = _start(
                tmp_path,
                "backend-audit",
                with_codex=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[claude, fresh", result.stdout)
            self.assertIn("audit-sandbox.sh backend-audit start --claude", tmux_call)

    def test_frontend_audit_uses_the_same_launcher_with_its_own_role(self):
        """Both audit roles share one enforced launcher; role is a parameter."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)

            result, tmux_call = _start(tmp_path, "frontend-audit", with_codex=False)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[claude, fresh", result.stdout)
            self.assertIn("audit-sandbox.sh frontend-audit start --claude", tmux_call)
            self.assertNotIn("backend-audit", tmux_call)

    def test_backend_audit_honours_explicit_codex(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)

            result, tmux_call = _start(tmp_path, "backend-audit")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[codex, fresh", result.stdout)
            self.assertIn("audit-sandbox.sh backend-audit start --codex", tmux_call)

    def test_backend_audit_on_claude_uses_the_same_enforced_sandbox(self):
        """Claude is a launcher parameter, never a way around the boundary."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)

            result, tmux_call = _start(
                tmp_path,
                "backend-audit",
                "--claude",
                with_codex=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[claude, fresh", result.stdout)
            self.assertIn("audit-sandbox.sh backend-audit start --claude", tmux_call)
            self.assertNotIn("claude --dangerously-skip-permissions", tmux_call)

    def test_backend_audit_resumes_claude_from_its_isolated_config_dir(self):
        """The auditor's transcripts live in its runtime, not the owner's ~/.claude."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _write_claude_session(
                tmp_path / "runtime" / "backend-audit" / "claude-home" / "projects",
                ROLE_DIRS["backend-audit"],
            )

            result, tmux_call = _start(
                tmp_path,
                "backend-audit",
                "--claude",
                with_codex=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[claude, resuming prior conversation]", result.stdout)
            self.assertIn("audit-sandbox.sh backend-audit resume --claude", tmux_call)

    def test_backend_audit_ignores_owner_claude_sessions(self):
        """A session in the owner's own config dir must not resume the auditor."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _write_claude_session(
                tmp_path / "home" / ".claude" / "projects",
                ROLE_DIRS["backend-audit"],
            )

            result, tmux_call = _start(
                tmp_path,
                "backend-audit",
                "--claude",
                with_codex=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[claude, fresh", result.stdout)
            self.assertIn("audit-sandbox.sh backend-audit start --claude", tmux_call)

    def test_codex_resumes_interactive_session_for_each_role(self):
        for role, cwd in ROLE_DIRS.items():
            with self.subTest(role=role), tempfile.TemporaryDirectory() as temp_dir:
                tmp_path = Path(temp_dir)
                if role in ("backend-audit", "frontend-audit"):
                    codex_home = tmp_path / "runtime" / role / "codex-home"
                else:
                    codex_home = tmp_path / "home" / ".codex"
                _write_session(codex_home, cwd)

                result, tmux_call = _start(tmp_path, role)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("[codex, resuming prior conversation]", result.stdout)
                if role in ("backend-audit", "frontend-audit"):
                    self.assertIn(f"audit-sandbox.sh {role} resume --codex", tmux_call)
                else:
                    self.assertIn("codex resume --last", tmux_call)
                    self.assertNotIn("--all", tmux_call)

    def test_codex_does_not_resume_another_roles_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _write_session(tmp_path / "home" / ".codex", ROLE_DIRS["backend"])

            result, tmux_call = _start(tmp_path, "frontend")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "[codex, fresh (no prior conversation for this directory)]",
                result.stdout,
            )
            self.assertNotIn("codex resume --last", tmux_call)

    def test_codex_fresh_flag_skips_matching_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _write_session(tmp_path / "home" / ".codex", ROLE_DIRS["backend"])

            result, tmux_call = _start(tmp_path, "backend", "--fresh")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[codex, fresh (forced)]", result.stdout)
            self.assertNotIn("codex resume --last", tmux_call)

    def test_codex_does_not_resume_headless_worker_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            _write_session(tmp_path / "home" / ".codex", ROLE_DIRS["api"], source="exec")

            result, tmux_call = _start(tmp_path, "api")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(
                "[codex, fresh (no prior conversation for this directory)]",
                result.stdout,
            )
            self.assertNotIn("codex resume --last", tmux_call)


if __name__ == "__main__":
    unittest.main()
