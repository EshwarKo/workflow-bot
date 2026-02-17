"""
Course Configuration Loader
============================

Loads and validates course_config.yaml files for MathPipe.
"""

import yaml
from pathlib import Path
from typing import Any, TypedDict


class ChapterConfig(TypedDict, total=False):
    """Configuration for a single chapter."""

    id: int
    title: str
    pages: list[int]  # [start, end] — optional if using LaTeX source
    prerequisites: list[int]


class SheetConfig(TypedDict, total=False):
    """Configuration for a problem sheet."""

    id: int
    filename: str
    chapters: list[int]


class CourseConfig(TypedDict, total=False):
    """Full course configuration."""

    course_id: str
    course_name: str
    term: str
    source_pdf: str
    source_tex: str
    chapters: list[ChapterConfig]
    sheets: list[SheetConfig]
    notation_overrides: dict[str, str]


def load_course_config(config_path: Path) -> CourseConfig:
    """
    Load and validate a course configuration YAML file.

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Validated CourseConfig dictionary.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If required fields are missing or invalid.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a YAML mapping, got {type(raw).__name__}")

    # Validate required top-level keys
    required = ["course_id", "course_name", "chapters"]
    for key in required:
        if key not in raw:
            raise ValueError(f"Missing required key '{key}' in config")

    # Validate course_id format
    course_id = raw["course_id"]
    if not isinstance(course_id, str) or not course_id.strip():
        raise ValueError("course_id must be a non-empty string")

    # Validate chapters
    chapters = raw["chapters"]
    if not isinstance(chapters, list) or len(chapters) == 0:
        raise ValueError("chapters must be a non-empty list")

    seen_ids: set[int] = set()
    for i, ch in enumerate(chapters):
        if not isinstance(ch, dict):
            raise ValueError(f"Chapter {i} must be a mapping")
        if "id" not in ch:
            raise ValueError(f"Chapter {i} missing 'id'")
        if "title" not in ch:
            raise ValueError(f"Chapter {i} missing 'title'")

        ch_id = ch["id"]
        if not isinstance(ch_id, int) or ch_id < 1:
            raise ValueError(f"Chapter id must be a positive integer, got {ch_id}")
        if ch_id in seen_ids:
            raise ValueError(f"Duplicate chapter id: {ch_id}")
        seen_ids.add(ch_id)

        # Validate pages if present
        if "pages" in ch:
            pages = ch["pages"]
            if not isinstance(pages, list) or len(pages) != 2:
                raise ValueError(f"Chapter {ch_id} pages must be [start, end]")
            if pages[0] > pages[1]:
                raise ValueError(
                    f"Chapter {ch_id} page start ({pages[0]}) > end ({pages[1]})"
                )

    # Validate sheets if present
    if "sheets" in raw:
        for i, sheet in enumerate(raw["sheets"]):
            if not isinstance(sheet, dict):
                raise ValueError(f"Sheet {i} must be a mapping")
            if "id" not in sheet:
                raise ValueError(f"Sheet {i} missing 'id'")

    # Validate notation_overrides if present
    if "notation_overrides" in raw:
        overrides = raw["notation_overrides"]
        if not isinstance(overrides, dict):
            raise ValueError("notation_overrides must be a mapping")

    return raw  # type: ignore[return-value]
