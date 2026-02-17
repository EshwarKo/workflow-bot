"""
KB Router — Two-Phase Retrieval
================================

Maps problems to relevant knowledge base entries using keyword-based
retrieval (no embeddings). Implements the spec's two-phase approach:

Phase 1: Identify relevant chapters from problem statement keywords.
Phase 2: Within identified chapters, score and rank KB entries.

This is pure Python — no LLM calls needed for routing.
"""

import re
from pathlib import Path
from typing import Any

from kb_writer import read_jsonl


# Mathematical keywords that signal specific topics
MATH_KEYWORDS: dict[str, list[str]] = {
    "compactness": ["compact", "compactness", "precompact", "relatively compact",
                     "sequentially compact", "heine-borel", "bolzano-weierstrass",
                     "arzela-ascoli", "totally bounded"],
    "completeness": ["complete", "completeness", "banach", "cauchy", "convergent",
                      "absolutely summable"],
    "continuity": ["continuous", "continuity", "uniformly continuous",
                    "lipschitz", "bounded operator", "operator norm"],
    "convergence": ["converge", "convergence", "limit", "pointwise",
                     "uniform convergence", "weak convergence", "strong convergence"],
    "duality": ["dual", "duality", "adjoint", "hahn-banach", "functional",
                 "hyperplane", "separation"],
    "baire": ["baire", "category", "meagre", "residual", "nowhere dense",
              "open mapping", "closed graph", "banach-steinhaus",
              "uniform boundedness"],
    "spectral": ["spectrum", "spectral", "eigenvalue", "resolvent",
                  "self-adjoint", "compact operator"],
    "topology": ["open", "closed", "dense", "closure", "interior",
                  "neighbourhood", "topology", "metric"],
    "linearity": ["linear", "subspace", "quotient", "dimension", "basis",
                   "span", "codimension"],
    "measure": ["measure", "measurable", "lebesgue", "integral", "integrable",
                 "dominated convergence", "monotone convergence", "fatou"],
    "norm": ["norm", "normed", "seminorm", "equivalent norms", "unit ball"],
}


def load_chapter_kb(kb_dir: Path, course_id: str, chapter_id: int) -> list[dict[str, Any]]:
    """Load all KB records for a specific chapter."""
    chapter_dir = kb_dir / course_id / f"chapter_{chapter_id}"
    if not chapter_dir.exists():
        return []

    records = []
    for jsonl_file in chapter_dir.glob("*.jsonl"):
        records.extend(read_jsonl(jsonl_file))
    return records


def load_full_kb(kb_dir: Path, course_id: str, chapter_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """Load KB records for multiple chapters, keyed by chapter_id."""
    kb: dict[int, list[dict[str, Any]]] = {}
    for ch_id in chapter_ids:
        records = load_chapter_kb(kb_dir, course_id, ch_id)
        if records:
            kb[ch_id] = records
    return kb


def _extract_keywords(text: str) -> set[str]:
    """Extract mathematical keywords from a text string."""
    text_lower = text.lower()
    # Remove LaTeX commands but keep their arguments
    text_clean = re.sub(r"\\[a-zA-Z]+", " ", text_lower)
    text_clean = re.sub(r"[{}$\\]", " ", text_clean)
    text_clean = re.sub(r"\s+", " ", text_clean)

    words = set(text_clean.split())

    # Also look for multi-word phrases
    found: set[str] = set()
    for category, terms in MATH_KEYWORDS.items():
        for term in terms:
            if term.lower() in text_lower:
                found.add(category)
                found.add(term.lower())

    return words | found


def _score_record(record: dict[str, Any], problem_keywords: set[str]) -> float:
    """Score a KB record's relevance to a problem based on keyword overlap."""
    record_text = " ".join([
        str(record.get("name", "")),
        str(record.get("statement_natural", "")),
        str(record.get("statement_latex", "")),
        str(record.get("conclusion", "")),
        " ".join(str(t) for t in record.get("triggers", [])),
        " ".join(str(h.get("content", "")) for h in record.get("hypotheses", [])),
    ])

    record_keywords = _extract_keywords(record_text)
    overlap = problem_keywords & record_keywords

    if not overlap:
        return 0.0

    # Base score from keyword overlap
    score = len(overlap) / max(len(problem_keywords), 1)

    # Boost for named results (they're usually more important)
    if record.get("name"):
        score *= 1.3

    # Boost for theorems/lemmas over examples/remarks
    type_boosts = {
        "theorem": 1.4,
        "lemma": 1.2,
        "proposition": 1.2,
        "definition": 1.1,
        "corollary": 1.1,
        "example": 0.8,
        "remark": 0.7,
    }
    score *= type_boosts.get(record.get("type", ""), 1.0)

    return min(score, 1.0)


def route_problem(
    problem: dict[str, Any],
    kb: dict[int, list[dict[str, Any]]],
    chapter_hints: list[int] | None = None,
    max_results: int = 15,
) -> list[dict[str, Any]]:
    """
    Route a single problem to relevant KB entries (two-phase retrieval).

    Phase 1: Identify relevant chapters.
    Phase 2: Score and rank entries within those chapters.

    Args:
        problem: Parsed problem dict with "statement" key.
        kb: Full KB dict keyed by chapter_id.
        chapter_hints: If provided, restrict to these chapters (from config).
        max_results: Maximum number of KB entries to return.

    Returns:
        List of relevant KB records, sorted by relevance score (highest first).
        Each record gets an added "relevance_score" field.
    """
    statement = problem.get("statement", "")
    problem_keywords = _extract_keywords(statement)

    # Phase 1: Identify relevant chapters
    if chapter_hints:
        relevant_chapters = chapter_hints
    else:
        # Score each chapter by aggregate keyword overlap
        chapter_scores: dict[int, float] = {}
        for ch_id, records in kb.items():
            ch_text = " ".join(
                str(r.get("statement_natural", "")) + " " + str(r.get("name", ""))
                for r in records
            )
            ch_keywords = _extract_keywords(ch_text)
            overlap = problem_keywords & ch_keywords
            chapter_scores[ch_id] = len(overlap) / max(len(problem_keywords), 1)

        # Take chapters with score > 0.1, or top 3 if fewer
        relevant_chapters = [
            ch_id for ch_id, score in sorted(
                chapter_scores.items(), key=lambda x: x[1], reverse=True
            )
            if score > 0.1
        ]
        if not relevant_chapters:
            relevant_chapters = sorted(chapter_scores, key=chapter_scores.get, reverse=True)[:3]

    # Phase 2: Score individual entries within relevant chapters
    scored_entries: list[tuple[float, dict[str, Any]]] = []

    for ch_id in relevant_chapters:
        if ch_id not in kb:
            continue
        for record in kb[ch_id]:
            score = _score_record(record, problem_keywords)
            if score > 0.0:
                enriched = {**record, "relevance_score": round(score, 3)}
                scored_entries.append((score, enriched))

    # Sort by score descending, take top K
    scored_entries.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored_entries[:max_results]]


def route_sheet(
    problems: list[dict[str, Any]],
    kb: dict[int, list[dict[str, Any]]],
    sheet_chapters: list[int] | None = None,
    max_results_per_problem: int = 15,
) -> dict[int, list[dict[str, Any]]]:
    """
    Route all problems in a sheet to relevant KB entries.

    Args:
        problems: List of parsed problem dicts.
        kb: Full KB dict keyed by chapter_id.
        sheet_chapters: Chapter hints from config (which chapters this sheet covers).
        max_results_per_problem: Max KB entries per problem.

    Returns:
        Dict mapping problem_id -> list of relevant KB records.
    """
    context_bundles: dict[int, list[dict[str, Any]]] = {}

    for problem in problems:
        pid = problem["id"]
        entries = route_problem(
            problem, kb,
            chapter_hints=sheet_chapters,
            max_results=max_results_per_problem,
        )
        context_bundles[pid] = entries

    return context_bundles


def format_context_bundle(entries: list[dict[str, Any]]) -> str:
    """
    Format a context bundle as a readable text block for injection into
    a solver prompt.

    Returns a structured text representation of the relevant KB entries.
    """
    if not entries:
        return "(No relevant KB entries found.)"

    lines = ["## Relevant Knowledge Base Entries\n"]

    for entry in entries:
        eid = entry.get("id", "?")
        etype = entry.get("type", "?")
        name = entry.get("name") or "(unnamed)"
        score = entry.get("relevance_score", 0)

        lines.append(f"### [{etype.upper()}] {name} ({eid})  [relevance: {score}]")

        # Statement
        stmt = entry.get("statement_natural") or entry.get("statement_latex", "")
        if stmt:
            lines.append(f"**Statement:** {stmt}")

        # Hypotheses
        hyps = entry.get("hypotheses", [])
        if hyps:
            lines.append("**Hypotheses:**")
            for h in hyps:
                lines.append(f"  - {h.get('content', '')}")

        # Conclusion
        conc = entry.get("conclusion")
        if conc:
            lines.append(f"**Conclusion:** {conc}")

        # Triggers
        triggers = entry.get("triggers", [])
        if triggers:
            lines.append(f"**When to use:** {'; '.join(triggers)}")

        # Proof strategy
        skel = entry.get("proof_skeleton")
        if skel and isinstance(skel, dict):
            strategy = skel.get("strategy", "")
            if strategy:
                lines.append(f"**Proof strategy:** {strategy}")

        lines.append("")

    return "\n".join(lines)
