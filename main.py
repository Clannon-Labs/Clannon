"""
CLI entry point for the Vraksha pipeline.

Two modes:

    .venv/bin/python main.py "your brief"    one-shot, exit code reflects outcome
    .venv/bin/python main.py                 interactive TUI

(The `vraksha` command installed by install.sh lands in the same place,
running this file inside the runtime container.)

The TUI keeps the terminal clean: you see your prompts, a live activity
feed while the pipeline works, and the answer. Full details (decision log,
stage summaries, library warnings) are appended to vraksha.log. Identity is
set once here (VRAKSHA_USER_ID, default "local-user") and travels in Flow
context.
"""

import asyncio
import logging
import os
import sys
import time
import uuid

from dotenv import load_dotenv

# Load environment before anything constructs provider clients. .env carries
# non-secret config (e.g. CLAMAV_HOST); .env.local holds secrets like the
# provider API key and overrides .env. The provider SDK reads the key from env.
load_dotenv(".env")
load_dotenv(".env.local", override=True)

# the google SDK prints a warning when both key names are set — pick one
if os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
    os.environ.pop("GEMINI_API_KEY", None)

from core import pipeline

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vraksha.log")

# display label per pipeline stage, in ACTIVE_STAGES order
_STAGE_LABELS = [
    "taking it in",
    "scanning input",
    "normalizing",
    "verifying",
    "working",
    "checking the answer",
    "delivering",
]

_KIND_GLYPH = {
    "hydration": "◈",
    "route": "→",
    "expert_spawn": "✦",
    "tool_call": "⚙",
    "observation": "·",
    "answer": "✓",
    "warning": "!",
    "error": "✗",
}


def _log_lines(lines: list[str]) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


class _ObservedLog(list):
    """Decision-log list that mirrors every append to the TUI."""

    def __init__(self, on_entry) -> None:
        super().__init__()
        self._on_entry = on_entry

    def append(self, entry) -> None:
        super().append(entry)
        self._on_entry(entry)


def _write_run_log(brief: str, session_id: str, user_id: str, flow, summary: dict) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"[{stamp}] user={user_id} session={session_id}", f"  brief: {brief[:300]}"]
    for entry in flow.ctx.decision_log:
        lines.append(f"  [{getattr(entry, 'kind', '?')}] {getattr(entry, 'message', entry)}")
    lines.append(f"  summary: {summary}")
    _log_lines(lines)


async def _one_shot(brief: str, user_id: str) -> int:
    # old behavior, scripts rely on it: delivery prints log + answer itself
    flow = await pipeline.run(brief, session_id="cli", user_id=user_id)
    _write_run_log(brief, "cli", user_id, flow, flow.summary())
    return 1 if flow.should_stop else 0


async def _repl(user_id: str) -> int:
    from foundation import Flow
    from rich.console import Console, Group
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.text import Text

    os.environ["VRAKSHA_CLI_QUIET"] = "1"  # the TUI renders the answer itself
    logging.basicConfig(
        filename=LOG_PATH, level=logging.WARNING,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    console = Console()
    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    console.print()
    console.print("[bold green]▲ vraksha[/] [dim]· research that remembers[/]")
    console.print(f"[dim]  user {user_id} · session {session_id} · details → vraksha.log[/]")
    console.print("[dim]  type a brief · /exit quits[/]\n")

    while True:
        try:
            brief = console.input("[bold green]you ›[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/]")
            return 0
        if not brief:
            continue
        if brief in ("/exit", "/quit", "exit", "quit"):
            console.print("[dim]bye[/]")
            return 0
        if brief == "/help":
            console.print("[dim]type a research brief and hit enter. /exit quits.[/]")
            continue

        # ---- live run: stage chain with an observed decision log --------
        activity: list[Text] = []
        stage_label = ["starting"]
        spinner = Spinner("dots", text=Text("starting", style="dim"), style="green")

        def _render() -> Group:
            spinner.update(text=Text(f"{stage_label[0]}…", style="dim"))
            return Group(*activity[-6:], spinner)

        def _on_entry(entry) -> None:
            kind = getattr(entry, "kind", "observation")
            message = str(getattr(entry, "message", entry))
            glyph = _KIND_GLYPH.get(kind, "·")
            style = "red" if kind == "error" else ("yellow" if kind == "warning" else "dim")
            activity.append(Text(f"  {glyph} {message[:110]}", style=style))

        started = time.monotonic()
        flow = Flow.new(brief, session_id=session_id, user_id=user_id)
        flow.ctx.decision_log = _ObservedLog(_on_entry)

        try:
            with Live(_render(), console=console, refresh_per_second=10, transient=True) as live:
                for stage, label in zip(pipeline.ACTIVE_STAGES, _STAGE_LABELS):
                    if flow.should_stop:
                        break
                    stage_label[0] = label
                    live.update(_render())
                    flow = await stage(flow)
                    live.update(_render())
        except KeyboardInterrupt:
            console.print("[yellow]run interrupted[/]\n")
            continue
        except Exception as exc:  # the TUI survives anything a run throws
            console.print(f"[bold red]run crashed[/] [dim]({exc})[/]\n")
            continue

        summary = flow.summary()
        _write_run_log(brief, session_id, user_id, flow, summary)
        took = f"{time.monotonic() - started:.1f}s"
        steps = len(flow.ctx.decision_log)

        if flow.should_stop:
            reason = summary.get("reason") or summary.get("error") or "no reason given"
            console.print(
                Panel(
                    str(reason)[:400],
                    title=f"[red]{summary.get('status', 'stopped')} at {summary.get('origin', '?')}[/]",
                    subtitle=f"[dim]{took} · vraksha.log has the trace[/]",
                    border_style="red",
                )
            )
        else:
            answer = str(flow.ctx.final_response or "(no answer produced)")
            console.print(
                Panel(
                    Markdown(answer),
                    title="[green]vraksha[/]",
                    subtitle=f"[dim]{steps} steps · {took}[/]",
                    border_style="green",
                )
            )
        console.print()


async def _main() -> int:
    user_id = os.getenv("VRAKSHA_USER_ID", "local-user")
    if len(sys.argv) > 1:
        return await _one_shot(sys.argv[1], user_id)
    if not sys.stdin.isatty():
        return await _one_shot(sys.stdin.read(), user_id)
    return await _repl(user_id)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
