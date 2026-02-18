"""
LaTeX Source Parser
===================

Splits LaTeX source files into per-chapter text based on course configuration.
Handles common LaTeX document structures used in Oxford-style lecture notes.
"""

import re
from pathlib import Path
from typing import Any


# Patterns for chapter/section boundaries in LaTeX
# The \*? handles starred variants like \section*{...}
CHAPTER_PATTERNS = [
    r"\\chapter\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}",
    r"\\section\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}",
    r"\\part\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}",
]

# Combined pattern that matches any chapter-like boundary
# Handles starred variants (\section*{...}) and optional short titles (\section[short]{long})
BOUNDARY_PATTERN = re.compile(
    r"\\(?:chapter|section|part)\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}",
    re.MULTILINE,
)


def _normalise_title(title: str) -> str:
    """Normalise a title for fuzzy matching."""
    # Remove LaTeX commands, extra whitespace, and normalise case
    cleaned = re.sub(r"\\[a-zA-Z]+\s*", "", title)
    cleaned = re.sub(r"[{}]", "", cleaned)
    # Strip leading section numbers like "0.", "1.", "2.1"
    cleaned = re.sub(r"^\s*[\d.]+\s*", "", cleaned)
    # Strip trailing periods
    cleaned = cleaned.rstrip(".")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def _title_matches(config_title: str, latex_title: str) -> bool:
    """Check if a config title matches a LaTeX section title (fuzzy)."""
    norm_config = _normalise_title(config_title)
    norm_latex = _normalise_title(latex_title)

    # Exact match after normalisation
    if norm_config == norm_latex:
        return True

    # One contains the other
    if norm_config in norm_latex or norm_latex in norm_config:
        return True

    # Word overlap: if >70% of config words appear in latex title
    config_words = set(norm_config.split())
    latex_words = set(norm_latex.split())
    if config_words and latex_words:
        overlap = len(config_words & latex_words)
        if overlap / len(config_words) > 0.7:
            return True

    return False


def split_into_chapters(
    source_path: Path, config: dict[str, Any]
) -> dict[int, str]:
    """
    Split a LaTeX source file into chapters based on course configuration.

    Strategy:
    1. Try to match chapter titles from config against LaTeX headings.
    2. If title matching fails, use sequential assignment of found headings.
    3. If no headings found, treat the entire file as a single chapter.

    Args:
        source_path: Path to the .tex file.
        config: Course configuration dict with 'chapters' list.

    Returns:
        Dict mapping chapter_id -> chapter text (preserving LaTeX).

    Raises:
        FileNotFoundError: If source file doesn't exist.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    source_text = source_path.read_text(encoding="utf-8")
    chapter_configs = sorted(config["chapters"], key=lambda c: c["id"])
    chapters: dict[int, str] = {}

    # Find all section/chapter boundaries
    boundaries = list(BOUNDARY_PATTERN.finditer(source_text))

    if not boundaries:
        # No LaTeX headings found — treat entire file as first chapter
        if chapter_configs:
            chapters[chapter_configs[0]["id"]] = source_text
        return chapters

    # Strategy 1: Match config titles to LaTeX headings
    matched_boundaries: list[tuple[int, re.Match[str]]] = []

    for ch_config in chapter_configs:
        config_title = ch_config["title"]
        for boundary in boundaries:
            latex_title = boundary.group(1)
            if _title_matches(config_title, latex_title):
                matched_boundaries.append((ch_config["id"], boundary))
                break

    # If we matched at least some chapters via titles, use those
    if matched_boundaries:
        # Sort by position in the source
        matched_boundaries.sort(key=lambda x: x[1].start())

        for i, (ch_id, boundary) in enumerate(matched_boundaries):
            start = boundary.start()
            if i + 1 < len(matched_boundaries):
                end = matched_boundaries[i + 1][1].start()
            else:
                end = len(source_text)
            chapters[ch_id] = source_text[start:end].strip()

        return chapters

    # Strategy 2: Sequential assignment — map boundaries to configs in order
    for i, ch_config in enumerate(chapter_configs):
        if i < len(boundaries):
            start = boundaries[i].start()
            end = (
                boundaries[i + 1].start()
                if i + 1 < len(boundaries)
                else len(source_text)
            )
            chapters[ch_config["id"]] = source_text[start:end].strip()

    return chapters


SUBSECTION_PATTERN = re.compile(
    r"\\subsection\*?\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}",
    re.MULTILINE,
)


def split_into_sections(
    chapter_text: str,
    chapter_id: int,
    char_threshold: int = 20_000,
) -> list[dict[str, Any]]:
    """
    Split a chapter into subsection-level chunks for parallel extraction.

    If the chapter is smaller than char_threshold, returns a single chunk
    containing the whole chapter. Otherwise splits on \\subsection boundaries.

    Args:
        chapter_text: Full LaTeX text of the chapter.
        chapter_id: The chapter number (used for labelling).
        char_threshold: Chapters smaller than this are returned as one chunk.

    Returns:
        List of dicts, each with:
        - "section_idx": 0-based index of this section within the chapter.
        - "title": Subsection title (or "Full Chapter" if unsplit).
        - "text": The LaTeX text for this section.
    """
    if len(chapter_text) <= char_threshold:
        return [
            {"section_idx": 0, "title": "Full Chapter", "text": chapter_text}
        ]

    boundaries = list(SUBSECTION_PATTERN.finditer(chapter_text))

    if not boundaries:
        # No subsections found — return whole chapter as one chunk
        return [
            {"section_idx": 0, "title": "Full Chapter", "text": chapter_text}
        ]

    sections: list[dict[str, Any]] = []

    # Content before the first subsection (chapter intro / preamble material)
    pre_text = chapter_text[: boundaries[0].start()].strip()
    if pre_text:
        sections.append(
            {"section_idx": 0, "title": "Chapter Introduction", "text": pre_text}
        )

    for i, boundary in enumerate(boundaries):
        start = boundary.start()
        end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(chapter_text)
        title = boundary.group(1).strip()
        sections.append(
            {
                "section_idx": len(sections),
                "title": title,
                "text": chapter_text[start:end].strip(),
            }
        )

    return sections


def extract_preamble(source_path: Path) -> str:
    """
    Extract the LaTeX preamble (everything before \\begin{document}).

    Useful for extracting custom command definitions and package imports
    that may define notation used throughout the document.

    Args:
        source_path: Path to the .tex file.

    Returns:
        Preamble text, or empty string if no \\begin{document} found.
    """
    source_text = source_path.read_text(encoding="utf-8")
    match = re.search(r"\\begin\{document\}", source_text)
    if match:
        return source_text[: match.start()].strip()
    return ""
