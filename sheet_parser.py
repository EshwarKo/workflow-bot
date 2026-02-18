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

    # Try multiple parsing strategies and pick the best result.
    # Strategy 1: explicit \begin{problem}/\begin{question} environments (unambiguous)
    problems = _parse_by_problem_env(text)

    if not problems:
        # Strategy 2 & 3: try both and pick whichever finds more problems.
        # This avoids a false-positive from numbered headings (e.g. a stray "1."
        # matching inside content) blocking the enumerate parser entirely.
        by_heading = _parse_by_numbered_headings(text)
        by_enumerate = _parse_by_enumerate(text)

        if by_heading and by_enumerate:
            problems = by_heading if len(by_heading) >= len(by_enumerate) else by_enumerate
        else:
            problems = by_heading or by_enumerate

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
    """Parse problems from \\begin{enumerate} environments.

    Handles multiple separate enumerate blocks (common in Oxford sheets where
    sections like Starter/Main/Pudding each have their own enumerate).
    Respects \\setcounter{enumi}{N} for correct problem numbering.
    Handles nested enumerate blocks correctly by tracking nesting depth.
    Only splits on \\item at the outermost level.
    """
    BEGIN = r"\begin{enumerate}"
    END = r"\end{enumerate}"

    # Find ALL outermost enumerate blocks, tracking positions in original text
    blocks: list[dict[str, Any]] = []
    pos = 0
    while pos < len(text):
        outer_start = text.find(BEGIN, pos)
        if outer_start == -1:
            break

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

        outer_end = body_end + len(END) if body_end < len(text) else len(text)
        blocks.append({
            "body": text[body_start:body_end],
            "outer_start": outer_start,
            "outer_end": outer_end,
        })
        pos = outer_end

    if not blocks:
        return []

    # Extract items from all blocks
    problems = []
    global_item_count = 0

    for block in blocks:
        enum_body = block["body"]

        # Check for \setcounter{enumi}{N} inside the block to determine start number
        setcounter_match = re.search(r"\\setcounter\{enumi\}\{(\d+)\}", enum_body)
        start_num = int(setcounter_match.group(1)) if setcounter_match else None

        # Find \item positions at depth 0 (inside this block but not nested)
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
            continue

        # Determine numbering: \setcounter{enumi}{N} means next \item is N+1
        if start_num is not None:
            first_num = start_num + 1
        else:
            first_num = global_item_count + 1

        for idx, item_pos in enumerate(item_positions):
            start = item_pos + 5  # skip \item
            end = item_positions[idx + 1] if idx + 1 < len(item_positions) else len(enum_body)
            body = enum_body[start:end].strip()
            if body:
                prob_num = first_num + idx
                problems.append({
                    "id": prob_num,
                    "statement": body,
                    "parts": [],
                    "raw_latex": body,
                })
                global_item_count = prob_num

    # Attach inter-block content (e.g. displayed matrices between enumerate blocks)
    # to the last problem of the preceding block.  Oxford sheets commonly place
    # \[ ... \] display math outside the enumerate environment.
    if problems:
        _attach_interblock_content(text, blocks, problems)

    return problems


def _is_meaningful_content(content: str) -> bool:
    """Check if inter-block text contains mathematical or problem content."""
    # Strip structural LaTeX commands that aren't part of problem statements
    stripped = re.sub(
        r"\\(?:sub)*section\*?\{[^}]*\}", "", content
    )
    stripped = re.sub(
        r"\\(?:bigskip|medskip|smallskip|vspace\{[^}]*\}|newpage|clearpage|noindent)\b",
        "", stripped,
    )
    return bool(stripped.strip())


def _attach_interblock_content(
    text: str,
    blocks: list[dict[str, Any]],
    problems: list[dict[str, Any]],
) -> None:
    """Append content between enumerate blocks to the last problem of the preceding block."""
    for i in range(len(blocks) - 1):
        gap = text[blocks[i]["outer_end"]: blocks[i + 1]["outer_start"]]
        if _is_meaningful_content(gap):
            # Find the last problem whose id came from block i.
            # That problem's statement should be extended.
            # We identify it by the id range: block i produced problems with ids
            # starting after the previous block's last id.  The simplest approach
            # is to just extend the last problem that was added *before* block i+1
            # contributed any items, but since we appended sequentially, we can
            # use the block boundary: the last problem with id <= first id of
            # block i+1's items (if any) minus 1, or simply the last problem
            # that existed after processing block i.
            #
            # A robust approach: walk backwards from the end of problems to find
            # one whose id is <= the start_num of the next block.
            _append_to_last_problem_before_block(problems, blocks, i, gap.strip())

    # Also handle trailing content after the last enumerate block
    trailing = text[blocks[-1]["outer_end"]:]
    if _is_meaningful_content(trailing):
        problems[-1]["statement"] += "\n" + trailing.strip()
        problems[-1]["raw_latex"] += "\n" + trailing.strip()


def _append_to_last_problem_before_block(
    problems: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    block_idx: int,
    content: str,
) -> None:
    """Append inter-block content to the last problem that came from block_idx."""
    # The next block (block_idx+1) may have a setcounter that tells us its
    # first problem number.  Any problem with id < that number came from
    # an earlier block.
    next_body = blocks[block_idx + 1]["body"]
    sc = re.search(r"\\setcounter\{enumi\}\{(\d+)\}", next_body)
    if sc:
        next_first_id = int(sc.group(1)) + 1
        # Find last problem with id < next_first_id
        for p in reversed(problems):
            if p["id"] < next_first_id:
                p["statement"] += "\n" + content
                p["raw_latex"] += "\n" + content
                return

    # Fallback: attach to whatever problem was last before the gap.
    # Walk backwards to find a problem whose id is plausibly from block_idx.
    # Since problems are in order, the problem just before the first one from
    # block_idx+1 is the right target.  We can approximate by finding the
    # first problem whose id matches the next block's items and taking the one
    # before it.
    next_start = blocks[block_idx + 1]["outer_start"]
    # Count how many problems came from blocks 0..block_idx by checking
    # which problems exist before the next block's first item would appear.
    # Simplest: just append to the last problem we have so far that isn't
    # from a later block.  Since we process blocks in order and this function
    # is called after all blocks are processed, we need a different approach.
    #
    # Safe fallback: find the last problem added from any block up to block_idx.
    # Since problems are appended in block order, the first problem from
    # block_idx+1 is the one with the smallest id > all block_idx problems.
    # Without setcounter, blocks are numbered sequentially, so the boundary
    # is: count items in blocks 0..block_idx.
    items_before = 0
    for bi in range(block_idx + 1):
        body = blocks[bi]["body"]
        # Count \item occurrences at depth 0 (approximate)
        items_before += len(re.findall(r"\\item(?![a-zA-Z])", body))

    if items_before > 0 and items_before <= len(problems):
        target = problems[items_before - 1]
        target["statement"] += "\n" + content
        target["raw_latex"] += "\n" + content


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
