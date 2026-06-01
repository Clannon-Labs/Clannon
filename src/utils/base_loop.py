from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.text import Text
from rich.theme import Theme
from rich.padding import Padding
from rich.table import Table
from rich import box

from src.utils.find_name import agent_name, user_name
from src.utils.exit_check import check_exit
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory


THEME = Theme({
    "accent":      "#d4a574",   # amber: her eyes (resting)
    "accent_lit":  "#f0c860",   # amber: her eyes (when she looks up)
    "accent_soft": "#8a6f4a",   # amber: deep, for borders
    "teal":        "#4ec9b0",   # robe trim
    "teal_soft":   "#2e7d6f",
    "user_tag":    "#a8c8d8",   # cool soft, for the person across from her
    "ai_tag":      "#d4a574",
    "warn":        "#e0a85a",
    "success":     "#7fb98b",
    "error":       "#c9665a",
    "text":        "#e8dcc4",   # warm cream: like candlelight on paper
    "muted":       "#7a7060",   # warm gray-brown: secondary
    "dim":         "#3d3a30",   # very dim warm: ambient
    "border":      "#2a2620",
    "border_lit":  "#4a4538",
})

console = Console(theme=THEME, highlight=False)


G = {
    "logo":    "◆",   # the keeper's mark
    "user":    "❯",
    "agent":   "◆",
    "dot":     "·",
    "check":   "✓",
    "spark":   "✦",
    "arrow":   "›",
    "diamond": "◇",
    "soft":    "╴",
}

# Persistent session for history and better line editing
session = PromptSession(history=InMemoryHistory())

def _box_width() -> int:
    return min(console.width - 4, 96)


def _cwd_label() -> str:
    cwd, home = Path.cwd(), Path.home()
    try:
        return "~/" + str(cwd.relative_to(home))
    except ValueError:
        return str(cwd)


def _show_branding():
    lines = [
        "██╗   ██╗██████╗  █████╗ ██╗  ██╗███████╗██╗  ██╗ █████╗",
        "██║   ██║██╔══██╗██╔══██╗██║ ██╔╝██╔════╝██║  ██║██╔══██╗",
        "██║   ██║██████╔╝███████║█████╔╝ ███████╗███████║███████║",
        "╚██╗ ██╔╝██╔══██╗██╔══██║██╔═██╗ ╚════██║██╔══██║██╔══██║",
        " ╚████╔╝ ██║  ██║██║  ██║██║  ██╗███████║██║  ██║██║  ██║",
        "  ╚═══╝  ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝",
    ]

    shades = ["#8a6f4a", "#a8855a", "#c69968", "#d4a574", "#c69968", "#a8855a"]
    console.print()
    for line, color in zip(lines, shades):
        console.print(Padding(Text(line, style=f"bold {color}"), (0, 0, 0, 2)))

    tag = Text.assemble(
        Text("        ", style=""),
        Text(G["diamond"], style="accent_lit"),
        Text("  the keeper  ", style="accent"),
        Text(G["dot"], style="dim"),
        Text("  she remembers everything", style="muted italic"),
    )
    console.print(tag)
    console.print()


def _welcome_card(agent: str, user: str):
    greeting = Text.assemble(
        Text(f" {G['logo']}  ", style="bold accent_lit"),
        Text("welcome back, ", style="text"),
        Text(user.lower(), style="bold user_tag"),
    )

    line2 = Text("    i remember everything about you and your projects,", style="muted italic")
    line3 = Text("    so you can focus on creating with a calm mind.",         style="muted italic")
    sep   = Text("    ─────────────────────────────────────", style="dim")

    meta = Table.grid(padding=(0, 2), expand=False)
    meta.add_column(style="muted", justify="left", min_width=8)
    meta.add_column(style="text",  justify="left")
    meta.add_row("    name",   f"[accent]{agent.lower()}[/accent]")
    meta.add_row("    cwd",    _cwd_label())
    meta.add_row("    memory", f"[success]{G['check']}[/success]  [text]ready[/text]")

    body = Group(greeting, Text(""), line2, line3, Text(""), sep, Text(""), meta)

    console.print(
        Padding(
            Panel(
                body,
                box=box.ROUNDED,
                border_style="border_lit",
                padding=(1, 3),
                width=_box_width(),
            ),
            (0, 0, 0, 2),
        )
    )

    hints = Text.assemble(
        Text("  ", style=""),
        Text("speak freely  ", style="muted italic"),
        Text(G["dot"], style="dim"),
        Text("  type ", style="muted"),
        Text("exit", style="accent"),
        Text(" when you're done  ", style="muted"),
        Text(G["dot"], style="dim"),
        Text("  ", style="muted"),
        Text("ctrl-c", style="accent"),
        Text(" to leave abruptly", style="muted"),
    )
    console.print(hints)
    console.print()


def _farewell_card(user: str) -> str:
    console.print()
    farewell = Text.assemble(
        Text(f"  {G['logo']}  ", style="bold accent_lit"),
        Text("until next time, ", style="muted italic"),
        Text(user.lower(), style="bold user_tag"),
    )
    sub = Text("       i'll remember.", style="dim italic")
    console.print(farewell)
    console.print(sub)
    console.print()


def _ask_prompt(input_prompt: str) -> str:
    """Open-frame input, no right border, so long input wraps freely.

    Layout:
        ╭─ ask me anything ╴╴╴╴╴
        │ ❯  user types here, can be very long, will simply
        wrap to the next line without breaking any frame
        ╰╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴╴

    The frame is *open on the right* on purpose, `console.input` cannot
    keep a right border aligned once the line wraps, and a broken right
    border looks worse than no right border. The trailing dotted run on
    the top suggests "open space" rather than a closed box.
    """
    label = f" {input_prompt} "
    # short trailing run of soft dashes, just enough to suggest openness
    trail = "╴" * 4

    top = (
        f"[border_lit]╭─[/border_lit]"
        f"[muted italic]{label}[/muted italic]"
        f"[border_lit]{trail}[/border_lit]"
    )
    bottom = f"[border_lit]╰{'╴' * 24}[/border_lit]"

    console.print(Padding(top, (1, 0, 0, 2)))
    
    # We use rich to render the prompt decorations to ANSI for prompt_toolkit
    prompt_text = f"  [border_lit]│[/border_lit]  [bold accent_lit]{G['user']}[/bold accent_lit]  "
    
    # Simple trick to get ANSI codes out of rich
    with console.capture() as capture:
        console.print(prompt_text, end="")
    ansi_prompt = ANSI(capture.get())

    try:
        raw = session.prompt(ansi_prompt)
    except (KeyboardInterrupt, EOFError):
        # Handle Ctrl+C or Ctrl+D at the prompt gracefully
        return "exit"

    console.print(Padding(bottom, (0, 0, 0, 2)))
    return raw.strip()

def _print_response(agent: str, response: str):
    """Minimal, content-first response block, no heavy panel chrome."""
    console.print()

    header = Text.assemble(
        Text("  "),
        Text(f"{G['agent']}  ", style="bold ai_tag"),
        Text(agent.lower(), style="bold text"),
        Text(f"   {G['dot']}   ", style="dim"),
        Text("she responds", style="muted italic"),
    )
    console.print(header)
    console.print(Padding(Text("│", style="accent_soft"), (0, 0, 0, 3)))
    console.print(
        Padding(
            Markdown(response, code_theme="monokai"),
            (0, 0, 0, 5),
        )
    )
    console.print(Padding(Text("│", style="accent_soft"), (0, 0, 0, 3)))
    console.print()


def _print_correction(agent: str, response: str):
    """Same shape as a response, but with a quiet success accent."""
    console.print()
    header = Text.assemble(
        Text("  "),
        Text(f"{G['check']}  ", style="bold success"),
        Text(agent.lower(), style="bold text"),
        Text(f"   {G['dot']}   ", style="dim"),
        Text("she remembers it differently now", style="success italic"),
    )
    console.print(header)
    console.print(Padding(Text("│", style="success"), (0, 0, 0, 3)))
    console.print(Padding(Markdown(response, code_theme="monokai"), (0, 0, 0, 5)))
    console.print(Padding(Text("│", style="success"), (0, 0, 0, 3)))
    console.print()


def _print_memory_sync(response: str):
    """The end-of-session memory dump, warm amber, like closing a journal."""
    console.print()
    header = Text.assemble(
        Text("  "),
        Text(f"{G['diamond']}  ", style="bold accent_lit"),
        Text("she folds the day away", style="bold text"),
        Text(f"   {G['dot']}   ", style="dim"),
        Text("written to memory", style="accent italic"),
    )
    console.print(header)
    console.print(Padding(Text("│", style="accent_lit"), (0, 0, 0, 3)))
    console.print(Padding(Markdown(response, code_theme="monokai"), (0, 0, 0, 5)))
    console.print(Padding(Text("│", style="accent_lit"), (0, 0, 0, 3)))
    console.print()


def _call_llm_only(llm_fn, messages) -> str:
    """Bare LLM call, no spinner, no exit detection. Always call within a
    console.status() context in the caller."""
    return llm_fn(messages)


def _run_memory_sync(llm_fn, messages, goodbye: str):
    """Commit the session to local indexed memory and print the farewell block."""
    with console.status(
        f"[accent_lit]  she is committing this to memory[/accent_lit]",
        spinner="dots",
        spinner_style="accent_lit",
    ):
        from src.memory.consolidation import run_consolidation

        run_consolidation(list(messages))
        final = "Session consolidated into local indexed memory."

    _print_memory_sync(final)
    console.print(
        Padding(
            Text.assemble(
                Text(f"  {G['check']}  ", style="bold success"),
                Text(goodbye, style="text"),
            ),
            (0, 0, 1, 0),
        )
    )


def run_loop(
    title: str,
    input_prompt: str,
    llm_fn,
    verify_always: bool = False,
    trigger_phrase: str = "VERIFICATION_REQUIRED",
    on_verify=None,
):
    agent = agent_name().capitalize()
    user  = user_name().capitalize()
    messages: list[dict] = []

    
    _show_branding()
    _welcome_card(agent, user)

    # === main loop =================================================
    while True:
        prompt = _ask_prompt(input_prompt)

        if not prompt:
            continue

        if prompt.lower().strip() in ("exit", "quit", "bye", "goodbye"):
            break

        messages.append({
            "role": "user",
            "content": prompt
            })

        with console.status(
            f"[muted italic]  Thinking[/muted italic]",
            spinner="dots",
            spinner_style="accent",
        ):
            response = _call_llm_only(llm_fn, messages)

        # Record the response before checking for exit, 
        # so any tool-use results are captured in the history.
        messages.append({
            "role": "assistant",
            "content": response
        })

        should_exit, goodbye = check_exit(response)

        if should_exit:
            _run_memory_sync(llm_fn, messages, goodbye)
            break

        _print_response(agent, response)


        should_verify = verify_always or trigger_phrase in response

        if should_verify:
            if on_verify:
                on_verify(messages, llm_fn, console)
            else:
                console.print(
                    Padding(
                        Text.assemble(
                            Text(f"  {G['diamond']}  ", style="warn"),
                            Text("was this verdict correct?", style="bold text"),
                        ),
                        (0, 0, 0, 0),
                    )
                )
                is_correct = Prompt.ask(
                    f"  [muted]{G['arrow']}[/muted]",
                    choices=["y", "n", "skip"],
                    default="y",
                    show_choices=True,
                )

                if is_correct == "n":
                    ground_truth = Prompt.ask(
                        f"  [muted]{G['arrow']} ground truth[/muted]",
                        choices=["human", "ai"],
                    )
                    reason = Prompt.ask(
                        f"  [muted]{G['arrow']} why was i wrong[/muted]"
                    )

                    messages.append({
                        "role": "user",
                        "content": (
                            f"WRONG VERDICT. Truth: {ground_truth}. "
                            f"Reason: {reason}. Update memory."
                        ),
                    })

                    with console.status(
                        f"[muted]  applying correction[/muted]",
                        spinner="dots",
                        spinner_style="success",
                    ):
                        correction = _call_llm_only(llm_fn, messages)

                    should_exit_c, goodbye_c = check_exit(correction)
                    if should_exit_c:
                        _run_memory_sync(llm_fn, messages, goodbye_c)
                        break

                    messages.append({
                        "role": "assistant",
                        "content": correction
                        })
                    _print_correction(agent, correction)

                elif is_correct == "y":
                    messages.append({
                        "role": "user",
                        "content": "Verdict confirmed correct. Update validation_benchmarks with PASS.",
                    })

    # === exit chrome ===========================================
    _farewell_card(user)
