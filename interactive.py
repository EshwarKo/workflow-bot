"""
MathPipe Interactive Mode
=========================

Persistent interactive CLI with arrow-key navigation, session state,
and guided workflow. Stays in the MathPipe shell between steps so you
can inspect outputs and pick your next action.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from InquirerPy import inquirer
from InquirerPy.separator import Separator
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ── Vim-style keybindings (j/k alongside arrows + Ctrl-N/P) ──────

VIM_KB = {
    "down": [
        {"key": "down"},
        {"key": "c-n"},
        {"key": "j"},
    ],
    "up": [
        {"key": "up"},
        {"key": "c-p"},
        {"key": "k"},
    ],
}


# ── Session state ─────────────────────────────────────────────────


class Session:
    """Remembers config/paths between steps so you don't re-type them."""

    def __init__(self) -> None:
        self.config_path: Path | None = None
        self.config: dict[str, Any] | None = None
        self.course_id: str | None = None
        self.sheet_path: Path | None = None
        self.sheet_id: int | None = None
        self.output_dir: Path = Path("./solutions")
        self.kb_dir: Path = Path("./kb")
        self.model: str = "sonnet"

    @property
    def work_dir(self) -> Path | None:
        if self.course_id and self.sheet_id is not None:
            return self.output_dir / self.course_id / f"sheet_{self.sheet_id}"
        return None


# ── Helpers ───────────────────────────────────────────────────────


def _find_files(pattern: str, dirs: list[str] | None = None) -> list[str]:
    """Find files matching a glob pattern in common directories."""
    results: list[str] = []
    search_dirs = dirs or [".", "config", "sample_data", "data", "sheets", "notes"]
    for d in search_dirs:
        p = Path(d)
        if p.exists():
            results.extend(str(f) for f in p.glob(pattern))
    return sorted(set(results))


def _ask_config(session: Session) -> bool:
    """Prompt for config file if not set. Returns False if user cancels."""
    if session.config_path and session.config:
        reuse = inquirer.confirm(
            message=f"Use current config? ({session.config_path})",
            default=True,
        ).execute()
        if reuse:
            return True

    yaml_files = _find_files("*.yaml") + _find_files("*.yml")
    if yaml_files:
        choices = yaml_files + [Separator(), "Enter path manually..."]
        picked = inquirer.select(
            message="Select config file:",
            choices=choices,
            keybindings=VIM_KB,
        ).execute()
        if picked == "Enter path manually...":
            picked = inquirer.filepath(
                message="Config file path:",
                validate=lambda x: Path(x).exists(),
                only_files=True,
            ).execute()
    else:
        picked = inquirer.filepath(
            message="Config file path:",
            validate=lambda x: Path(x).exists(),
            only_files=True,
        ).execute()

    from config_loader import load_course_config
    try:
        session.config_path = Path(picked)
        session.config = load_course_config(session.config_path)
        session.course_id = session.config["course_id"]
        console.print(f"  [green]Loaded:[/] {session.config['course_name']} ({session.course_id})")
        return True
    except Exception as e:
        console.print(f"  [red]Error loading config:[/] {e}")
        session.config_path = None
        session.config = None
        return False


def _ask_sheet(session: Session) -> bool:
    """Prompt for sheet file if not set. Returns False if user cancels."""
    if session.sheet_path and session.sheet_id is not None:
        reuse = inquirer.confirm(
            message=f"Use current sheet? ({session.sheet_path.name}, ID {session.sheet_id})",
            default=True,
        ).execute()
        if reuse:
            return True

    tex_files = _find_files("*.tex")
    if tex_files:
        choices = tex_files + [Separator(), "Enter path manually..."]
        picked = inquirer.select(
            message="Select problem sheet:",
            choices=choices,
            keybindings=VIM_KB,
        ).execute()
        if picked == "Enter path manually...":
            picked = inquirer.filepath(
                message="Sheet file path:",
                validate=lambda x: Path(x).exists(),
                only_files=True,
            ).execute()
    else:
        picked = inquirer.filepath(
            message="Sheet file path:",
            validate=lambda x: Path(x).exists(),
            only_files=True,
        ).execute()

    session.sheet_path = Path(picked)

    import re
    match = re.search(r"(\d+)", session.sheet_path.stem)
    default_id = int(match.group(1)) if match else 1

    session.sheet_id = int(inquirer.number(
        message="Sheet ID:",
        default=default_id,
        min_allowed=1,
    ).execute())

    return True


def _ask_model(session: Session) -> str:
    """Prompt for model selection."""
    from agent_session import MODELS
    model = inquirer.select(
        message="Model:",
        choices=list(MODELS.keys()),
        default=session.model,
        keybindings=VIM_KB,
    ).execute()
    session.model = model
    return model


def _ask_problems(session: Session) -> list[int] | None:
    """Optionally pick specific problems to process."""
    work_dir = session.work_dir
    if not work_dir:
        return None

    problems_file = work_dir / "parsed_problems.json"
    if not problems_file.exists():
        return None

    with open(problems_file, encoding="utf-8") as f:
        problems = json.load(f)

    select_mode = inquirer.select(
        message="Which problems?",
        choices=["All problems", "Pick specific problems"],
        default="All problems",
        keybindings=VIM_KB,
    ).execute()

    if select_mode == "All problems":
        return None

    choices = []
    for p in problems:
        preview = p["statement"][:60].replace("\n", " ")
        parts = ", ".join(pt["label"] for pt in p.get("parts", [])) or ""
        suffix = f" ({parts})" if parts else ""
        choices.append({"name": f"Problem {p['id']}: {preview}...{suffix}", "value": p["id"]})

    selected = inquirer.checkbox(
        message="Select problems (space to toggle, enter to confirm):",
        choices=choices,
        keybindings=VIM_KB,
    ).execute()

    return selected if selected else None


def _show_status(session: Session) -> None:
    """Display pipeline status for current session."""
    from pipeline_state import load_state, STEPS

    work_dir = session.work_dir
    if not work_dir or not work_dir.exists():
        console.print("  [dim]No pipeline state yet. Run 'Parse' first.[/]")
        return

    state = load_state(work_dir)
    steps = state.get("steps", {})

    ICONS = {
        "done": "[green]\u2713[/]",
        "partial": "[yellow]\u25d0[/]",
        "pending": "[dim]\u25cb[/]",
        "error": "[red]\u2717[/]",
    }

    table = Table(border_style="blue", show_header=True, padding=(0, 1))
    table.add_column("Step", style="bold", width=10)
    table.add_column("Status", width=10)
    table.add_column("Details", ratio=1)

    for step_name in STEPS:
        step = steps.get(step_name, {"status": "pending"})
        st = step.get("status", "pending")
        icon = ICONS.get(st, "[dim]?[/]")

        details_parts = []
        if step.get("problems_count"):
            details_parts.append(f"{step['problems_count']} problems")
        if step.get("total_entries"):
            details_parts.append(f"{step['total_entries']} KB entries")
        if step.get("done"):
            details_parts.append(f"done: {step['done']}")
        if step.get("pending"):
            details_parts.append(f"pending: {step['pending']}")
        if step.get("mode"):
            details_parts.append(f"mode: {step['mode']}")
        if step.get("size_bytes"):
            details_parts.append(f"{step['size_bytes']:,}b")
        details = ", ".join(details_parts) or "-"

        table.add_row(step_name, f"{icon} {st}", details)

    console.print(table)


# ── Actions ───────────────────────────────────────────────────────


def _action_parse(session: Session) -> None:
    """Interactive parse."""
    if not _ask_config(session):
        return
    if not _ask_sheet(session):
        return

    from sheet_parser import parse_sheet
    from kb_writer import ensure_solutions_dir, write_json
    from pipeline_state import init_state, mark_step

    console.print(f"\n  Parsing [bold]{session.sheet_path.name}[/]...")
    problems = parse_sheet(session.sheet_path)

    if not problems:
        console.print("  [red]No problems found in sheet.[/]")
        return

    # Display table
    table = Table(title=f"Parsed Problems ({len(problems)})", border_style="cyan")
    table.add_column("#", style="bold", width=4)
    table.add_column("Preview", ratio=1)
    table.add_column("Parts", width=10)

    for p in problems:
        preview = p["statement"][:80].replace("\n", " ")
        if len(p["statement"]) > 80:
            preview += "..."
        parts_str = ", ".join(pt["label"] for pt in p.get("parts", [])) or "-"
        table.add_row(str(p["id"]), preview, parts_str)

    console.print(table)

    # Write
    work_dir = ensure_solutions_dir(session.output_dir, session.course_id, session.sheet_id)
    out_file = work_dir / "parsed_problems.json"
    write_json(out_file, problems)

    init_state(
        work_dir, session.sheet_id,
        sheet_file=str(session.sheet_path),
        config_file=str(session.config_path),
        course_id=session.course_id,
    )
    mark_step(work_dir, "parse", "done", problems_count=len(problems))
    console.print(f"\n  [green]\u2713[/] Wrote [bold]{out_file}[/]")


def _action_route(session: Session) -> None:
    """Interactive route."""
    if not _ask_config(session):
        return

    work_dir = session.work_dir
    if not work_dir or not (work_dir / "parsed_problems.json").exists():
        console.print("  [red]No parsed problems. Run 'Parse' first.[/]")
        return

    from router import load_full_kb, route_sheet, format_context_bundle
    from kb_writer import write_json
    from pipeline_state import mark_step

    with open(work_dir / "parsed_problems.json", encoding="utf-8") as f:
        problems = json.load(f)

    all_chapter_ids = [ch["id"] for ch in session.config["chapters"]]
    kb = load_full_kb(session.kb_dir, session.course_id, all_chapter_ids)
    total_kb = sum(len(v) for v in kb.values())

    if total_kb == 0:
        console.print("  [red]KB is empty.[/] Run 'Build KB' first.")
        return

    console.print(f"  Loaded KB: [bold]{total_kb}[/] entries across {len(kb)} chapters")

    # Get sheet chapters
    sheet_chapters = None
    if session.config.get("sheets"):
        for s in session.config["sheets"]:
            if s["id"] == session.sheet_id:
                sheet_chapters = s.get("chapters")
                break

    context_bundles = route_sheet(problems, kb, sheet_chapters=sheet_chapters)

    # Display
    table = Table(title="Routing Results", border_style="cyan")
    table.add_column("Problem", style="bold", width=8)
    table.add_column("KB Entries", width=10)
    table.add_column("Top Match", ratio=1)

    total_entries = 0
    for p in problems:
        pid = p["id"]
        entries = context_bundles.get(pid, [])
        total_entries += len(entries)
        top = entries[0].get("name", "?") if entries else "-"
        table.add_row(str(pid), str(len(entries)), top)

    console.print(table)

    # Write
    routing_data = {str(pid): entries for pid, entries in context_bundles.items()}
    write_json(work_dir / "routing.json", routing_data)

    for p in problems:
        pid = p["id"]
        entries = context_bundles.get(pid, [])
        ctx_file = work_dir / f"context_{pid}.txt"
        ctx_file.write_text(format_context_bundle(entries), encoding="utf-8")

    mark_step(work_dir, "route", "done", total_entries=total_entries)
    console.print(f"\n  [green]\u2713[/] Routing complete ({total_entries} total entries)")


def _action_solve(session: Session) -> None:
    """Interactive solve."""
    if not _ask_config(session):
        return

    work_dir = session.work_dir
    if not work_dir or not (work_dir / "routing.json").exists():
        console.print("  [red]No routing data. Run 'Route' first.[/]")
        return

    model = _ask_model(session)
    target_ids = _ask_problems(session)

    with open(work_dir / "parsed_problems.json", encoding="utf-8") as f:
        all_problems = json.load(f)
    with open(work_dir / "routing.json", encoding="utf-8") as f:
        routing = json.load(f)

    if target_ids:
        to_solve = [p for p in all_problems if p["id"] in target_ids]
    else:
        to_solve = all_problems

    console.print(f"\n  Solving [bold]{len(to_solve)}[/] problems with [bold]{model}[/]...")

    from agent_session import MODELS
    from mathpipe import _solve_problem
    from pipeline_state import load_state, mark_step

    model_id = MODELS[model]
    solve_stats: list[dict[str, Any]] = []

    async def _do():
        for p in to_solve:
            pid = p["id"]
            context_entries = routing.get(str(pid), [])
            stats = await _solve_problem(
                problem=p,
                context_entries=context_entries,
                course_config=session.config,
                work_dir=work_dir,
                model=model_id,
                problem_num=pid,
            )
            solve_stats.append(stats)

    asyncio.run(_do())

    # Display results
    table = Table(title="Solve Results", border_style="yellow")
    table.add_column("Problem", style="bold", width=8)
    table.add_column("Status", width=14)
    table.add_column("Strategies", width=10)
    table.add_column("Confidence", width=10)

    for s in solve_stats:
        st_style = "green" if s["status"] == "success" else "red"
        table.add_row(
            str(s["problem_id"]),
            f"[{st_style}]{s['status']}[/]",
            str(s.get("strategies", "-")),
            str(s.get("confidence", "-")),
        )

    console.print(table)

    done_ids = [s["problem_id"] for s in solve_stats if s["status"] == "success"]
    state = load_state(work_dir)
    prev_done = state.get("steps", {}).get("solve", {}).get("done", [])
    all_done = sorted(set(prev_done) | set(done_ids))
    all_ids = [p["id"] for p in all_problems]
    pending = sorted(set(all_ids) - set(all_done))

    status = "done" if not pending else "partial"
    mark_step(work_dir, "solve", status, done=all_done, pending=pending)
    console.print(f"\n  [green]\u2713[/] Solve complete")


def _action_verify(session: Session) -> None:
    """Interactive verify."""
    if not _ask_config(session):
        return

    work_dir = session.work_dir
    if not work_dir:
        console.print("  [red]No session. Run 'Parse' first.[/]")
        return

    # Check for solutions
    solution_files = sorted(work_dir.glob("solution_*.json"))
    if not solution_files:
        console.print("  [red]No solutions found. Run 'Solve' first.[/]")
        return

    model = _ask_model(session)
    target_ids = _ask_problems(session)

    with open(work_dir / "parsed_problems.json", encoding="utf-8") as f:
        all_problems = json.load(f)

    solved_ids = []
    for p in all_problems:
        if (work_dir / f"solution_{p['id']}.json").exists():
            solved_ids.append(p["id"])

    ids_to_verify = target_ids or solved_ids
    ids_to_verify = [pid for pid in ids_to_verify if pid in solved_ids]

    console.print(f"\n  Verifying problems [bold]{ids_to_verify}[/] with [bold]{model}[/]...")

    from agent_session import MODELS
    from mathpipe import _verify_problem
    from pipeline_state import load_state, mark_step

    model_id = MODELS[model]
    verify_stats: list[dict[str, Any]] = []

    async def _do():
        for pid in ids_to_verify:
            stats = await _verify_problem(
                problem_num=pid,
                work_dir=work_dir,
                course_config=session.config,
                model=model_id,
            )
            verify_stats.append(stats)

    asyncio.run(_do())

    # Display
    table = Table(title="Verification Results", border_style="magenta")
    table.add_column("Problem", style="bold", width=8)
    table.add_column("Verdict", width=12)
    table.add_column("Confidence", width=10)
    table.add_column("Review?", width=8)

    for s in verify_stats:
        verdict = s.get("verification_status", "-")
        v_style = {"verified": "green", "flagged": "yellow", "rejected": "red"}.get(verdict, "white")
        review = "yes" if s.get("human_review_required") else "no"
        table.add_row(
            str(s["problem_id"]),
            f"[{v_style}]{verdict}[/]",
            str(s.get("confidence", "-")),
            review,
        )

    console.print(table)

    done_ids = [s["problem_id"] for s in verify_stats if s["status"] == "success"]
    state = load_state(work_dir)
    prev_done = state.get("steps", {}).get("verify", {}).get("done", [])
    all_done = sorted(set(prev_done) | set(done_ids))
    pending = sorted(set(solved_ids) - set(all_done))

    status = "done" if not pending else "partial"
    mark_step(work_dir, "verify", status, done=all_done, pending=pending)
    console.print(f"\n  [green]\u2713[/] Verification complete")


def _action_generate(session: Session) -> None:
    """Interactive generate."""
    if not _ask_config(session):
        return

    work_dir = session.work_dir
    if not work_dir:
        console.print("  [red]No session. Run 'Parse' first.[/]")
        return

    solution_files = sorted(work_dir.glob("solution_*.json"))
    if not solution_files:
        console.print("  [red]No solutions found. Run 'Solve' first.[/]")
        return

    mode = inquirer.select(
        message="Output mode:",
        choices=[
            {"name": "hints          Progressive disclosure with spoiler tags", "value": "hints"},
            {"name": "study          Full study document with intuition", "value": "study"},
            {"name": "solution_guide Deep intuition solution guide", "value": "solution_guide"},
            {"name": "anki           Spaced repetition flashcards (CSV)", "value": "anki"},
            {"name": "tricks         Transferable technique bank (JSONL)", "value": "tricks"},
        ],
        default="solution_guide",
        keybindings=VIM_KB,
    ).execute()

    model = _ask_model(session)

    console.print(f"\n  Generating [bold]{mode}[/] output with [bold]{model}[/]...")

    from agent_session import MODELS
    from mathpipe import _generate_output
    from pipeline_state import mark_step

    model_id = MODELS[model]

    async def _do():
        return await _generate_output(
            work_dir=work_dir,
            course_config=session.config,
            model=model_id,
            mode=mode,
            sheet_id=session.sheet_id,
        )

    output_file = asyncio.run(_do())

    if output_file:
        size = output_file.stat().st_size
        mark_step(work_dir, "generate", "done", mode=mode, output_file=str(output_file), size_bytes=size)
        console.print(f"\n  [green]\u2713[/] Wrote [bold]{output_file}[/] ({size:,} bytes)")
    else:
        console.print("  [red]Output file was not created.[/]")


def _action_kb(session: Session) -> None:
    """Interactive KB build."""
    if not _ask_config(session):
        return

    # Pick source file
    tex_files = _find_files("*.tex")
    if tex_files:
        choices = tex_files + [Separator(), "Enter path manually..."]
        picked = inquirer.select(message="LaTeX source file:", choices=choices, keybindings=VIM_KB).execute()
        if picked == "Enter path manually...":
            picked = inquirer.filepath(
                message="Source path:", validate=lambda x: Path(x).exists(), only_files=True,
            ).execute()
    else:
        picked = inquirer.filepath(
            message="Source path:", validate=lambda x: Path(x).exists(), only_files=True,
        ).execute()

    source_path = Path(picked)
    model = _ask_model(session)

    from agent_session import MODELS
    from latex_parser import split_into_chapters, extract_preamble
    from mathpipe import _run_kb_extraction
    from kb_writer import write_json
    import time

    model_id = MODELS[model]
    preamble = extract_preamble(source_path)
    chapter_map = split_into_chapters(source_path, session.config)

    if not chapter_map:
        console.print("  [red]No chapters found. Check config titles match LaTeX headings.[/]")
        return

    # Let user pick chapters
    chapter_configs = {ch["id"]: ch for ch in session.config["chapters"]}
    ch_choices = [
        {"name": f"Chapter {cid}: {chapter_configs[cid]['title']}", "value": cid}
        for cid in sorted(chapter_map.keys())
    ]

    selected = inquirer.checkbox(
        message="Select chapters (space to toggle, enter for all):",
        choices=ch_choices,
        keybindings=VIM_KB,
    ).execute()

    if not selected:
        selected = sorted(chapter_map.keys())

    console.print(f"\n  Building KB for chapters {selected} with [bold]{model}[/]...")

    async def _do():
        all_stats = []
        for chapter_id in selected:
            stats = await _run_kb_extraction(
                chapter_text=chapter_map[chapter_id],
                chapter_config=chapter_configs[chapter_id],
                course_config=session.config,
                output_dir=session.kb_dir,
                model=model_id,
                preamble=preamble,
            )
            all_stats.append(stats)
        return all_stats

    all_stats = asyncio.run(_do())

    total_records = sum(s.get("total_records", 0) for s in all_stats)
    table = Table(title=f"KB Build \u2014 {total_records} records", border_style="green")
    table.add_column("Ch", style="bold", width=4)
    table.add_column("Title", ratio=1)
    table.add_column("Records", width=8)
    table.add_column("Status", width=10)

    for s in all_stats:
        st = s.get("status", "?")
        st_style = "green" if st == "success" else "red"
        table.add_row(str(s["chapter_id"]), s["title"], str(s.get("total_records", 0)), f"[{st_style}]{st}[/]")

    console.print(table)


def _action_settings(session: Session) -> None:
    """Adjust session settings."""
    setting = inquirer.select(
        message="Setting to change:",
        choices=[
            {"name": f"Model          (current: {session.model})", "value": "model"},
            {"name": f"Output dir     (current: {session.output_dir})", "value": "output_dir"},
            {"name": f"KB dir         (current: {session.kb_dir})", "value": "kb_dir"},
            {"name": f"Config         (current: {session.config_path or 'not set'})", "value": "config"},
            {"name": f"Sheet          (current: {session.sheet_path or 'not set'}, ID {session.sheet_id})", "value": "sheet"},
        ],
        keybindings=VIM_KB,
    ).execute()

    if setting == "model":
        _ask_model(session)
    elif setting == "output_dir":
        session.output_dir = Path(inquirer.text(
            message="Output directory:", default=str(session.output_dir),
        ).execute())
    elif setting == "kb_dir":
        session.kb_dir = Path(inquirer.text(
            message="KB directory:", default=str(session.kb_dir),
        ).execute())
    elif setting == "config":
        session.config_path = None
        _ask_config(session)
    elif setting == "sheet":
        session.sheet_path = None
        session.sheet_id = None
        _ask_sheet(session)


# ── Main loop ─────────────────────────────────────────────────────

LOGO = r"""[bold cyan]
    __  ___      __  __    ____  _
   /  |/  /___ _/ /_/ /_  / __ \(_)___  ___
  / /|_/ / __ `/ __/ __ \/ /_/ / / __ \/ _ \
 / /  / / /_/ / /_/ / / / ____/ / /_/ /  __/
/_/  /_/\__,_/\__/_/ /_/_/   /_/ .___/\___/
                              /_/[/]"""


def run_interactive() -> None:
    """Main interactive loop."""
    console.print(LOGO)
    console.print("  [dim]Mathematics Learning Pipeline \u2014 Interactive Mode[/]\n")

    session = Session()

    ACTIONS = {
        "parse": _action_parse,
        "route": _action_route,
        "solve": _action_solve,
        "verify": _action_verify,
        "generate": _action_generate,
        "status": lambda s: _show_status(s),
        "kb": _action_kb,
        "settings": _action_settings,
    }

    while True:
        # Build menu with status hints
        status_hint = ""
        if session.work_dir and session.work_dir.exists():
            from pipeline_state import load_state
            state = load_state(session.work_dir)
            steps = state.get("steps", {})
            done = [s for s in ("parse", "route", "solve", "verify", "generate") if steps.get(s, {}).get("status") == "done"]
            if done:
                status_hint = f"  [dim]({', '.join(done)} done)[/]"

        if status_hint:
            console.print(status_hint)

        choices = [
            Separator("\n  \u2500\u2500 Sheet Pipeline \u2500\u2500"),
            {"name": "  Parse         Extract problems from LaTeX sheet", "value": "parse"},
            {"name": "  Route         Match problems to KB entries", "value": "route"},
            {"name": "  Solve         Generate solutions (LLM)", "value": "solve"},
            {"name": "  Verify        Check solutions (LLM)", "value": "verify"},
            {"name": "  Generate      Create output (hints/study/guide)", "value": "generate"},
            Separator("\n  \u2500\u2500 Other \u2500\u2500"),
            {"name": "  Status        Show pipeline progress", "value": "status"},
            {"name": "  Build KB      Extract knowledge base from notes", "value": "kb"},
            {"name": "  Settings      Change model, paths, config", "value": "settings"},
            Separator(),
            {"name": "  Exit", "value": "exit"},
        ]

        try:
            action = inquirer.select(
                message="What would you like to do?",
                choices=choices,
                default="parse" if not session.config else None,
                pointer="\u25b8",
                show_cursor=False,
                keybindings=VIM_KB,
            ).execute()
        except (KeyboardInterrupt, EOFError):
            break

        if action == "exit":
            break

        console.print()

        try:
            ACTIONS[action](session)
        except KeyboardInterrupt:
            console.print("\n  [yellow]Interrupted.[/]")
        except Exception as e:
            console.print(f"\n  [red]Error:[/] {type(e).__name__}: {e}")

        console.print()

    console.print("\n  [dim]Goodbye.[/]\n")
