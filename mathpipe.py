#!/usr/bin/env python3
"""
MathPipe: Autonomous Mathematics Learning Pipeline
===================================================

Converts LaTeX lecture notes and problem sheets into structured,
confidence-graded study materials with genuine mathematical intuition.

Commands:
    kb      Build knowledge base from LaTeX source
    sheet   Process a problem sheet (route → solve → verify → output)
    export  Generate study materials (study notes, Anki cards, trick bank)

Usage:
    python mathpipe.py kb    --config config/course.yaml --source notes.tex
    python mathpipe.py sheet --config config/course.yaml --sheet sheet1.tex
    python mathpipe.py export --config config/course.yaml --format study
"""

import argparse
import asyncio
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent_session import MODELS, load_prompt, run_agent
from config_loader import load_course_config, CourseConfig
from latex_parser import split_into_chapters, split_into_sections, extract_preamble
from kb_writer import (
    ensure_kb_dir,
    ensure_solutions_dir,
    ensure_exports_dir,
    validate_jsonl_output,
    read_jsonl,
    write_jsonl,
    write_json,
)
from sheet_parser import parse_sheet, format_problem_for_display
from router import load_full_kb, route_sheet, format_context_bundle

load_dotenv()


# ── KB BUILD PIPELINE ──────────────────────────────────────────────


async def _run_section_extraction(
    section_text: str,
    section_title: str,
    section_idx: int,
    chapter_id: int,
    course_config: CourseConfig,
    work_dir: Path,
    model: str,
    preamble: str = "",
) -> list[dict[str, Any]]:
    """
    Run KB extraction on a single section chunk.

    Returns the list of extracted records (parsed from JSONL).
    """
    course_id = course_config["course_id"]
    system_prompt = load_prompt("kb_builder_prompt")

    # Each section gets its own source + output file to avoid collisions
    source_file = work_dir / f"section_{section_idx}_source.tex"
    output_file = work_dir / f"section_{section_idx}_kb.jsonl"
    source_file.write_text(section_text, encoding="utf-8")

    # Build notation context
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

    task_message = f"""Extract all mathematical objects from the section source file.

**Course:** {course_config["course_name"]} ({course_id})
**Chapter {chapter_id}, Section:** {section_title}
**Source file:** {source_file.name}
**Output file:** {output_file.name}
{notation_section}{preamble_note}
Instructions:
1. {"Read `preamble.tex` first, then read" if preamble else "Read"} `{source_file.name}`.
2. Identify ALL definitions, theorems, lemmas, propositions, corollaries, examples, and remarks.
3. For each, extract ALL structured fields including intuition, mechanism, triggers, and pitfalls.
4. Use the ID format: `{course_id}.ch{chapter_id}.<type_abbrev>.<number>`
5. Write the complete JSONL to `{output_file.name}` — one JSON object per line, NO wrapping array, NO markdown fences.
6. Report a summary: count of each type, any items with confidence < 0.80, and any difficulties.

Be thorough. Extract EVERY formal mathematical statement. Spend time writing GOOD intuition — this is the most valuable output."""

    print(f"    Section {section_idx}: {section_title} ({len(section_text):,} chars)")

    await run_agent(
        system_prompt=system_prompt,
        task_message=task_message,
        cwd=work_dir,
        model=model,
        max_turns=60,
    )

    if output_file.exists():
        return read_jsonl(output_file)
    return []


async def run_kb_extraction(
    chapter_text: str,
    chapter_config: dict[str, Any],
    course_config: CourseConfig,
    output_dir: Path,
    model: str,
    preamble: str = "",
) -> dict[str, Any]:
    """
    Run KB extraction for a single chapter.

    Large chapters are automatically split into subsection-level chunks
    and processed independently, then merged into one kb.jsonl.
    """
    course_id = course_config["course_id"]
    chapter_id = chapter_config["id"]
    chapter_title = chapter_config["title"]

    kb_dir = ensure_kb_dir(output_dir, course_id, chapter_id)

    if preamble:
        (kb_dir / "preamble.tex").write_text(preamble, encoding="utf-8")

    output_file = kb_dir / "kb.jsonl"

    # Split chapter into sections (returns 1 chunk if small enough)
    sections = split_into_sections(chapter_text, chapter_id)

    print(f"\n{'='*60}")
    print(f"  Chapter {chapter_id}: {chapter_title}")
    print(f"  Source: {len(chapter_text):,} characters")
    if len(sections) > 1:
        print(f"  Chunked into {len(sections)} sections for parallel extraction")
    print(f"  Output: {output_file}")
    print(f"{'='*60}\n")

    start_time = time.time()

    if len(sections) == 1:
        # Small chapter — single extraction (original behaviour)
        all_records = await _run_section_extraction(
            section_text=sections[0]["text"],
            section_title=sections[0]["title"],
            section_idx=0,
            chapter_id=chapter_id,
            course_config=course_config,
            work_dir=kb_dir,
            model=model,
            preamble=preamble,
        )
    else:
        # Large chapter — extract each section concurrently, then merge
        tasks = [
            _run_section_extraction(
                section_text=sec["text"],
                section_title=sec["title"],
                section_idx=sec["section_idx"],
                chapter_id=chapter_id,
                course_config=course_config,
                work_dir=kb_dir,
                model=model,
                preamble=preamble,
            )
            for sec in sections
        ]
        results = await asyncio.gather(*tasks)
        all_records = [rec for section_recs in results for rec in section_recs]

    duration = round(time.time() - start_time, 1)

    # Deduplicate by ID (in case sections overlap at boundaries)
    seen_ids: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for rec in all_records:
        rid = rec.get("id", "")
        if rid and rid in seen_ids:
            continue
        seen_ids.add(rid)
        deduped.append(rec)

    # Write merged output
    write_jsonl(output_file, deduped)

    # Validate merged output
    records = validate_jsonl_output(output_file)

    stats: dict[str, Any] = {
        "chapter_id": chapter_id,
        "title": chapter_title,
        "duration_seconds": duration,
        "sections_processed": len(sections),
    }

    if records:
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

    if len(sections) > 1:
        print(f"\n  Merged {len(deduped)} records from {len(sections)} sections")

    return stats


async def cmd_kb(args: argparse.Namespace) -> int:
    """Build knowledge base from LaTeX source."""
    config = load_course_config(args.config)
    course_id = config["course_id"]
    model = MODELS[args.model]

    preamble = extract_preamble(args.source)
    if preamble:
        print(f"Extracted LaTeX preamble ({len(preamble)} chars)")

    chapters = split_into_chapters(args.source, config)
    if not chapters:
        print("Error: No chapters found. Check config titles match LaTeX headings.")
        return 1

    if args.chapters:
        chapter_ids = [int(x.strip()) for x in args.chapters.split(",")]
        chapters = {k: v for k, v in chapters.items() if k in chapter_ids}
        if not chapters:
            print(f"Error: No matching chapters for IDs {chapter_ids}")
            return 1

    print(f"\nMathPipe KB Builder — {config['course_name']}")
    print(f"Model: {args.model} | Chapters: {sorted(chapters.keys())}")
    print(f"Output: {args.output_dir / course_id}\n")

    all_stats: list[dict[str, Any]] = []
    pipeline_start = time.time()
    chapter_configs = {ch["id"]: ch for ch in config["chapters"]}

    for chapter_id in sorted(chapters.keys()):
        stats = await run_kb_extraction(
            chapter_text=chapters[chapter_id],
            chapter_config=chapter_configs[chapter_id],
            course_config=config,
            output_dir=args.output_dir,
            model=model,
            preamble=preamble,
        )
        all_stats.append(stats)

    total_time = round(time.time() - pipeline_start, 1)
    total_records = sum(s.get("total_records", 0) for s in all_stats)

    print(f"\n{'='*60}")
    print(f"  KB BUILD COMPLETE — {total_records} records in {total_time}s")
    for s in all_stats:
        marker = "OK" if s.get("status") == "success" else s.get("status", "?").upper()
        print(f"  Ch {s['chapter_id']}: {s.get('total_records', 0)} records [{marker}]")
    print(f"{'='*60}\n")

    # Write log
    log_dir = args.output_dir / course_id / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    write_json(log_dir / f"kb_build_{int(time.time())}.json", {
        "course_id": course_id,
        "model": args.model,
        "total_time_seconds": total_time,
        "total_records": total_records,
        "chapters": all_stats,
    })

    return 0


# ── SHEET PROCESSING PIPELINE ──────────────────────────────────────


async def solve_problem(
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

    # Write problem and context for the agent
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

    print(f"\n  Problem {problem_num}: solving...")
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


async def verify_problem(
    problem_num: int,
    work_dir: Path,
    course_config: CourseConfig,
    model: str,
) -> dict[str, Any]:
    """Run the verifier agent on a solved problem."""
    system_prompt = load_prompt("verifier_prompt")
    output_file = work_dir / f"verification_{problem_num}.json"

    solution_file = work_dir / f"solution_{problem_num}.json"
    context_file = work_dir / f"context_{problem_num}.txt"

    if not solution_file.exists():
        return {"problem_id": problem_num, "status": "no_solution"}

    task_message = f"""Verify the solution in `solution_{problem_num}.json`.

**Context:** KB entries are in `context_{problem_num}.txt`.
**Output:** Write your verification report to `verification_{problem_num}.json`.

Read both files, then perform all verification layers as specified in your system prompt.
The output must be valid JSON. No markdown fences."""

    print(f"  Problem {problem_num}: verifying...")
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


async def cmd_sheet(args: argparse.Namespace) -> int:
    """Process a problem sheet: parse → route → solve → verify → output."""
    config = load_course_config(args.config)
    course_id = config["course_id"]
    model = MODELS[args.model]

    # Parse problem sheet
    print(f"\nParsing problem sheet: {args.sheet}")
    problems = parse_sheet(args.sheet)
    if not problems:
        print("Error: No problems found in sheet.")
        return 1
    print(f"Found {len(problems)} problems")
    for p in problems:
        print(f"  {format_problem_for_display(p)}")

    # Determine sheet ID from filename or flag
    sheet_id = args.sheet_id or _infer_sheet_id(args.sheet)
    print(f"Sheet ID: {sheet_id}")

    # Load KB
    all_chapter_ids = [ch["id"] for ch in config["chapters"]]
    kb = load_full_kb(args.kb_dir, course_id, all_chapter_ids)
    total_kb = sum(len(v) for v in kb.values())
    print(f"Loaded KB: {total_kb} entries across {len(kb)} chapters")

    if total_kb == 0:
        print("Error: KB is empty. Run `mathpipe.py kb` first to build it.")
        return 1

    # Determine relevant chapters for this sheet
    sheet_chapters = None
    if config.get("sheets"):
        for s in config["sheets"]:
            if s["id"] == sheet_id:
                sheet_chapters = s.get("chapters")
                break
    if sheet_chapters:
        print(f"Sheet covers chapters: {sheet_chapters}")

    # Route problems to KB entries
    print("\nRouting problems to KB entries...")
    context_bundles = route_sheet(problems, kb, sheet_chapters=sheet_chapters)
    for pid, entries in context_bundles.items():
        print(f"  Problem {pid}: {len(entries)} relevant KB entries")

    # Create work directory
    work_dir = ensure_solutions_dir(args.output_dir, course_id, sheet_id)
    print(f"Work directory: {work_dir}")

    # Solve each problem
    print(f"\n{'='*60}")
    print(f"  SOLVING — Sheet {sheet_id} ({len(problems)} problems)")
    print(f"  Model: {args.model}")
    print(f"{'='*60}")

    solve_stats: list[dict[str, Any]] = []
    for problem in problems:
        pid = problem["id"]
        stats = await solve_problem(
            problem=problem,
            context_entries=context_bundles.get(pid, []),
            course_config=config,
            work_dir=work_dir,
            model=model,
            problem_num=pid,
        )
        solve_stats.append(stats)

    # Verify each solved problem
    if not args.skip_verify:
        print(f"\n{'='*60}")
        print(f"  VERIFYING")
        print(f"{'='*60}")

        verify_stats: list[dict[str, Any]] = []
        for problem in problems:
            pid = problem["id"]
            stats = await verify_problem(
                problem_num=pid,
                work_dir=work_dir,
                course_config=config,
                model=model,
            )
            verify_stats.append(stats)
    else:
        verify_stats = []
        print("\n  Verification skipped (--skip-verify)")

    # Generate output based on mode
    print(f"\n{'='*60}")
    print(f"  GENERATING OUTPUT — mode: {args.mode}")
    print(f"{'='*60}")

    await _generate_sheet_output(
        problems=problems,
        work_dir=work_dir,
        course_config=config,
        model=model,
        mode=args.mode,
        sheet_id=sheet_id,
    )

    # Print summary
    print(f"\n{'='*60}")
    print(f"  SHEET PROCESSING COMPLETE")
    print(f"{'='*60}")
    for ss in solve_stats:
        v = next((v for v in verify_stats if v["problem_id"] == ss["problem_id"]), {})
        vstat = v.get("verification_status", "skipped")
        print(f"  Problem {ss['problem_id']}: solve={ss['status']}, verify={vstat}")
    print(f"  Output: {work_dir}")
    print(f"{'='*60}\n")

    return 0


async def _generate_sheet_output(
    problems: list[dict[str, Any]],
    work_dir: Path,
    course_config: CourseConfig,
    model: str,
    mode: str,
    sheet_id: int,
) -> None:
    """Generate the final output document for a processed sheet."""
    system_prompt = load_prompt("output_prompt")

    # Collect all solution and verification files
    solution_files = sorted(work_dir.glob("solution_*.json"))
    verification_files = sorted(work_dir.glob("verification_*.json"))

    output_ext = {"hints": "md", "study": "md", "anki": "csv", "tricks": "jsonl"}
    output_file = work_dir / f"output_{mode}.{output_ext.get(mode, 'md')}"

    task_message = f"""Generate {mode} mode output for problem sheet {sheet_id}.

**Course:** {course_config["course_name"]} ({course_config["course_id"]})
**Mode:** {mode}
**Solution files:** {', '.join(f.name for f in solution_files)}
**Verification files:** {', '.join(f.name for f in verification_files)}
**Output file:** {output_file.name}

Read all solution files (and verification files if present), then generate the output in {mode} mode as specified in your system prompt.
Write the result to `{output_file.name}`. No wrapping markdown fences — write the raw format."""

    await run_agent(
        system_prompt=system_prompt,
        task_message=task_message,
        cwd=work_dir,
        model=model,
        max_turns=40,
    )

    if output_file.exists():
        size = output_file.stat().st_size
        print(f"  Output written: {output_file} ({size:,} bytes)")
    else:
        print(f"  Warning: Output file not created: {output_file}")


def _infer_sheet_id(sheet_path: Path) -> int:
    """Try to infer sheet ID from filename like 'sheet1.tex' or 'Sheet_2.tex'."""
    import re
    match = re.search(r"(\d+)", sheet_path.stem)
    return int(match.group(1)) if match else 1


# ── EXPORT PIPELINE ────────────────────────────────────────────────


async def cmd_export(args: argparse.Namespace) -> int:
    """Generate study materials from the KB."""
    config = load_course_config(args.config)
    course_id = config["course_id"]
    model = MODELS[args.model]

    # Load KB
    all_chapter_ids = [ch["id"] for ch in config["chapters"]]
    if args.chapters:
        all_chapter_ids = [int(x.strip()) for x in args.chapters.split(",")]

    kb = load_full_kb(args.kb_dir, course_id, all_chapter_ids)
    total_kb = sum(len(v) for v in kb.values())
    print(f"\nLoaded KB: {total_kb} entries across {len(kb)} chapters")

    if total_kb == 0:
        print("Error: KB is empty. Run `mathpipe.py kb` first.")
        return 1

    export_dir = ensure_exports_dir(args.output_dir, course_id)
    system_prompt = load_prompt("output_prompt")

    output_ext = {"study": "md", "anki": "csv", "tricks": "jsonl"}
    output_file = export_dir / f"{args.format}.{output_ext.get(args.format, 'md')}"

    # Write all KB entries to a single file for the agent to read
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

    task_message = f"""Generate {args.format} mode output from the knowledge base.

**Course:** {config["course_name"]} ({course_id})
**Mode:** {args.format}
**KB file:** kb_all.jsonl ({total_kb} entries)
**Chapters:** {chapters_info}
**Output file:** {output_file.name}

Read `kb_all.jsonl` (one JSON object per line), then generate the {args.format} output as specified in your system prompt.
Write the result to `{output_file.name}`. No wrapping markdown fences."""

    print(f"\nGenerating {args.format} export...")
    print(f"Model: {args.model} | Output: {output_file}")

    await run_agent(
        system_prompt=system_prompt,
        task_message=task_message,
        cwd=export_dir,
        model=model,
        max_turns=50,
    )

    if output_file.exists():
        size = output_file.stat().st_size
        print(f"\nExport written: {output_file} ({size:,} bytes)")
    else:
        print(f"\nWarning: Export not created: {output_file}")

    return 0


# ── CLI ─────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="mathpipe",
        description="MathPipe — Autonomous Mathematics Learning Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  kb      Build knowledge base from LaTeX source
  sheet   Process a problem sheet (route, solve, verify, output)
  export  Generate study materials from the KB (study notes, Anki, tricks)

Examples:
  python mathpipe.py kb --config config/course.yaml --source notes.tex
  python mathpipe.py sheet --config config/course.yaml --sheet sheet1.tex
  python mathpipe.py export --config config/course.yaml --format anki
        """,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── kb ──
    kb_p = subparsers.add_parser("kb", help="Build knowledge base from LaTeX source")
    kb_p.add_argument("--config", type=Path, required=True, help="Course config YAML")
    kb_p.add_argument("--source", type=Path, required=True, help="LaTeX source file")
    kb_p.add_argument("--output-dir", type=Path, default=Path("./kb"), help="KB output dir")
    kb_p.add_argument("--chapters", type=str, default=None, help="Comma-separated chapter IDs")
    kb_p.add_argument("--model", choices=list(MODELS.keys()), default="sonnet")

    # ── sheet ──
    sheet_p = subparsers.add_parser("sheet", help="Process a problem sheet")
    sheet_p.add_argument("--config", type=Path, required=True, help="Course config YAML")
    sheet_p.add_argument("--sheet", type=Path, required=True, help="Problem sheet .tex file")
    sheet_p.add_argument("--kb-dir", type=Path, default=Path("./kb"), help="KB directory")
    sheet_p.add_argument("--output-dir", type=Path, default=Path("./solutions"), help="Solutions output dir")
    sheet_p.add_argument("--sheet-id", type=int, default=None, help="Sheet ID (inferred from filename if omitted)")
    sheet_p.add_argument("--model", choices=list(MODELS.keys()), default="sonnet")
    sheet_p.add_argument("--mode", choices=["hints", "study", "full"], default="hints",
                         help="Output mode: hints (progressive disclosure), study (full notes), full (everything)")
    sheet_p.add_argument("--skip-verify", action="store_true", help="Skip verification step")

    # ── export ──
    export_p = subparsers.add_parser("export", help="Generate study materials from KB")
    export_p.add_argument("--config", type=Path, required=True, help="Course config YAML")
    export_p.add_argument("--kb-dir", type=Path, default=Path("./kb"), help="KB directory")
    export_p.add_argument("--output-dir", type=Path, default=Path("./kb"), help="Export output dir")
    export_p.add_argument("--chapters", type=str, default=None, help="Comma-separated chapter IDs")
    export_p.add_argument("--format", choices=["study", "anki", "tricks"], required=True,
                          help="Export format")
    export_p.add_argument("--model", choices=list(MODELS.keys()), default="sonnet")

    return parser


def main() -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate common inputs
    if not args.config.exists():
        print(f"Error: Config not found: {args.config}")
        return 1

    if args.command == "kb" and not args.source.exists():
        print(f"Error: Source not found: {args.source}")
        return 1

    if args.command == "sheet" and not args.sheet.exists():
        print(f"Error: Sheet not found: {args.sheet}")
        return 1

    # Dispatch to command handler
    handlers = {
        "kb": cmd_kb,
        "sheet": cmd_sheet,
        "export": cmd_export,
    }

    try:
        return asyncio.run(handlers[args.command](args))
    except KeyboardInterrupt:
        print("\n\nInterrupted. Partial output may be available.")
        return 130
    except Exception as e:
        print(f"\nFatal error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
