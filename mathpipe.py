#!/usr/bin/env python3
"""
MathPipe: Autonomous Mathematics Learning Pipeline
===================================================

MVP — Knowledge Base Builder from LaTeX Source

Extracts structured mathematical knowledge (definitions, theorems, lemmas,
proof skeletons) from LaTeX lecture notes into JSONL knowledge base files.

Usage:
    python mathpipe.py --config config/example_functional_analysis.yaml --source sample_data/example_chapter.tex
    python mathpipe.py --config config/my_course.yaml --source notes.tex --chapters 1,2
    python mathpipe.py --config config/my_course.yaml --source notes.tex --model opus
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

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    ToolUseBlock,
    UserMessage,
    ToolResultBlock,
)

from config_loader import load_course_config, CourseConfig
from latex_parser import split_into_chapters, extract_preamble
from kb_writer import ensure_kb_dir, validate_jsonl_output

load_dotenv()


# Available models
MODELS: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-5-20250929",
    "opus": "claude-opus-4-5-20251101",
}

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_kb_builder_prompt() -> str:
    """Load the KB builder system prompt."""
    return (PROMPTS_DIR / "kb_builder_prompt.md").read_text()


async def run_kb_extraction(
    chapter_text: str,
    chapter_config: dict[str, Any],
    course_config: CourseConfig,
    output_dir: Path,
    model: str,
    preamble: str = "",
) -> dict[str, Any]:
    """
    Run KB extraction for a single chapter using Claude Agent SDK.

    Creates a dedicated agent session that reads the chapter source and
    writes structured JSONL output.

    Args:
        chapter_text: The LaTeX source text for this chapter.
        chapter_config: Config dict for this chapter (id, title, etc.).
        course_config: Full course configuration.
        output_dir: Base output directory for KB files.
        model: Full model ID string.
        preamble: LaTeX preamble (custom commands, notation).

    Returns:
        Stats dict with extraction results.
    """
    course_id = course_config["course_id"]
    chapter_id = chapter_config["id"]
    chapter_title = chapter_config["title"]

    # Create workspace
    kb_dir = ensure_kb_dir(output_dir, course_id, chapter_id)

    # Write chapter source for the agent to read
    source_file = kb_dir / "chapter_source.tex"
    source_file.write_text(chapter_text, encoding="utf-8")

    # Write preamble if available (for notation reference)
    if preamble:
        preamble_file = kb_dir / "preamble.tex"
        preamble_file.write_text(preamble, encoding="utf-8")

    # Output file path (agent will write here)
    output_file = kb_dir / "kb.jsonl"

    # Build system prompt
    system_prompt = load_kb_builder_prompt()

    # Build notation context
    notation_overrides = course_config.get("notation_overrides", {})
    notation_section = ""
    if notation_overrides:
        notation_section = "\n\nCourse-specific notation overrides:\n"
        for symbol, meaning in notation_overrides.items():
            notation_section += f"  - `{symbol}` means: {meaning}\n"

    preamble_section = ""
    if preamble:
        preamble_section = (
            "\n\nThe file `preamble.tex` contains the document preamble with "
            "custom LaTeX command definitions. Read it first to understand any "
            "custom notation used in the chapter.\n"
        )

    # Build the task message
    task_message = f"""Extract all mathematical objects from the chapter source file.

**Course:** {course_config["course_name"]} ({course_id})
**Chapter {chapter_id}:** {chapter_title}
**Source file:** chapter_source.tex
**Output file:** kb.jsonl
{notation_section}{preamble_section}
Instructions:
1. {"Read `preamble.tex` first for custom commands, then read" if preamble else "Read"} `chapter_source.tex`.
2. Identify ALL definitions, theorems, lemmas, propositions, corollaries, examples, and remarks.
3. For each, extract the structured fields as specified in your system prompt.
4. Use the ID format: `{course_id}.ch{chapter_id}.<type_abbrev>.<number>`
5. Write the complete JSONL to `kb.jsonl` — one JSON object per line, NO wrapping array, NO markdown fences.
6. After writing, report a summary: count of each type extracted, any items with confidence < 0.80, and any difficulties.

Be thorough. Extract EVERY formal mathematical statement in the chapter."""

    print(f"\n{'='*60}")
    print(f"  Chapter {chapter_id}: {chapter_title}")
    print(f"  Source: {len(chapter_text):,} characters")
    print(f"  Output: {output_file}")
    print(f"{'='*60}\n")

    # Create the agent
    client = ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=system_prompt,
            allowed_tools=["Read", "Write", "Glob", "Grep"],
            max_turns=50,
            cwd=str(kb_dir.resolve()),
        )
    )

    # Run the agent session
    result_text = ""
    ch_start = time.time()

    try:
        async with client:
            await client.query(task_message)

            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                            print(block.text, end="", flush=True)
                        elif isinstance(block, ToolUseBlock):
                            print(f"\n  [Tool: {block.name}]", flush=True)

                elif isinstance(msg, UserMessage):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            is_error = bool(block.is_error) if block.is_error else False
                            if is_error:
                                error_str = str(block.content)[:300]
                                print(f"  [Error] {error_str}", flush=True)
                            else:
                                print("  [Done]", flush=True)

    except Exception as e:
        print(f"\n  Agent error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return {
            "chapter_id": chapter_id,
            "title": chapter_title,
            "status": "error",
            "error": str(e),
            "total_records": 0,
            "duration_seconds": round(time.time() - ch_start, 1),
        }

    print()  # newline after streaming

    # Validate output
    stats: dict[str, Any] = {
        "chapter_id": chapter_id,
        "title": chapter_title,
        "duration_seconds": round(time.time() - ch_start, 1),
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
        else:
            stats["avg_confidence"] = None
            stats["low_confidence_count"] = 0

        stats["status"] = "success"
    else:
        stats["status"] = "no_output"
        stats["total_records"] = 0

    return stats


async def run_kb_pipeline(
    config: CourseConfig,
    chapters: dict[int, str],
    output_dir: Path,
    model_name: str,
    preamble: str = "",
) -> None:
    """
    Run the full KB extraction pipeline across all specified chapters.

    Args:
        config: Course configuration.
        chapters: Dict mapping chapter_id -> chapter LaTeX text.
        output_dir: Base output directory.
        model_name: Short model name (haiku/sonnet/opus).
        preamble: LaTeX preamble text.
    """
    model = MODELS[model_name]
    course_id = config["course_id"]

    print(f"\n{'='*60}")
    print(f"  MathPipe KB Builder")
    print(f"{'='*60}")
    print(f"  Course: {config['course_name']} ({course_id})")
    print(f"  Chapters: {sorted(chapters.keys())}")
    print(f"  Model: {model_name} ({model})")
    print(f"  Output: {output_dir / course_id}")
    print(f"{'='*60}")

    all_stats: list[dict[str, Any]] = []
    pipeline_start = time.time()

    for chapter_id in sorted(chapters.keys()):
        chapter_text = chapters[chapter_id]
        chapter_configs = {ch["id"]: ch for ch in config["chapters"]}
        chapter_config = chapter_configs[chapter_id]

        stats = await run_kb_extraction(
            chapter_text=chapter_text,
            chapter_config=chapter_config,
            course_config=config,
            output_dir=output_dir,
            model=model,
            preamble=preamble,
        )
        all_stats.append(stats)

    total_time = round(time.time() - pipeline_start, 1)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  Total time: {total_time}s")
    print(f"  Chapters processed: {len(all_stats)}")

    total_records = 0
    for s in all_stats:
        total_records += s.get("total_records", 0)
        marker = "OK" if s["status"] == "success" else s["status"].upper()
        print(f"\n  Chapter {s['chapter_id']}: {s['title']}")
        print(f"    Status: {marker}")
        print(f"    Records: {s.get('total_records', 0)}")
        if s.get("by_type"):
            for t, count in sorted(s["by_type"].items()):
                print(f"      {t}: {count}")
        if s.get("avg_confidence") is not None:
            print(f"    Avg confidence: {s['avg_confidence']}")
        if s.get("low_confidence_count", 0) > 0:
            print(f"    Low confidence (<0.80): {s['low_confidence_count']}")
        print(f"    Duration: {s.get('duration_seconds', '?')}s")

    print(f"\n  Total KB records: {total_records}")

    # Write pipeline log
    log_dir = output_dir / course_id / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"pipeline_run_{int(time.time())}.json"
    with open(log_file, "w") as f:
        json.dump(
            {
                "course_id": course_id,
                "course_name": config["course_name"],
                "model": model_name,
                "total_time_seconds": total_time,
                "total_records": total_records,
                "chapters": all_stats,
            },
            f,
            indent=2,
        )
    print(f"\n  Pipeline log: {log_file}")
    print(f"{'='*60}\n")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="MathPipe — Mathematics Knowledge Base Builder (MVP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all chapters from a LaTeX source
  python mathpipe.py --config config/example_functional_analysis.yaml \\
                     --source sample_data/example_chapter.tex

  # Process specific chapters only
  python mathpipe.py --config config/my_course.yaml --source notes.tex --chapters 1,2

  # Use Opus for higher quality extraction
  python mathpipe.py --config config/my_course.yaml --source notes.tex --model opus

  # Custom output directory
  python mathpipe.py --config config/my_course.yaml --source notes.tex --output-dir ./my_kb
        """,
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to course_config.yaml",
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to LaTeX source file (.tex)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./kb"),
        help="Output directory for KB files (default: ./kb)",
    )
    parser.add_argument(
        "--chapters",
        type=str,
        default=None,
        help="Comma-separated chapter IDs to process (default: all)",
    )
    parser.add_argument(
        "--model",
        choices=list(MODELS.keys()),
        default="sonnet",
        help="Model for extraction (default: sonnet)",
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Validate inputs
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}")
        return 1
    if not args.source.exists():
        print(f"Error: Source file not found: {args.source}")
        return 1

    # Load config
    try:
        config = load_course_config(args.config)
    except (ValueError, FileNotFoundError) as e:
        print(f"Error loading config: {e}")
        return 1

    # Extract preamble for notation reference
    preamble = extract_preamble(args.source)
    if preamble:
        print(f"Extracted LaTeX preamble ({len(preamble)} chars)")

    # Split source into chapters
    try:
        chapters = split_into_chapters(args.source, config)
    except Exception as e:
        print(f"Error parsing source: {e}")
        return 1

    if not chapters:
        print("Error: No chapters found in source file.")
        print("Check that your config chapter titles match the LaTeX headings.")
        print("The parser looks for \\chapter{...} or \\section{...} commands.")
        return 1

    # Filter chapters if specified
    if args.chapters:
        try:
            chapter_ids = [int(x.strip()) for x in args.chapters.split(",")]
        except ValueError:
            print("Error: --chapters must be comma-separated integers (e.g., 1,2,3)")
            return 1
        chapters = {k: v for k, v in chapters.items() if k in chapter_ids}
        if not chapters:
            available = sorted(
                ch["id"] for ch in config["chapters"]
            )
            print(f"Error: No matching chapters for IDs {chapter_ids}")
            print(f"Available chapter IDs: {available}")
            return 1

    # Print chapter summary
    print(f"\nFound {len(chapters)} chapter(s) to process:")
    for ch_id, ch_text in sorted(chapters.items()):
        print(f"  Chapter {ch_id}: {len(ch_text):,} characters")

    # Run pipeline
    try:
        asyncio.run(
            run_kb_pipeline(config, chapters, args.output_dir, args.model, preamble)
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted. Partial output may be in the output directory.")
        return 130
    except Exception as e:
        print(f"\nFatal error: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
