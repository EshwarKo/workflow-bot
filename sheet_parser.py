"""
Problem Sheet Parser
====================

Parses LaTeX problem sheets into individual problems.
Handles common Oxford-style formats: numbered problems, lettered sub-parts,
\\begin{enumerate} environments, and plain-text numbered lists.
"""

import re
from pathlib import Path
from typing import Any


def parse_sheet(source_path: Path) -> list[dict[str, Any]]:
    """
    Parse a LaTeX problem sheet into individual problems.

    Args:
        source_path: Path to the .tex problem sheet file.

    Returns:
        List of problem dicts, each with:
        - "id": Sequential problem number (1-based).
        - "statement": Full LaTeX text of the problem.
        - "parts": List of sub-parts if the problem has (a), (b), etc.
        - "raw_latex": The exact LaTeX source.
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Sheet not found: {source_path}")

    text = source_path.read_text(encoding="utf-8")

    # Strip preamble — everything before \begin{document} or the first problem
    doc_match = re.search(r"\\begin\{document\}", text)
    if doc_match:
        text = text[doc_match.end() :]
    # Strip \end{document}
    text = re.sub(r"\\end\{document\}", "", text)

    # Try multiple parsing strategies in order
    problems = _parse_by_problem_env(text)
    if not problems:
        problems = _parse_by_numbered_headings(text)
    if not problems:
        problems = _parse_by_enumerate(text)
    if not problems:
        # Last resort: treat the whole sheet as one problem
        cleaned = text.strip()
        if cleaned:
            problems = [{"id": 1, "statement": cleaned, "parts": [], "raw_latex": cleaned}]

    # Extract sub-parts for each problem
    for prob in problems:
        if not prob["parts"]:
            prob["parts"] = _extract_parts(prob["statement"])

    return problems


def _parse_by_problem_env(text: str) -> list[dict[str, Any]]:
    """Parse problems defined with \\begin{problem} or \\begin{question} environments."""
    pattern = r"\\begin\{(?:problem|question)\}(?:\[([^\]]*)\])?(.*?)\\end\{(?:problem|question)\}"
    matches = list(re.finditer(pattern, text, re.DOTALL))

    if not matches:
        return []

    problems = []
    for i, m in enumerate(matches, 1):
        label = m.group(1) or ""
        body = m.group(2).strip()
        problems.append({
            "id": i,
            "label": label,
            "statement": body,
            "parts": [],
            "raw_latex": m.group(0),
        })

    return problems


def _parse_by_numbered_headings(text: str) -> list[dict[str, Any]]:
    """
    Parse problems separated by numbered headings like:
    "1.", "Problem 1.", "Question 1:", "Q1.", etc.
    """
    # Match patterns like "1." or "Problem 1." or "Question 1:" at start of line
    pattern = r"(?:^|\n)\s*(?:Problem|Question|Q\.?|Ex\.?)?\s*(\d+)\s*[.:)\]]"
    matches = list(re.finditer(pattern, text, re.IGNORECASE))

    if len(matches) < 2:
        # Need at least 2 boundaries to split
        # Check if there's exactly one problem
        if matches:
            body = text[matches[0].end() :].strip()
            return [{
                "id": int(matches[0].group(1)),
                "statement": body,
                "parts": [],
                "raw_latex": body,
            }]
        return []

    problems = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            problems.append({
                "id": int(m.group(1)),
                "statement": body,
                "parts": [],
                "raw_latex": body,
            })

    return problems


def _parse_by_enumerate(text: str) -> list[dict[str, Any]]:
    """Parse problems from the outermost \\begin{enumerate} environment.

    Handles nested enumerate blocks correctly by tracking nesting depth.
    Only splits on \\item at the outermost level.
    """
    # Find the outermost enumerate by tracking nesting depth
    BEGIN = r"\begin{enumerate}"
    END = r"\end{enumerate}"
    outer_start = text.find(BEGIN)
    if outer_start == -1:
        return []

    body_start = outer_start + len(BEGIN)
    depth = 1
    i = body_start
    body_end = len(text)

    while i < len(text) and depth > 0:
        next_begin = text.find(BEGIN, i)
        next_end = text.find(END, i)

        if next_end == -1:
            break

        if next_begin != -1 and next_begin < next_end:
            depth += 1
            i = next_begin + len(BEGIN)
        else:
            depth -= 1
            if depth == 0:
                body_end = next_end
            i = next_end + len(END)

    enum_body = text[body_start:body_end]

    # Find \item positions at depth 0 (inside outermost but not nested)
    item_positions: list[int] = []
    depth = 0
    j = 0
    while j < len(enum_body):
        if enum_body[j:].startswith(BEGIN):
            depth += 1
            j += len(BEGIN)
        elif enum_body[j:].startswith(END):
            depth -= 1
            j += len(END)
        elif depth == 0 and enum_body[j:].startswith("\\item"):
            # Verify it's \item and not \itemize etc.
            after = enum_body[j + 5: j + 6]
            if not after or not after.isalpha():
                item_positions.append(j)
            j += 5
        else:
            j += 1

    if not item_positions:
        return []

    # Split on item positions
    problems = []
    for idx, pos in enumerate(item_positions):
        start = pos + 5  # skip \item
        # Skip optional [\label] right after \item (but not [(a)] sub-items)
        end = item_positions[idx + 1] if idx + 1 < len(item_positions) else len(enum_body)
        body = enum_body[start:end].strip()
        if body:
            problems.append({
                "id": idx + 1,
                "statement": body,
                "parts": [],
                "raw_latex": body,
            })

    return problems


def _extract_parts(statement: str) -> list[dict[str, str]]:
    """
    Extract sub-parts (a), (b), (c) or (i), (ii), (iii) from a problem.

    Returns:
        List of dicts with "label" and "statement" keys.
    """
    # Try lettered parts: (a), (b), (c) ...
    parts_pattern = r"\(([a-z])\)\s*"
    part_matches = list(re.finditer(parts_pattern, statement))

    if len(part_matches) >= 2:
        parts = []
        for i, m in enumerate(part_matches):
            start = m.end()
            end = (
                part_matches[i + 1].start()
                if i + 1 < len(part_matches)
                else len(statement)
            )
            parts.append({
                "label": m.group(1),
                "statement": statement[start:end].strip(),
            })
        return parts

    # Try roman numeral parts: (i), (ii), (iii) ...
    roman_pattern = r"\((i{1,3}v?|vi{0,3})\)\s*"
    roman_matches = list(re.finditer(roman_pattern, statement))

    if len(roman_matches) >= 2:
        parts = []
        for i, m in enumerate(roman_matches):
            start = m.end()
            end = (
                roman_matches[i + 1].start()
                if i + 1 < len(roman_matches)
                else len(statement)
            )
            parts.append({
                "label": m.group(1),
                "statement": statement[start:end].strip(),
            })
        return parts

    # Try nested enumerate
    nested = re.search(
        r"\\begin\{enumerate\}(.*?)\\end\{enumerate\}", statement, re.DOTALL
    )
    if nested:
        items = re.split(r"\\item\b", nested.group(1))
        items = [item.strip() for item in items if item.strip()]
        labels = "abcdefghijklmnopqrstuvwxyz"
        return [
            {"label": labels[i] if i < 26 else str(i + 1), "statement": item}
            for i, item in enumerate(items)
        ]

    return []


def format_problem_for_display(problem: dict[str, Any]) -> str:
    """Format a parsed problem for human-readable display."""
    lines = [f"Problem {problem['id']}:"]
    lines.append(problem["statement"][:200])
    if len(problem["statement"]) > 200:
        lines.append("...")
    if problem.get("parts"):
        lines.append(f"  ({len(problem['parts'])} sub-parts)")
    return "\n".join(lines)
