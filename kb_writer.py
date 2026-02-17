"""
Knowledge Base Writer
=====================

Utilities for reading, writing, and validating JSONL knowledge base files.
"""

import json
from pathlib import Path
from typing import Any


def ensure_kb_dir(output_dir: Path, course_id: str, chapter_id: int) -> Path:
    """
    Create and return the KB directory for a chapter.

    Structure: {output_dir}/{course_id}/chapter_{chapter_id}/

    Args:
        output_dir: Base output directory.
        course_id: Course identifier.
        chapter_id: Chapter number.

    Returns:
        Path to the chapter's KB directory.
    """
    kb_dir = output_dir / course_id / f"chapter_{chapter_id}"
    kb_dir.mkdir(parents=True, exist_ok=True)
    return kb_dir


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> int:
    """
    Write records to a JSONL file (one JSON object per line).

    Args:
        path: Output file path.
        records: List of dictionaries to write.

    Returns:
        Number of records written.
    """
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(records)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """
    Read records from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of parsed dictionaries.
    """
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  Warning: Invalid JSON on line {line_num} of {path}: {e}")
    return records


def validate_jsonl_output(path: Path) -> list[dict[str, Any]]:
    """
    Read and validate a KB JSONL file, reporting any issues.

    Checks:
    - File exists and is valid JSONL.
    - Each record has required fields (id, type).
    - IDs are unique.
    - Confidence scores are in [0, 1].

    Args:
        path: Path to the JSONL file.

    Returns:
        List of valid records.
    """
    if not path.exists():
        print(f"  Warning: Output file not found: {path}")
        return []

    records = read_jsonl(path)

    if not records:
        print(f"  Warning: No records in {path}")
        return []

    # Validate each record
    seen_ids: set[str] = set()
    valid_records: list[dict[str, Any]] = []
    issues: list[str] = []

    required_fields = {"id", "type"}
    valid_types = {
        "definition",
        "theorem",
        "lemma",
        "proposition",
        "corollary",
        "example",
        "remark",
    }

    for i, record in enumerate(records):
        # Check required fields
        missing = required_fields - set(record.keys())
        if missing:
            issues.append(f"Record {i}: missing fields {missing}")
            continue

        # Check type
        if record["type"] not in valid_types:
            issues.append(
                f"Record {i} ({record['id']}): unknown type '{record['type']}'"
            )

        # Check unique ID
        rid = record["id"]
        if rid in seen_ids:
            issues.append(f"Record {i}: duplicate id '{rid}'")
        seen_ids.add(rid)

        # Check confidence range
        conf = record.get("confidence")
        if conf is not None:
            if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                issues.append(
                    f"Record {i} ({rid}): confidence {conf} not in [0, 1]"
                )

        valid_records.append(record)

    if issues:
        print(f"  Validation issues in {path.name}:")
        for issue in issues[:10]:  # cap at 10
            print(f"    - {issue}")
        if len(issues) > 10:
            print(f"    ... and {len(issues) - 10} more")

    return valid_records


def summarise_kb(kb_dir: Path) -> dict[str, Any]:
    """
    Summarise the contents of a chapter's KB directory.

    Args:
        kb_dir: Path to the chapter KB directory.

    Returns:
        Summary dict with counts by type, confidence stats, etc.
    """
    summary: dict[str, Any] = {"path": str(kb_dir), "files": [], "by_type": {}}
    total = 0
    confidences: list[float] = []

    for jsonl_file in sorted(kb_dir.glob("*.jsonl")):
        records = read_jsonl(jsonl_file)
        summary["files"].append(
            {"name": jsonl_file.name, "records": len(records)}
        )
        for r in records:
            rtype = r.get("type", "unknown")
            summary["by_type"][rtype] = summary["by_type"].get(rtype, 0) + 1
            total += 1
            conf = r.get("confidence")
            if isinstance(conf, (int, float)):
                confidences.append(float(conf))

    summary["total_records"] = total
    if confidences:
        summary["avg_confidence"] = round(sum(confidences) / len(confidences), 3)
        summary["min_confidence"] = round(min(confidences), 3)
        summary["low_confidence_count"] = sum(1 for c in confidences if c < 0.80)
    else:
        summary["avg_confidence"] = None
        summary["min_confidence"] = None
        summary["low_confidence_count"] = 0

    return summary
