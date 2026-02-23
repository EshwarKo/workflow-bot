#!/usr/bin/env python3
"""
MathPipe: Autonomous Mathematics Learning Pipeline
===================================================

Converts LaTeX lecture notes and problem sheets into structured,
confidence-graded study materials with genuine mathematical intuition.

Human-in-the-loop workflow — run each step individually and inspect
intermediate outputs, or run the full pipeline end-to-end.

Course layout (under courses/<course>/):
    course.yaml          config file
    notes/               lecture notes (.tex)
    sheets/              problem sheets (.tex)
    kb/                  generated knowledge base
    solutions/           generated solutions
    exports/             exported study materials

Usage:
    python mathpipe.py parse    --config courses/func/course.yaml --sheet sheets/sheet1.tex
    python mathpipe.py route    --config courses/func/course.yaml --sheet-id 1
    python mathpipe.py solve    --config courses/func/course.yaml --sheet-id 1
    python mathpipe.py verify   --config courses/func/course.yaml --sheet-id 1
    python mathpipe.py generate --config courses/func/course.yaml --sheet-id 1 --mode hints
    python mathpipe.py status   --config courses/func/course.yaml --sheet-id 1
    python mathpipe.py sheet    --config courses/func/course.yaml --sheet sheets/sheet1.tex
    python mathpipe.py kb       --config courses/func/course.yaml --source notes/notes.tex
    python mathpipe.py export   --config courses/func/course.yaml --format study
"""

import asyncio
import json
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from agent_session import MODELS, load_prompt, run_agent
from config_loader import load_course_config, resolve_path, CourseConfig
from kb_writer import (
    ensure_kb_dir,
    ensure_solutions_dir,
    ensure_exports_dir,
    validate_jsonl_output,
    read_jsonl,
    write_json,
)
from latex_parser import split_into_chapters, extract_preamble
from pipeline_state import (
    STEPS,
    init_state,
    load_state,
    mark_step,
    save_state,
)
from router import load_full_kb, route_sheet, format_context_bundle
from sheet_parser import parse_sheet, format_problem_for_display

load_dotenv()

console = Console()

# ── Branding ──────────────────────────────────────────────────────

LOGO = r"""[bold cyan]
    __  ___      __  __    ____  _
   /  |/  /___ _/ /_/ /_  / __ \(_)___  ___
  / /|_/ / __ `/ __/ __ \/ /_/ / / __ \/ _ \
 / /  / / /_/ / /_/ / / / ____/ / /_/ /  __/
/_/  /_/\__,_/\__/_/ /_/_/   /_/ .___/\___/
                              /_/[/]"""

TAGLINE = "[dim]Mathematics Learning Pipeline — human-in-the-loop[/dim]"


def _banner() -> None:
    console.print(LOGO)
    console.print(f"  {TAGLINE}\n")


# ── Helpers ───────────────────────────────────────────────────────


def _infer_sheet_id(sheet_path: Path) -> int:
    """Infer sheet ID from filename like 'sheet1.tex' or 'Sheet_2.tex'."""
    match = re.search(r"(\d+)", sheet_path.stem)
    return int(match.group(1)) if match else 1


def _resolve_work_dir(base_dir: Path, sheet_id: int) -> Path:
    return ensure_solutions_dir(base_dir, sheet_id)


def _load_parsed_problems(work_dir: Path) -> list[dict[str, Any]]:
    """Load previously parsed problems from the work directory."""
    f = work_dir / "parsed_problems.json"
    if not f.exists():
        raise click.ClickException(
            f"No parsed problems found at {f}\n"
            "Run 'mathpipe parse' first."
        )
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


def _load_routing(work_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Load routing results."""
    f = work_dir / "routing.json"
    if not f.exists():
        raise click.ClickException(
            f"No routing data found at {f}\n"
            "Run 'mathpipe route' first."
        )
    with open(f, encoding="utf-8") as fh:
        return json.load(fh)


def _parse_problem_ids(problems_str: str | None) -> list[int] | None:
    """Parse comma-separated problem IDs like '1,3,5'."""
    if not problems_str:
        return None
    return [int(x.strip()) for x in problems_str.split(",")]


def _get_sheet_chapters(config: CourseConfig, sheet_id: int) -> list[int] | None:
    """Get chapter IDs for a specific sheet from config."""
    if config.get("sheets"):
        for s in config["sheets"]:
            if s["id"] == sheet_id:
                return s.get("chapters")
    return None


def _resolve_sheet_path(config: CourseConfig, sheet_arg: Path) -> Path:
    """Resolve a sheet path: if relative, resolve against config base_dir."""
    if sheet_arg.is_absolute():
        return sheet_arg
    resolved = resolve_path(config, str(sheet_arg))
    if resolved.exists():
        return resolved
    # Fall back to CWD-relative (backwards compat)
    if sheet_arg.exists():
        return sheet_arg.resolve()
    return resolved


def _run_async(coro):
    """Run an async coroutine from sync click commands."""
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/] Partial output may be available.")
        sys.exit(130)


# ── Pipeline core functions ───────────────────────────────────────


async def _run_kb_extraction(
    chapter_text: str,
    chapter_config: dict[str, Any],
    course_config: CourseConfig,
    model: str,
    preamble: str = "",
) -> dict[str, Any]:
    """Run KB extraction for a single chapter."""
    course_id = course_config["course_id"]
    base_dir = course_config["base_dir"]
    chapter_id = chapter_config["id"]
    chapter_title = chapter_config["title"]

    kb_dir = ensure_kb_dir(base_dir, chapter_id)

    source_file = kb_dir / "chapter_source.tex"
    source_file.write_text(chapter_text, encoding="utf-8")

    if preamble:
        (kb_dir / "preamble.tex").write_text(preamble, encoding="utf-8")

    output_file = kb_dir / "kb.jsonl"
    system_prompt = load_prompt("kb_builder_prompt")

    notation_overrides = course_config.get("notation_overrides", {})
    notation_section = ""
    if notation_overrides:
        notation_section = "\n\nCourse-specific notation overrides:\n"
        for symbol, meaning in notation_overrides.items():
            notation_section += f"  - `{symbol}` means: {meaning}\n"

    preamble_note = ""
    if preamble:
        preamble_note = (
            "\n\nThe file `preamble.tex` contains custom LaTeX command "
            "definitions. Read it first for notation context.\n"
        )

    task_message = f"""Extract all mathematical objects from the chapter source file.

**Course:** {course_config["course_name"]} ({course_id})
**Chapter {chapter_id}:** {chapter_title}
**Source file:** chapter_source.tex
**Output file:** kb.jsonl
{notation_section}{preamble_note}
Instructions:
1. {"Read `preamble.tex` first, then read" if preamble else "Read"} `chapter_source.tex`.
2. Identify ALL definitions, theorems, lemmas, propositions, corollaries, examples, and remarks.
3. For each, extract ALL structured fields including intuition, mechanism, triggers, and pitfalls.
4. Use the ID format: `{course_id}.ch{chapter_id}.<type_abbrev>.<number>`
5. Write the complete JSONL to `kb.jsonl` — one JSON object per line, NO wrapping array, NO markdown fences.
6. Report a summary: count of each type, any items with confidence < 0.80, and any difficulties.

Be thorough. Extract EVERY formal mathematical statement. Spend time writing GOOD intuition — this is the most valuable output."""

    console.print(Panel(
        f"[bold]Chapter {chapter_id}:[/] {chapter_title}\n"
        f"Source: {len(chapter_text):,} characters\n"
        f"Output: {output_file}",
        title="KB Extraction",
        border_style="blue",
    ))

    result = await run_agent(
        system_prompt=system_prompt,
        task_message=task_message,
        cwd=kb_dir,
        model=model,
        max_turns=60,
    )

    stats: dict[str, Any] = {
        "chapter_id": chapter_id,
        "title": chapter_title,
        "duration_seconds": result["duration_seconds"],
    }

    if output_file.exists():
        records = validate_jsonl_output(output_file)
        stats["total_records"] = len(records)
        stats["by_type"] = {}
        for r in records:
            rtype = r.get("type", "unknown")
            stats["by_type"][rtype] = stats["by_type"].get(rtype, 0) + 1

        confidences = [
            r.get("confidence", 1.0)
            for r in records
            if isinstance(r.get("confidence"), (int, float))
        ]
        if confidences:
            stats["avg_confidence"] = round(sum(confidences) / len(confidences), 3)
            stats["low_confidence_count"] = sum(1 for c in confidences if c < 0.80)

        stats["status"] = "success"
    else:
        stats["status"] = "no_output"
        stats["total_records"] = 0

    return stats


async def _solve_problem(
    problem: dict[str, Any],
    context_entries: list[dict[str, Any]],
    course_config: CourseConfig,
    work_dir: Path,
    model: str,
    problem_num: int,
) -> dict[str, Any]:
    """Run the solver agent on a single problem."""
    system_prompt = load_prompt("solver_prompt")
    course_id = course_config["course_id"]

    problem_file = work_dir / f"problem_{problem_num}.json"
    context_file = work_dir / f"context_{problem_num}.txt"
    output_file = work_dir / f"solution_{problem_num}.json"

    write_json(problem_file, problem)
    context_file.write_text(format_context_bundle(context_entries), encoding="utf-8")

    task_message = f"""Solve the mathematical problem in `problem_{problem_num}.json`.

**Course:** {course_config["course_name"]} ({course_id})
**Context:** Relevant KB entries are in `context_{problem_num}.txt`.
**Output:** Write your solution to `solution_{problem_num}.json`.

Read both files, then produce a complete solution following the schema in your system prompt.
The output must be valid JSON (single object, not JSONL). No markdown fences in the file."""

    console.print(f"  [cyan]Problem {problem_num}:[/] solving...")
    result = await run_agent(
        system_prompt=system_prompt,
        task_message=task_message,
        cwd=work_dir,
        model=model,
        max_turns=40,
    )

    stats = {
        "problem_id": problem_num,
        "duration_seconds": result["duration_seconds"],
        "status": result["status"],
    }

    if output_file.exists():
        try:
            from kb_writer import read_json
            solution = read_json(output_file)
            stats["strategies"] = len(solution.get("strategies", []))
            stats["confidence"] = solution.get("classification", {}).get("confidence", None)
            stats["status"] = "success"
        except Exception:
            stats["status"] = "invalid_output"
    else:
        stats["status"] = "no_output"

    return stats


async def _verify_problem(
    problem_num: int,
    work_dir: Path,
    course_config: CourseConfig,
    model: str,
) -> dict[str, Any]:
    """Run the verifier agent on a solved problem."""
    system_prompt = load_prompt("verifier_prompt")
    output_file = work_dir / f"verification_{problem_num}.json"

    solution_file = work_dir / f"solution_{problem_num}.json"

    if not solution_file.exists():
        return {"problem_id": problem_num, "status": "no_solution"}

    task_message = f"""Verify the solution in `solution_{problem_num}.json`.

**Context:** KB entries are in `context_{problem_num}.txt`.
**Output:** Write your verification report to `verification_{problem_num}.json`.

Read both files, then perform all verification layers as specified in your system prompt.
The output must be valid JSON. No markdown fences."""

    console.print(f"  [cyan]Problem {problem_num}:[/] verifying...")
    result = await run_agent(
        system_prompt=system_prompt,
        task_message=task_message,
        cwd=work_dir,
        model=model,
        max_turns=30,
    )

    stats = {
        "problem_id": problem_num,
        "duration_seconds": result["duration_seconds"],
        "status": result["status"],
    }

    if output_file.exists():
        try:
            from kb_writer import read_json
            verification = read_json(output_file)
            overall = verification.get("overall", {})
            stats["confidence"] = overall.get("confidence")
            stats["verification_status"] = overall.get("status", "unknown")
            stats["human_review_required"] = overall.get("human_review_required", True)
            stats["status"] = "success"
        except Exception:
            stats["status"] = "invalid_output"

    return stats


async def _generate_output(
    work_dir: Path,
    course_config: CourseConfig,
    model: str,
    mode: str,
    sheet_id: int,
) -> Path | None:
    """Generate the final output document for a processed sheet."""
    if mode == "solution_guide":
        system_prompt = load_prompt("solution_guide_prompt")
    else:
        system_prompt = load_prompt("output_prompt")

    solution_files = sorted(work_dir.glob("solution_*.json"))
    verification_files = sorted(work_dir.glob("verification_*.json"))

    output_ext = {"hints": "md", "study": "md", "anki": "csv", "tricks": "jsonl", "solution_guide": "md"}
    output_file = work_dir / f"output_{mode}.{output_ext.get(mode, 'md')}"

    task_message = f"""Generate {mode} mode output for problem sheet {sheet_id}.

**Course:** {course_config["course_name"]} ({course_config["course_id"]})
**Mode:** {mode}
**Solution files:** {', '.join(f.name for f in solution_files)}
**Verification files:** {', '.join(f.name for f in verification_files)}
**Output file:** {output_file.name}

Read all solution files (and verification files if present), then generate the output in {mode} mode as specified in your system prompt.
Write the result to `{output_file.name}`. No wrapping markdown fences — write the raw format."""

    turns = 60 if mode == "solution_guide" else 40

    await run_agent(
        system_prompt=system_prompt,
        task_message=task_message,
        cwd=work_dir,
        model=model,
        max_turns=turns,
    )

    if output_file.exists():
        return output_file
    return None


# ── Click CLI ─────────────────────────────────────────────────────

MODEL_NAMES = list(MODELS.keys())


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """MathPipe — Autonomous Mathematics Learning Pipeline.

    Run without a command to launch interactive mode with arrow-key navigation.

    \b
    Course layout:
      courses/<name>/course.yaml     config
      courses/<name>/notes/           lecture notes
      courses/<name>/sheets/          problem sheets
      courses/<name>/kb/              generated KB
      courses/<name>/solutions/       generated solutions

    \b
    Interactive:              Step-by-step:           Full pipeline:
      mathpipe                  mathpipe parse          mathpipe sheet
      mathpipe interactive      mathpipe route          mathpipe kb
                                mathpipe solve          mathpipe export
                                mathpipe verify
                                mathpipe generate
                                mathpipe status
    """
    if ctx.invoked_subcommand is None:
        from interactive import run_interactive
        run_interactive()


# ── interactive ───────────────────────────────────────────────────


@cli.command()
def interactive():
    """Launch interactive mode with arrow-key navigation.

    Persistent shell that remembers your config and sheet between steps.
    """
    from interactive import run_interactive
    run_interactive()


# ── parse ─────────────────────────────────────────────────────────


@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--sheet", "sheet_path", type=click.Path(path_type=Path), required=True, help="Problem sheet .tex file (relative to course dir or absolute).")
@click.option("--sheet-id", type=int, default=None, help="Sheet ID (inferred from filename if omitted).")
def parse(config_path: Path, sheet_path: Path, sheet_id: int | None):
    """Parse a problem sheet into individual problems.

    Extracts problems from LaTeX source and writes parsed_problems.json.
    No LLM calls — pure parsing. Inspect the output before proceeding.
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    course_id = config["course_id"]
    sheet_path = _resolve_sheet_path(config, sheet_path)
    sid = sheet_id or _infer_sheet_id(sheet_path)

    console.print(Panel(
        f"[bold]Course:[/] {config['course_name']}\n"
        f"[bold]Sheet:[/]  {sheet_path.name} (ID {sid})",
        title="[bold]Parse[/]",
        border_style="cyan",
    ))

    problems = parse_sheet(sheet_path)
    if not problems:
        raise click.ClickException("No problems found in sheet.")

    # Display results table
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

    # Write output
    work_dir = _resolve_work_dir(base_dir, sid)
    out_file = work_dir / "parsed_problems.json"
    write_json(out_file, problems)

    # Update manifest
    init_state(
        work_dir, sid,
        sheet_file=str(sheet_path),
        config_file=str(config_path),
        course_id=course_id,
    )
    mark_step(work_dir, "parse", "done", problems_count=len(problems))

    console.print(f"\n[green]Done.[/] Wrote [bold]{out_file}[/] ({len(problems)} problems)")
    console.print("[dim]Inspect the file, then run:[/] [bold cyan]mathpipe route[/]")


# ── route ─────────────────────────────────────────────────────────


@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID.")
def route(config_path: Path, sheet_id: int):
    """Route parsed problems to relevant KB entries.

    Matches each problem to knowledge base entries using keyword analysis.
    No LLM calls — pure keyword scoring. Inspect routing.json before solving.
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    work_dir = _resolve_work_dir(base_dir, sheet_id)

    problems = _load_parsed_problems(work_dir)

    console.print(Panel(
        f"[bold]Course:[/] {config['course_name']}\n"
        f"[bold]Sheet:[/]  {sheet_id} ({len(problems)} problems)",
        title="[bold]Route[/]",
        border_style="cyan",
    ))

    # Load KB
    all_chapter_ids = [ch["id"] for ch in config["chapters"]]
    kb = load_full_kb(base_dir, all_chapter_ids)
    total_kb = sum(len(v) for v in kb.values())

    if total_kb == 0:
        raise click.ClickException(
            "KB is empty. Run 'mathpipe kb' first to build it."
        )

    console.print(f"  Loaded KB: [bold]{total_kb}[/] entries across {len(kb)} chapters")

    sheet_chapters = _get_sheet_chapters(config, sheet_id)
    if sheet_chapters:
        console.print(f"  Sheet covers chapters: {sheet_chapters}")

    # Route
    context_bundles = route_sheet(problems, kb, sheet_chapters=sheet_chapters)

    # Display results
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

    # Write outputs
    routing_file = work_dir / "routing.json"
    routing_data = {str(pid): entries for pid, entries in context_bundles.items()}
    write_json(routing_file, routing_data)

    for p in problems:
        pid = p["id"]
        entries = context_bundles.get(pid, [])
        ctx_file = work_dir / f"context_{pid}.txt"
        ctx_file.write_text(format_context_bundle(entries), encoding="utf-8")

    mark_step(work_dir, "route", "done", total_entries=total_entries)

    console.print(f"\n[green]Done.[/] Wrote [bold]{routing_file}[/] ({total_entries} total entries)")
    console.print("[dim]Inspect routing.json and context_N.txt, then run:[/] [bold cyan]mathpipe solve[/]")


# ── solve ─────────────────────────────────────────────────────────


@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID.")
@click.option("--model", type=click.Choice(MODEL_NAMES), default="sonnet", help="Model to use.")
@click.option("--problems", type=str, default=None, help="Comma-separated problem IDs to solve (default: all).")
def solve(config_path: Path, sheet_id: int, model: str, problems: str | None):
    """Solve problems using the LLM.

    Requires parse and route to have been run first.
    Use --problems to solve specific problems (e.g. --problems 1,3,5).
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    work_dir = _resolve_work_dir(base_dir, sheet_id)

    all_problems = _load_parsed_problems(work_dir)
    routing = _load_routing(work_dir)

    target_ids = _parse_problem_ids(problems)
    if target_ids:
        to_solve = [p for p in all_problems if p["id"] in target_ids]
    else:
        to_solve = all_problems

    console.print(Panel(
        f"[bold]Course:[/] {config['course_name']}\n"
        f"[bold]Sheet:[/]  {sheet_id}\n"
        f"[bold]Model:[/]  {model}\n"
        f"[bold]Problems:[/] {', '.join(str(p['id']) for p in to_solve)}",
        title="[bold]Solve[/]",
        border_style="yellow",
    ))

    model_id = MODELS[model]
    solve_stats: list[dict[str, Any]] = []

    async def _do_solve():
        for p in to_solve:
            pid = p["id"]
            context_entries = routing.get(str(pid), [])
            stats = await _solve_problem(
                problem=p,
                context_entries=context_entries,
                course_config=config,
                work_dir=work_dir,
                model=model_id,
                problem_num=pid,
            )
            solve_stats.append(stats)

    _run_async(_do_solve())

    # Display results
    table = Table(title="Solve Results", border_style="yellow")
    table.add_column("Problem", style="bold", width=8)
    table.add_column("Status", width=14)
    table.add_column("Strategies", width=10)
    table.add_column("Confidence", width=10)
    table.add_column("Time", width=8)

    for s in solve_stats:
        status_style = "green" if s["status"] == "success" else "red"
        table.add_row(
            str(s["problem_id"]),
            f"[{status_style}]{s['status']}[/]",
            str(s.get("strategies", "-")),
            f"{s.get('confidence', '-')}",
            f"{s.get('duration_seconds', '-')}s",
        )

    console.print(table)

    # Update manifest
    done_ids = [s["problem_id"] for s in solve_stats if s["status"] == "success"]
    all_ids = [p["id"] for p in all_problems]
    state = load_state(work_dir)
    prev_done = state.get("steps", {}).get("solve", {}).get("done", [])
    all_done = sorted(set(prev_done) | set(done_ids))
    pending = sorted(set(all_ids) - set(all_done))

    status = "done" if not pending else "partial"
    mark_step(work_dir, "solve", status, done=all_done, pending=pending)

    console.print(f"\n[green]Done.[/] Solutions written to [bold]{work_dir}[/]")
    console.print("[dim]Inspect solution_N.json files, then run:[/] [bold cyan]mathpipe verify[/]")


# ── verify ────────────────────────────────────────────────────────


@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID.")
@click.option("--model", type=click.Choice(MODEL_NAMES), default="sonnet", help="Model to use.")
@click.option("--problems", type=str, default=None, help="Comma-separated problem IDs to verify (default: all solved).")
def verify(config_path: Path, sheet_id: int, model: str, problems: str | None):
    """Verify solutions using adversarial LLM checking.

    Requires solve to have been run first. Each solution gets a
    4-layer verification: structural, adversarial, consistency, confidence.
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    work_dir = _resolve_work_dir(base_dir, sheet_id)

    all_problems = _load_parsed_problems(work_dir)

    # Find which problems have solutions
    solved_ids = []
    for p in all_problems:
        if (work_dir / f"solution_{p['id']}.json").exists():
            solved_ids.append(p["id"])

    if not solved_ids:
        raise click.ClickException("No solutions found. Run 'mathpipe solve' first.")

    target_ids = _parse_problem_ids(problems) or solved_ids
    target_ids = [pid for pid in target_ids if pid in solved_ids]

    console.print(Panel(
        f"[bold]Course:[/] {config['course_name']}\n"
        f"[bold]Sheet:[/]  {sheet_id}\n"
        f"[bold]Model:[/]  {model}\n"
        f"[bold]Verifying:[/] problems {', '.join(str(x) for x in target_ids)}",
        title="[bold]Verify[/]",
        border_style="magenta",
    ))

    model_id = MODELS[model]
    verify_stats: list[dict[str, Any]] = []

    async def _do_verify():
        for pid in target_ids:
            stats = await _verify_problem(
                problem_num=pid,
                work_dir=work_dir,
                course_config=config,
                model=model_id,
            )
            verify_stats.append(stats)

    _run_async(_do_verify())

    # Display results
    table = Table(title="Verification Results", border_style="magenta")
    table.add_column("Problem", style="bold", width=8)
    table.add_column("Status", width=14)
    table.add_column("Verdict", width=12)
    table.add_column("Confidence", width=10)
    table.add_column("Review?", width=8)

    for s in verify_stats:
        status_style = "green" if s["status"] == "success" else "red"
        verdict = s.get("verification_status", "-")
        verdict_style = {"verified": "green", "flagged": "yellow", "rejected": "red"}.get(verdict, "white")
        review = "yes" if s.get("human_review_required") else "no"
        table.add_row(
            str(s["problem_id"]),
            f"[{status_style}]{s['status']}[/]",
            f"[{verdict_style}]{verdict}[/]",
            f"{s.get('confidence', '-')}",
            review,
        )

    console.print(table)

    # Update manifest
    done_ids = [s["problem_id"] for s in verify_stats if s["status"] == "success"]
    state = load_state(work_dir)
    prev_done = state.get("steps", {}).get("verify", {}).get("done", [])
    all_done = sorted(set(prev_done) | set(done_ids))
    pending = sorted(set(solved_ids) - set(all_done))

    status = "done" if not pending else "partial"
    mark_step(work_dir, "verify", status, done=all_done, pending=pending)

    console.print(f"\n[green]Done.[/] Verifications written to [bold]{work_dir}[/]")
    console.print("[dim]Inspect verification_N.json files, then run:[/] [bold cyan]mathpipe generate[/]")


# ── generate ──────────────────────────────────────────────────────


@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID.")
@click.option("--model", type=click.Choice(MODEL_NAMES), default="sonnet", help="Model to use.")
@click.option("--mode", type=click.Choice(["hints", "study", "solution_guide", "anki", "tricks"]), default="hints", help="Output mode.")
def generate(config_path: Path, sheet_id: int, model: str, mode: str):
    """Generate final output from solutions.

    Transforms solved (and optionally verified) problems into the chosen
    output format: hints, study notes, solution guide, Anki cards, or tricks.
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    work_dir = _resolve_work_dir(base_dir, sheet_id)

    # Check that solutions exist
    solution_files = sorted(work_dir.glob("solution_*.json"))
    if not solution_files:
        raise click.ClickException("No solutions found. Run 'mathpipe solve' first.")

    verification_files = sorted(work_dir.glob("verification_*.json"))

    console.print(Panel(
        f"[bold]Course:[/] {config['course_name']}\n"
        f"[bold]Sheet:[/]  {sheet_id}\n"
        f"[bold]Mode:[/]   {mode}\n"
        f"[bold]Model:[/]  {model}\n"
        f"Solutions: {len(solution_files)} | Verifications: {len(verification_files)}",
        title="[bold]Generate[/]",
        border_style="green",
    ))

    model_id = MODELS[model]

    async def _do_generate():
        return await _generate_output(
            work_dir=work_dir,
            course_config=config,
            model=model_id,
            mode=mode,
            sheet_id=sheet_id,
        )

    output_file = _run_async(_do_generate())

    if output_file:
        size = output_file.stat().st_size
        mark_step(work_dir, "generate", "done", mode=mode, output_file=str(output_file), size_bytes=size)
        console.print(f"\n[green]Done.[/] Wrote [bold]{output_file}[/] ({size:,} bytes)")
    else:
        console.print("[red]Warning:[/] Output file was not created.")


# ── status ────────────────────────────────────────────────────────


@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--sheet-id", type=int, required=True, help="Sheet ID.")
def status(config_path: Path, sheet_id: int):
    """Show pipeline status for a problem sheet.

    Displays which steps have been completed, their timestamps,
    and key statistics.
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    work_dir = _resolve_work_dir(base_dir, sheet_id)

    state = load_state(work_dir)
    steps = state.get("steps", {})

    console.print(Panel(
        f"[bold]Course:[/]  {config['course_name']}\n"
        f"[bold]Sheet:[/]   {sheet_id}\n"
        f"[bold]WorkDir:[/] {work_dir}",
        title="[bold]Pipeline Status[/]",
        border_style="blue",
    ))

    # Status icons
    ICONS = {"done": "[green]\u2713[/]", "partial": "[yellow]\u25d0[/]", "pending": "[dim]\u25cb[/]", "error": "[red]\u2717[/]"}

    table = Table(border_style="blue", show_header=True)
    table.add_column("Step", style="bold", width=10)
    table.add_column("Status", width=10)
    table.add_column("Details", ratio=1)
    table.add_column("Timestamp", width=22)

    for step_name in STEPS:
        step = steps.get(step_name, {"status": "pending"})
        st = step.get("status", "pending")
        icon = ICONS.get(st, "[dim]?[/]")
        ts = step.get("timestamp", "")

        # Build details string
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
            details_parts.append(f"{step['size_bytes']:,} bytes")
        details = ", ".join(details_parts) or "-"

        table.add_row(step_name, f"{icon} {st}", details, ts)

    console.print(table)

    # Show files in work directory
    if work_dir.exists():
        files = sorted(work_dir.iterdir())
        if files:
            file_table = Table(title="Work Directory Files", border_style="dim")
            file_table.add_column("File", ratio=1)
            file_table.add_column("Size", width=12)
            for f in files:
                if f.is_file():
                    file_table.add_row(f.name, f"{f.stat().st_size:,} bytes")
            console.print(file_table)


# ── sheet (full pipeline) ────────────────────────────────────────


@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--sheet", "sheet_path", type=click.Path(path_type=Path), required=True, help="Problem sheet .tex file (relative to course dir or absolute).")
@click.option("--sheet-id", type=int, default=None, help="Sheet ID (inferred from filename if omitted).")
@click.option("--model", type=click.Choice(MODEL_NAMES), default="sonnet", help="Model to use.")
@click.option("--mode", type=click.Choice(["hints", "study", "solution_guide", "anki", "tricks"]), default="hints", help="Output mode.")
@click.option("--skip-verify", is_flag=True, help="Skip verification step.")
def sheet(config_path: Path, sheet_path: Path, sheet_id: int | None, model: str, mode: str, skip_verify: bool):
    """Run the full pipeline: parse -> route -> solve -> verify -> generate.

    Convenience command that runs all steps end-to-end without pausing
    for human inspection. Use the individual step commands for more control.
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    model_id = MODELS[model]
    sheet_path = _resolve_sheet_path(config, sheet_path)
    sid = sheet_id or _infer_sheet_id(sheet_path)

    console.print(Panel(
        f"[bold]Course:[/] {config['course_name']}\n"
        f"[bold]Sheet:[/]  {sheet_path.name} (ID {sid})\n"
        f"[bold]Model:[/]  {model}\n"
        f"[bold]Mode:[/]   {mode}",
        title="[bold]Full Pipeline[/]",
        border_style="blue",
    ))

    async def _do_full_pipeline():
        # Step 1: Parse
        console.rule("[cyan]Step 1/5 — Parse[/]")
        problems = parse_sheet(sheet_path)
        if not problems:
            raise click.ClickException("No problems found in sheet.")
        console.print(f"  Found [bold]{len(problems)}[/] problems")
        for p in problems:
            console.print(f"  {format_problem_for_display(p)}")

        work_dir = _resolve_work_dir(base_dir, sid)
        write_json(work_dir / "parsed_problems.json", problems)
        init_state(work_dir, sid, str(sheet_path), str(config_path), config["course_id"])
        mark_step(work_dir, "parse", "done", problems_count=len(problems))

        # Step 2: Route
        console.rule("[cyan]Step 2/5 — Route[/]")
        all_chapter_ids = [ch["id"] for ch in config["chapters"]]
        kb = load_full_kb(base_dir, all_chapter_ids)
        total_kb = sum(len(v) for v in kb.values())
        console.print(f"  Loaded KB: [bold]{total_kb}[/] entries")

        if total_kb == 0:
            raise click.ClickException("KB is empty. Run 'mathpipe kb' first.")

        sheet_chapters = _get_sheet_chapters(config, sid)
        context_bundles = route_sheet(problems, kb, sheet_chapters=sheet_chapters)

        routing_data = {str(pid): entries for pid, entries in context_bundles.items()}
        write_json(work_dir / "routing.json", routing_data)
        for p in problems:
            pid = p["id"]
            entries = context_bundles.get(pid, [])
            ctx_file = work_dir / f"context_{pid}.txt"
            ctx_file.write_text(format_context_bundle(entries), encoding="utf-8")
            console.print(f"  Problem {pid}: {len(entries)} KB entries")
        mark_step(work_dir, "route", "done", total_entries=sum(len(v) for v in context_bundles.values()))

        # Step 3: Solve
        console.rule("[yellow]Step 3/5 — Solve[/]")
        solve_stats = []
        for p in problems:
            pid = p["id"]
            stats = await _solve_problem(
                problem=p,
                context_entries=context_bundles.get(pid, []),
                course_config=config,
                work_dir=work_dir,
                model=model_id,
                problem_num=pid,
            )
            solve_stats.append(stats)
        done_ids = [s["problem_id"] for s in solve_stats if s["status"] == "success"]
        mark_step(work_dir, "solve", "done", done=done_ids, pending=[])

        # Step 4: Verify
        verify_stats = []
        if not skip_verify:
            console.rule("[magenta]Step 4/5 — Verify[/]")
            for p in problems:
                pid = p["id"]
                stats = await _verify_problem(
                    problem_num=pid,
                    work_dir=work_dir,
                    course_config=config,
                    model=model_id,
                )
                verify_stats.append(stats)
            vdone = [s["problem_id"] for s in verify_stats if s["status"] == "success"]
            mark_step(work_dir, "verify", "done", done=vdone, pending=[])
        else:
            console.print("\n  [dim]Verification skipped (--skip-verify)[/]")
            mark_step(work_dir, "verify", "done", skipped=True)

        # Step 5: Generate
        console.rule("[green]Step 5/5 — Generate[/]")
        output_file = await _generate_output(
            work_dir=work_dir,
            course_config=config,
            model=model_id,
            mode=mode,
            sheet_id=sid,
        )

        if output_file:
            size = output_file.stat().st_size
            mark_step(work_dir, "generate", "done", mode=mode, output_file=str(output_file), size_bytes=size)

        # Summary
        console.rule("[bold]Summary[/]")
        summary_table = Table(border_style="green")
        summary_table.add_column("Problem", style="bold", width=8)
        summary_table.add_column("Solve", width=14)
        summary_table.add_column("Verify", width=14)

        for ss in solve_stats:
            v = next((v for v in verify_stats if v["problem_id"] == ss["problem_id"]), {})
            vstat = v.get("verification_status", "skipped")
            s_style = "green" if ss["status"] == "success" else "red"
            v_style = {"verified": "green", "flagged": "yellow", "rejected": "red", "skipped": "dim"}.get(vstat, "white")
            summary_table.add_row(
                str(ss["problem_id"]),
                f"[{s_style}]{ss['status']}[/]",
                f"[{v_style}]{vstat}[/]",
            )

        console.print(summary_table)
        if output_file:
            console.print(f"\n[green]Output:[/] [bold]{output_file}[/]")
        console.print(f"[green]Work dir:[/] [bold]{work_dir}[/]")

    _run_async(_do_full_pipeline())


# ── kb ────────────────────────────────────────────────────────────


@cli.command()
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--source", "source_path", type=click.Path(path_type=Path), default=None, help="LaTeX source file (default: source_tex from config).")
@click.option("--chapters", type=str, default=None, help="Comma-separated chapter IDs.")
@click.option("--model", type=click.Choice(MODEL_NAMES), default="sonnet", help="Model to use.")
def kb(config_path: Path, source_path: Path | None, chapters: str | None, model: str):
    """Build knowledge base from LaTeX lecture notes.

    Extracts definitions, theorems, lemmas, and other mathematical objects
    from LaTeX source, building a structured JSONL knowledge base.

    If --source is omitted, uses source_tex from the config file.
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    course_id = config["course_id"]
    model_id = MODELS[model]

    # Resolve source path
    if source_path is None:
        if "source_tex" not in config:
            raise click.ClickException("No --source given and no source_tex in config.")
        source_path = resolve_path(config, config["source_tex"])
    else:
        source_path = _resolve_sheet_path(config, source_path)

    if not source_path.exists():
        raise click.ClickException(f"Source file not found: {source_path}")

    preamble = extract_preamble(source_path)
    if preamble:
        console.print(f"  Extracted LaTeX preamble ({len(preamble)} chars)")

    chapter_map = split_into_chapters(source_path, config)
    if not chapter_map:
        raise click.ClickException("No chapters found. Check config titles match LaTeX headings.")

    if chapters:
        chapter_ids = [int(x.strip()) for x in chapters.split(",")]
        chapter_map = {k: v for k, v in chapter_map.items() if k in chapter_ids}
        if not chapter_map:
            raise click.ClickException(f"No matching chapters for IDs {chapter_ids}")

    console.print(Panel(
        f"[bold]Course:[/]   {config['course_name']}\n"
        f"[bold]Model:[/]    {model}\n"
        f"[bold]Chapters:[/] {sorted(chapter_map.keys())}\n"
        f"[bold]Output:[/]   {base_dir / 'kb'}",
        title="[bold]KB Build[/]",
        border_style="blue",
    ))

    chapter_configs = {ch["id"]: ch for ch in config["chapters"]}

    async def _do_kb():
        all_stats = []
        pipeline_start = time.time()

        for chapter_id in sorted(chapter_map.keys()):
            stats = await _run_kb_extraction(
                chapter_text=chapter_map[chapter_id],
                chapter_config=chapter_configs[chapter_id],
                course_config=config,
                model=model_id,
                preamble=preamble,
            )
            all_stats.append(stats)

        total_time = round(time.time() - pipeline_start, 1)
        total_records = sum(s.get("total_records", 0) for s in all_stats)

        # Summary table
        table = Table(title=f"KB Build Complete \u2014 {total_records} records in {total_time}s", border_style="green")
        table.add_column("Chapter", style="bold", width=8)
        table.add_column("Title", ratio=1)
        table.add_column("Records", width=8)
        table.add_column("Status", width=10)

        for s in all_stats:
            st = s.get("status", "?")
            st_style = "green" if st == "success" else "red"
            table.add_row(
                str(s["chapter_id"]),
                s["title"],
                str(s.get("total_records", 0)),
                f"[{st_style}]{st}[/]",
            )

        console.print(table)

        # Write log
        log_dir = base_dir / "kb" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        write_json(log_dir / f"kb_build_{int(time.time())}.json", {
            "course_id": course_id,
            "model": model,
            "total_time_seconds": total_time,
            "total_records": total_records,
            "chapters": all_stats,
        })

    _run_async(_do_kb())


# ── export ────────────────────────────────────────────────────────


@cli.command("export")
@click.option("--config", "config_path", type=click.Path(exists=True, path_type=Path), required=True, help="Course config YAML.")
@click.option("--chapters", type=str, default=None, help="Comma-separated chapter IDs.")
@click.option("--format", "fmt", type=click.Choice(["study", "anki", "tricks"]), required=True, help="Export format.")
@click.option("--model", type=click.Choice(MODEL_NAMES), default="sonnet", help="Model to use.")
def export_cmd(config_path: Path, chapters: str | None, fmt: str, model: str):
    """Generate study materials from the knowledge base.

    Export the KB as study notes, Anki flashcards, or a trick bank.
    """
    _banner()
    config = load_course_config(config_path)
    base_dir = config["base_dir"]
    course_id = config["course_id"]
    model_id = MODELS[model]

    all_chapter_ids = [ch["id"] for ch in config["chapters"]]
    if chapters:
        all_chapter_ids = [int(x.strip()) for x in chapters.split(",")]

    kb = load_full_kb(base_dir, all_chapter_ids)
    total_kb = sum(len(v) for v in kb.values())

    if total_kb == 0:
        raise click.ClickException("KB is empty. Run 'mathpipe kb' first.")

    console.print(Panel(
        f"[bold]Course:[/]  {config['course_name']}\n"
        f"[bold]Format:[/]  {fmt}\n"
        f"[bold]KB:[/]      {total_kb} entries across {len(kb)} chapters\n"
        f"[bold]Model:[/]   {model}",
        title="[bold]Export[/]",
        border_style="green",
    ))

    export_dir = ensure_exports_dir(base_dir)
    system_prompt = load_prompt("output_prompt")

    output_ext = {"study": "md", "anki": "csv", "tricks": "jsonl"}
    output_file = export_dir / f"{fmt}.{output_ext.get(fmt, 'md')}"

    all_entries_file = export_dir / "kb_all.jsonl"
    with open(all_entries_file, "w", encoding="utf-8") as f:
        for ch_id in sorted(kb.keys()):
            for record in kb[ch_id]:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    chapters_info = ", ".join(
        f"Ch {ch['id']}: {ch['title']}"
        for ch in config["chapters"]
        if ch["id"] in all_chapter_ids
    )

    task_message = f"""Generate {fmt} mode output from the knowledge base.

**Course:** {config["course_name"]} ({course_id})
**Mode:** {fmt}
**KB file:** kb_all.jsonl ({total_kb} entries)
**Chapters:** {chapters_info}
**Output file:** {output_file.name}

Read `kb_all.jsonl` (one JSON object per line), then generate the {fmt} output as specified in your system prompt.
Write the result to `{output_file.name}`. No wrapping markdown fences."""

    async def _do_export():
        await run_agent(
            system_prompt=system_prompt,
            task_message=task_message,
            cwd=export_dir,
            model=model_id,
            max_turns=50,
        )

    _run_async(_do_export())

    if output_file.exists():
        size = output_file.stat().st_size
        console.print(f"\n[green]Done.[/] Wrote [bold]{output_file}[/] ({size:,} bytes)")
    else:
        console.print("[red]Warning:[/] Export file was not created.")


# ── Entry point ───────────────────────────────────────────────────


def main():
    try:
        cli(standalone_mode=False)
    except click.ClickException as e:
        console.print(f"[red]Error:[/] {e.format_message()}")
        sys.exit(1)
    except click.Abort:
        console.print("\n[yellow]Aborted.[/]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Fatal error:[/] {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
