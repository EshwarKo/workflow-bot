#!/usr/bin/env python3
"""
Solution PDF Compiler
=====================

Reads solution_N.json, verification_N.json, and problem_N.json files from a
MathPipe solutions directory and compiles them into a properly formatted PDF.

Usage:
    python compile_pdf.py solutions/linalg_ii_ht2026/sheet_5356765
    python compile_pdf.py solutions/linalg_ii_ht2026/sheet_5356765 -o my_solutions.pdf
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import latex2mathml.converter
from jinja2 import Template
from weasyprint import HTML


# ── LaTeX → MathML conversion ────────────────────────────────────────


def _convert_latex_fragment(latex: str, display: bool = False) -> str:
    """Convert a single LaTeX math fragment to MathML."""
    try:
        mathml = latex2mathml.converter.convert(latex)
        if display:
            mathml = mathml.replace('display="inline"', 'display="block"')
        return mathml
    except Exception:
        # Fallback: render as styled code
        escaped = latex.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        tag = "div" if display else "span"
        return f'<{tag} class="math-fallback">{escaped}</{tag}>'


def latex_to_html(text: str) -> str:
    """Convert a string containing LaTeX math delimiters to HTML with MathML.

    Handles:
      - \\[ ... \\]  and  $$ ... $$   (display math)
      - \\( ... \\)  and  $ ... $     (inline math)
      - \\begin{...} ... \\end{...}   (environments used as display math)
      - LaTeX formatting: \\textbf, \\emph, \\\\, \\quad, etc.
    """
    if not text:
        return ""

    # Normalise line breaks inside the text
    result = text

    # Step 1: Display math  \[ ... \]
    def _replace_display_bracket(m: re.Match) -> str:
        return _convert_latex_fragment(m.group(1).strip(), display=True)

    result = re.sub(r"\\\[(.*?)\\\]", _replace_display_bracket, result, flags=re.DOTALL)

    # Step 2: Display math  $$ ... $$
    def _replace_display_dollar(m: re.Match) -> str:
        return _convert_latex_fragment(m.group(1).strip(), display=True)

    result = re.sub(r"\$\$(.*?)\$\$", _replace_display_dollar, result, flags=re.DOTALL)

    # Step 3: Standalone display-math environments not yet wrapped
    # e.g. \begin{vmatrix}...\end{vmatrix}, \begin{align*}...\end{align*}
    def _replace_env_display(m: re.Match) -> str:
        return _convert_latex_fragment(m.group(0).strip(), display=True)

    result = re.sub(
        r"\\begin\{(vmatrix|bmatrix|pmatrix|Vmatrix|Bmatrix|matrix|align\*?|"
        r"equation\*?|gather\*?|cases)\}.*?\\end\{\1\}",
        _replace_env_display,
        result,
        flags=re.DOTALL,
    )

    # Step 4: Inline math  \( ... \)
    def _replace_inline_paren(m: re.Match) -> str:
        return _convert_latex_fragment(m.group(1).strip(), display=False)

    result = re.sub(r"\\\((.*?)\\\)", _replace_inline_paren, result, flags=re.DOTALL)

    # Step 5: Inline math  $ ... $  (but not $$)
    def _replace_inline_dollar(m: re.Match) -> str:
        return _convert_latex_fragment(m.group(1).strip(), display=False)

    result = re.sub(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)", _replace_inline_dollar, result, flags=re.DOTALL)

    # Step 6: LaTeX formatting commands
    result = re.sub(r"\\textbf\{(.*?)\}", r"<strong>\1</strong>", result)
    result = re.sub(r"\\emph\{(.*?)\}", r"<em>\1</em>", result)
    result = re.sub(r"\\textit\{(.*?)\}", r"<em>\1</em>", result)
    result = re.sub(r"\\text\{(.*?)\}", r"\1", result)

    # Step 7: Markdown-style bold and italic (common in LLM-generated solutions)
    # Bold: **text**  (but not inside MathML tags)
    result = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", result)
    # Italic: *text*  (but not ** and not inside MathML)
    result = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", result)

    # Step 8: Markdown-style headers within solution text
    # ### Header → <h4>  (used inside solutions, we don't want full <h3>)
    result = re.sub(r"(?:^|\n)#{3,}\s+(.+?)(?:\n|$)", r"<h4>\1</h4>", result)

    # Line breaks
    result = result.replace("\\\\", "<br>")
    result = result.replace("\\newline", "<br>")

    # Spacing
    result = result.replace("\\quad", "&emsp;")
    result = result.replace("\\qquad", "&emsp;&emsp;")
    result = result.replace("\\,", "&thinsp;")

    # Markdown-style bullet lists:  lines starting with "- "
    def _replace_md_list(m: re.Match) -> str:
        items = re.findall(r"^- (.+)$", m.group(0), re.MULTILINE)
        li = "".join(f"<li>{item}</li>" for item in items)
        return f"<ul>{li}</ul>"

    result = re.sub(r"(?:^|\n)(- .+(?:\n- .+)*)", _replace_md_list, result)

    # Convert newlines to <br> for multi-line content (but not double-newlines
    # which become paragraph breaks)
    result = re.sub(r"\n{2,}", "</p><p>", result)
    result = result.replace("\n", " ")

    return result


# ── Data loading ─────────────────────────────────────────────────────


def load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file, returning None if it doesn't exist or is invalid."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def load_solutions_dir(work_dir: Path) -> list[dict[str, Any]]:
    """Load all problem/solution/verification triples from a solutions dir."""
    problems = []

    # Find all solution files and sort by problem number
    solution_files = sorted(work_dir.glob("solution_*.json"))
    if not solution_files:
        print(f"No solution files found in {work_dir}")
        return []

    for sf in solution_files:
        # Extract problem number from filename
        match = re.search(r"solution_(\d+)\.json", sf.name)
        if not match:
            continue
        num = int(match.group(1))

        solution = load_json(sf)
        if not solution:
            continue

        problem = load_json(work_dir / f"problem_{num}.json")
        verification = load_json(work_dir / f"verification_{num}.json")

        problems.append({
            "num": num,
            "problem": problem,
            "solution": solution,
            "verification": verification,
        })

    problems.sort(key=lambda p: p["num"])
    return problems


# ── Verification badge ───────────────────────────────────────────────


def verification_badge(verification: dict[str, Any] | None) -> dict[str, str]:
    """Return badge class and label for a verification status."""
    if not verification:
        return {"cls": "badge-skip", "label": "Not verified"}

    overall = verification.get("overall", {})
    status = overall.get("status", "unknown")
    confidence = overall.get("confidence", 0)

    if status == "verified":
        return {"cls": "badge-pass", "label": f"Verified ({confidence:.0%})"}
    elif status == "flagged":
        return {"cls": "badge-warn", "label": f"Flagged ({confidence:.0%})"}
    elif status == "rejected":
        return {"cls": "badge-fail", "label": f"Rejected ({confidence:.0%})"}
    else:
        return {"cls": "badge-skip", "label": status.title()}


# ── HTML template ────────────────────────────────────────────────────

HTML_TEMPLATE = Template(r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ title }}</title>
<style>
  @page {
    size: A4;
    margin: 2cm 2.2cm;
    @bottom-center {
      content: "Page " counter(page) " of " counter(pages);
      font-size: 9pt;
      color: #888;
    }
  }

  :root {
    --accent: #1a3a5c;
    --accent-light: #e8f0f8;
    --border: #c0c8d0;
    --text: #1a1a1a;
    --text-light: #555;
    --green: #1a7a3a;
    --green-bg: #e6f5ec;
    --amber: #8a6d00;
    --amber-bg: #fff8e1;
    --red: #a82020;
    --red-bg: #fde8e8;
    --grey-bg: #f5f5f5;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: "Latin Modern Roman", "Computer Modern", "Times New Roman", Georgia, serif;
    font-size: 11pt;
    line-height: 1.55;
    color: var(--text);
  }

  /* ── Title page ─────────────────────────── */
  .title-page {
    page-break-after: always;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 80vh;
    text-align: center;
  }
  .title-page h1 {
    font-size: 24pt;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 0.3em;
    letter-spacing: 0.02em;
  }
  .title-page .subtitle {
    font-size: 14pt;
    color: var(--text-light);
    margin-bottom: 2em;
  }
  .title-page .meta {
    font-size: 10pt;
    color: #888;
  }
  .title-page .rule {
    width: 60%;
    height: 2px;
    background: var(--accent);
    margin: 1.5em auto;
  }
  .title-page .summary-table {
    margin-top: 1.5em;
    border-collapse: collapse;
    font-size: 10pt;
  }
  .summary-table td, .summary-table th {
    padding: 0.35em 1em;
    text-align: left;
    border-bottom: 1px solid #ddd;
  }
  .summary-table th {
    font-weight: 600;
    color: var(--accent);
  }

  /* ── Problems ───────────────────────────── */
  .problem {
    page-break-before: always;
  }
  .problem:first-of-type {
    page-break-before: auto;
  }

  .problem-header {
    background: var(--accent);
    color: white;
    padding: 0.5em 0.8em;
    font-size: 14pt;
    font-weight: 700;
    margin-bottom: 0;
    border-radius: 4px 4px 0 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .badge {
    font-size: 8.5pt;
    font-weight: 600;
    padding: 0.2em 0.6em;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .badge-pass { background: var(--green-bg); color: var(--green); }
  .badge-warn { background: var(--amber-bg); color: var(--amber); }
  .badge-fail { background: var(--red-bg); color: var(--red); }
  .badge-skip { background: var(--grey-bg); color: #888; }

  .problem-statement {
    background: var(--accent-light);
    border: 1px solid var(--border);
    border-top: none;
    padding: 0.8em 1em;
    margin-bottom: 1.2em;
    border-radius: 0 0 4px 4px;
    font-style: italic;
  }

  /* ── Sections within a problem ──────────── */
  h3 {
    font-size: 12pt;
    font-weight: 700;
    color: var(--accent);
    border-bottom: 1.5px solid var(--accent);
    padding-bottom: 0.15em;
    margin: 1.2em 0 0.5em 0;
  }

  h4 {
    font-size: 11pt;
    font-weight: 600;
    color: var(--text);
    margin: 0.9em 0 0.3em 0;
  }

  p { margin: 0.4em 0; }

  /* ── Solution steps ─────────────────────── */
  .step {
    margin: 0.5em 0;
    padding: 0.5em 0.7em;
    border-left: 3px solid var(--accent);
    background: #fafcfe;
  }
  .step-num {
    font-weight: 700;
    color: var(--accent);
    margin-right: 0.3em;
  }
  .step .justification {
    font-size: 10pt;
    color: var(--text-light);
    margin-top: 0.15em;
  }
  .step .kb-refs {
    font-size: 9pt;
    color: #888;
    margin-top: 0.1em;
  }

  /* ── Hints tiers ────────────────────────── */
  .hint-tier {
    margin: 0.5em 0;
    padding: 0.5em 0.8em;
    border-radius: 4px;
  }
  .tier1 { background: #f0faf0; border-left: 3px solid var(--green); }
  .tier2 { background: var(--amber-bg); border-left: 3px solid var(--amber); }
  .tier3 { background: var(--accent-light); border-left: 3px solid var(--accent); }
  .hint-label {
    font-size: 9pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.2em;
  }
  .tier1 .hint-label { color: var(--green); }
  .tier2 .hint-label { color: var(--amber); }
  .tier3 .hint-label { color: var(--accent); }

  /* ── Postmortem ─────────────────────────── */
  .postmortem {
    background: var(--grey-bg);
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 0.8em 1em;
    margin-top: 1em;
  }
  .postmortem h3 { border-bottom-color: #999; color: #444; }

  .insight-box {
    background: white;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.6em 0.8em;
    margin: 0.4em 0;
  }
  .insight-box .label {
    font-size: 9pt;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--accent);
    margin-bottom: 0.15em;
  }

  /* ── Verification detail ────────────────── */
  .verification-detail {
    font-size: 10pt;
    margin-top: 0.8em;
    padding: 0.6em 0.8em;
    border: 1px solid #ddd;
    border-radius: 4px;
    background: white;
  }
  .verification-detail .check-row {
    display: flex;
    justify-content: space-between;
    padding: 0.2em 0;
    border-bottom: 1px solid #eee;
  }
  .check-row:last-child { border-bottom: none; }
  .check-pass { color: var(--green); }
  .check-warn { color: var(--amber); }
  .check-fail { color: var(--red); }

  /* ── Lists ──────────────────────────────── */
  ul, ol { margin: 0.3em 0 0.3em 1.5em; }
  li { margin: 0.15em 0; }

  /* ── Math ───────────────────────────────── */
  math { font-size: 1.05em; }
  math[display="block"] {
    display: block;
    text-align: center;
    margin: 0.6em 0;
  }
  .math-fallback {
    font-family: "Latin Modern Mono", "Courier New", monospace;
    font-size: 10pt;
    background: #f4f4f4;
    padding: 0.1em 0.3em;
    border-radius: 2px;
  }
  div.math-fallback {
    display: block;
    text-align: center;
    margin: 0.5em 0;
    padding: 0.5em;
  }

  /* ── Common errors list ─────────────────── */
  .error-list li {
    color: var(--red);
  }
  .error-list li span {
    color: var(--text);
  }
</style>
</head>
<body>

<!-- ═══ TITLE PAGE ═══ -->
<div class="title-page">
  <h1>{{ title }}</h1>
  <div class="rule"></div>
  <div class="subtitle">{{ subtitle }}</div>
  <table class="summary-table">
    <tr><th>Problems</th><td>{{ entries|length }}</td></tr>
    {% set ns = namespace(v=0, f=0, r=0) %}
    {% for e in entries %}
      {% if e.verification %}
        {% set status = e.verification.get("overall", {}).get("status", "") %}
        {% if status == "verified" %}{% set ns.v = ns.v + 1 %}
        {% elif status == "flagged" %}{% set ns.f = ns.f + 1 %}
        {% elif status == "rejected" %}{% set ns.r = ns.r + 1 %}{% endif %}
      {% endif %}
    {% endfor %}
    <tr><th>Verified</th><td>{{ ns.v }} passed, {{ ns.f }} flagged, {{ ns.r }} rejected</td></tr>
    <tr><th>Generated by</th><td>MathPipe</td></tr>
  </table>
  <div class="meta" style="margin-top:2em;">Compiled {{ generated_date }}</div>
</div>

<!-- ═══ PROBLEMS ═══ -->
{% for entry in entries %}
{% set sol = entry.solution %}
{% set ver = entry.verification %}
{% set prob = entry.problem %}
{% set badge = entry.badge %}
{% set rec_id = sol.get("recommended_strategy", "s1") %}
{% set strategies = sol.get("strategies", []) %}

<div class="problem">

  <!-- Header -->
  <div class="problem-header">
    <span>Problem {{ entry.num }}</span>
    <span class="badge {{ badge.cls }}">{{ badge.label }}</span>
  </div>

  <!-- Problem statement -->
  <div class="problem-statement">
    {% if prob %}
      {{ latex_to_html(prob.get("statement", sol.get("problem_statement", ""))) }}
    {% else %}
      {{ latex_to_html(sol.get("problem_statement", "Problem statement not available.")) }}
    {% endif %}
  </div>

  <!-- Classification -->
  {% set cls = sol.get("classification", {}) %}
  {% if cls %}
  <h3>Classification</h3>
  <p>
    <strong>{{ cls.get("primary_archetype", "—") }}</strong>
    {% if cls.get("secondary_archetypes") %}
      &ensp;|&ensp;Also: {{ cls.get("secondary_archetypes", [])|join(", ") }}
    {% endif %}
    {% if cls.get("confidence") is not none %}
      &ensp;|&ensp;Confidence: {{ "%.0f"|format(cls.get("confidence", 0) * 100) }}%
    {% endif %}
  </p>
  {% if cls.get("reasoning") %}
    <p style="font-size:10pt;color:var(--text-light);">{{ cls.get("reasoning") }}</p>
  {% endif %}
  {% endif %}

  <!-- Progressive hints -->
  {% for strat in strategies %}
  {% if strat.get("id") == rec_id and strat.get("hints") %}
  {% set hints = strat["hints"] %}
  <h3>Hints</h3>
  {% if hints.get("tier1_conceptual") %}
  <div class="hint-tier tier1">
    <div class="hint-label">Tier 1 — Conceptual Nudge</div>
    {{ latex_to_html(hints["tier1_conceptual"]) }}
  </div>
  {% endif %}
  {% if hints.get("tier2_strategic") %}
  <div class="hint-tier tier2">
    <div class="hint-label">Tier 2 — The Tool</div>
    {{ latex_to_html(hints["tier2_strategic"]) }}
  </div>
  {% endif %}
  {% if hints.get("tier3_outline") %}
  <div class="hint-tier tier3">
    <div class="hint-label">Tier 3 — Outline</div>
    {{ latex_to_html(hints["tier3_outline"]) }}
  </div>
  {% endif %}
  {% endif %}
  {% endfor %}

  <!-- Solution (recommended strategy) -->
  {% for strat in strategies %}
  {% if strat.get("id") == rec_id %}
  <h3>Solution{% if strategies|length > 1 %}: {{ strat.get("approach_name", "Primary") }}{% endif %}</h3>

  {% if strat.get("confidence") is not none %}
  <p style="font-size:10pt;color:var(--text-light);">
    Strategy confidence: {{ "%.0f"|format(strat.get("confidence", 0) * 100) }}%
  </p>
  {% endif %}

  {% if strat.get("solution") %}
    {{ latex_to_html(strat["solution"]) }}
  {% endif %}

  <!-- Solution steps -->
  {% if strat.get("solution_steps") %}
  <h4>Step-by-step breakdown</h4>
  {% for step in strat["solution_steps"] %}
  <div class="step">
    <span class="step-num">Step {{ step.get("step", loop.index) }}.</span>
    {{ latex_to_html(step.get("action", "")) }}
    {% if step.get("justification") %}
    <div class="justification">{{ latex_to_html(step["justification"]) }}</div>
    {% endif %}
    {% if step.get("kb_references") %}
    <div class="kb-refs">Refs: {{ step["kb_references"]|join(", ") }}</div>
    {% endif %}
  </div>
  {% endfor %}
  {% endif %}

  {% endif %}
  {% endfor %}

  <!-- Alternative strategies (brief) -->
  {% if strategies|length > 1 %}
  <h3>Alternative Approaches</h3>
  {% for strat in strategies %}
  {% if strat.get("id") != rec_id %}
  <h4>{{ strat.get("approach_name", "Strategy " + strat.get("id", "?")) }}
    {% if strat.get("confidence") is not none %}
      ({{ "%.0f"|format(strat.get("confidence", 0) * 100) }}%)
    {% endif %}
  </h4>
  {% if strat.get("solution") %}
    {{ latex_to_html(strat["solution"]) }}
  {% elif strat.get("attack_plan") %}
    <ol>
    {% for step in strat["attack_plan"] %}
      <li>{{ latex_to_html(step) }}</li>
    {% endfor %}
    </ol>
  {% endif %}
  {% endif %}
  {% endfor %}
  {% endif %}

  <!-- Verification detail -->
  {% if ver %}
  {% set overall = ver.get("overall", {}) %}
  <div class="verification-detail">
    <strong>Verification Report</strong>
    <div class="check-row">
      <span>Structural check</span>
      {% set sc = ver.get("structural_check", {}).get("status", "—") %}
      <span class="{% if sc == 'PASS' %}check-pass{% elif sc == 'WARN' %}check-warn{% else %}check-fail{% endif %}">{{ sc }}</span>
    </div>
    <div class="check-row">
      <span>Adversarial check</span>
      {% set ac = ver.get("adversarial_check", {}).get("status", "—") %}
      <span class="{% if ac == 'PASS' %}check-pass{% elif ac == 'FLAG' %}check-warn{% else %}check-fail{% endif %}">{{ ac }}</span>
    </div>
    <div class="check-row">
      <span>Consistency check</span>
      {% set cc = ver.get("consistency_check", {}).get("status", "—") %}
      <span class="{% if cc == 'PASS' %}check-pass{% elif cc == 'WARN' %}check-warn{% else %}check-fail{% endif %}">{{ cc }}</span>
    </div>
    {% if overall.get("summary") %}
    <p style="margin-top:0.4em;font-size:10pt;">{{ overall["summary"] }}</p>
    {% endif %}
    {% if overall.get("human_review_required") and overall.get("human_review_reason") %}
    <p style="margin-top:0.3em;font-size:10pt;color:var(--amber);">
      &#9888; {{ overall["human_review_reason"] }}
    </p>
    {% endif %}
  </div>
  {% endif %}

  <!-- Postmortem -->
  {% set pm = sol.get("postmortem", {}) %}
  {% if pm %}
  <div class="postmortem">
    <h3>Postmortem</h3>

    {% if pm.get("key_insight") %}
    <div class="insight-box">
      <div class="label">Key Insight</div>
      {{ latex_to_html(pm["key_insight"]) }}
    </div>
    {% endif %}

    {% if pm.get("transferable_technique") %}
    <div class="insight-box">
      <div class="label">Transferable Technique</div>
      {{ latex_to_html(pm["transferable_technique"]) }}
    </div>
    {% endif %}

    {% if pm.get("common_errors") %}
    <h4>Common Errors</h4>
    <ul class="error-list">
    {% for err in pm["common_errors"] %}
      <li><span>{{ latex_to_html(err) }}</span></li>
    {% endfor %}
    </ul>
    {% endif %}

    {% if pm.get("deeper_connections") %}
    <h4>Deeper Connections</h4>
    <p>{{ latex_to_html(pm["deeper_connections"]) }}</p>
    {% endif %}

    {% if pm.get("variant_problems") %}
    <h4>Variant Problems</h4>
    <ul>
    {% for v in pm["variant_problems"] %}
      <li>{{ latex_to_html(v) }}</li>
    {% endfor %}
    </ul>
    {% endif %}
  </div>
  {% endif %}

</div>
{% endfor %}

</body>
</html>
""")


# ── PDF generation ───────────────────────────────────────────────────


def _prettify_course_id(course_id: str) -> str:
    """Turn a course_id like 'linalg_ii_ht2026' into 'Linear Algebra II — HT 2026'."""
    # Common abbreviation expansions
    _ABBREVS = {
        "linalg": "Linear Algebra",
        "alg": "Algebra",
        "geom": "Geometry",
        "topo": "Topology",
        "prob": "Probability",
        "stats": "Statistics",
        "func": "Functional",
        "anal": "Analysis",
        "diff": "Differential",
        "num": "Numerical",
        "intro": "Introduction to",
    }
    _ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii"}
    _TERMS = {"ht": "HT", "mt": "MT", "tt": "TT"}

    parts = course_id.lower().split("_")
    course_parts: list[str] = []
    term_part = ""

    for p in parts:
        # Term + year like "ht2026"
        term_match = re.match(r"^(ht|mt|tt)(\d{4})$", p)
        if term_match:
            term_part = f"{_TERMS[term_match.group(1)]} {term_match.group(2)}"
            continue
        # Roman numerals
        if p in _ROMAN:
            course_parts.append(p.upper())
            continue
        # Known abbreviations
        if p in _ABBREVS:
            course_parts.append(_ABBREVS[p])
            continue
        # Bare year
        if re.match(r"^\d{4}$", p):
            term_part = term_part or p
            continue
        # Default: capitalize
        course_parts.append(p.capitalize())

    name = " ".join(course_parts)
    if term_part:
        name += f" — {term_part}"
    return name


def _infer_title_from_config(work_dir: Path) -> str | None:
    """Try to find the course config and return the course_name."""
    # Walk up from work_dir looking for config/*.yaml that has course_name
    import yaml
    for parent in [work_dir, *work_dir.parents]:
        config_dir = parent / "config"
        if config_dir.is_dir():
            for f in config_dir.glob("*.yaml"):
                try:
                    data = yaml.safe_load(f.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "course_name" in data:
                        return data["course_name"]
                except Exception:
                    continue
        # Stop at the repo root
        if (parent / ".git").exists():
            break
    return None


def compile_pdf(
    work_dir: Path,
    output_path: Path | None = None,
    title: str | None = None,
    subtitle: str | None = None,
) -> Path:
    """Compile solution files from work_dir into a PDF.

    Args:
        work_dir: Directory containing solution_N.json, etc.
        output_path: Where to write the PDF. Defaults to work_dir/solutions.pdf.
        title: Document title. Inferred from directory name if not given.
        subtitle: Document subtitle.

    Returns:
        Path to the generated PDF.
    """
    from datetime import date

    entries = load_solutions_dir(work_dir)
    if not entries:
        raise FileNotFoundError(f"No solution files found in {work_dir}")

    # Enrich entries with badge info
    for e in entries:
        e["badge"] = verification_badge(e.get("verification"))

    # Infer title from directory structure or course config
    if not title:
        parts = work_dir.resolve().parts
        # Try to load course config for the proper name
        title = _infer_title_from_config(work_dir)

        if not title and len(parts) >= 2:
            title = _prettify_course_id(parts[-2])
        elif not title:
            title = "Solutions"

    if not subtitle:
        if len(parts) >= 2:
            sheet_dir = parts[-1]
            # Extract just the number from "sheet_1" or "sheet_5356765"
            sheet_match = re.search(r"(\d+)", sheet_dir)
            if sheet_match:
                subtitle = f"Problem Sheet {sheet_match.group(1)}"
            else:
                subtitle = sheet_dir.replace("_", " ").title()
        else:
            subtitle = f"{len(entries)} Problems"

    # Render HTML
    html_str = HTML_TEMPLATE.render(
        title=title,
        subtitle=subtitle,
        entries=entries,
        latex_to_html=latex_to_html,
        generated_date=date.today().strftime("%d %B %Y"),
    )

    # Write PDF
    if output_path is None:
        output_path = work_dir / "solutions.pdf"

    HTML(string=html_str).write_pdf(str(output_path))
    return output_path


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile MathPipe solution files into a formatted PDF.",
    )
    parser.add_argument(
        "work_dir",
        type=Path,
        help="Directory containing solution_N.json files",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output PDF path (default: <work_dir>/solutions.pdf)",
    )
    parser.add_argument("--title", type=str, default=None, help="Document title")
    parser.add_argument("--subtitle", type=str, default=None, help="Document subtitle")

    args = parser.parse_args()

    if not args.work_dir.is_dir():
        print(f"Error: Not a directory: {args.work_dir}")
        return 1

    try:
        out = compile_pdf(
            work_dir=args.work_dir,
            output_path=args.output,
            title=args.title,
            subtitle=args.subtitle,
        )
        size_kb = out.stat().st_size / 1024
        print(f"PDF compiled: {out} ({size_kb:.0f} KB)")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error generating PDF: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
