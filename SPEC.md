# MathPipe — Product Specification

**Version:** 0.1.0 (MVP)
**Last updated:** 2026-02-25

---

## 1. Overview

MathPipe is an autonomous mathematics learning pipeline that converts LaTeX lecture notes and problem sheets into structured, confidence-graded study materials with genuine mathematical intuition. It targets advanced university mathematics students (Oxford-style courses in functional analysis, measure theory, algebraic topology, etc.) who want to deeply understand material rather than merely memorise it.

The system is human-in-the-loop by design: each pipeline step produces inspectable intermediate artefacts (JSON, JSONL, Markdown), allowing the student to review, correct, and steer the process before the next step runs.

### 1.1 Core Value Proposition

A student who uses MathPipe's output should gain the same intuition they would have acquired from spending hours struggling through problems themselves — compressed into a readable, structured format. This means:

- **Pattern recognition** — recognising problem types in the wild
- **Strategic taste** — knowing how a mathematician approaches a problem, not just the answer
- **Error inoculation** — knowing the traps because MathPipe walks through the trap door
- **Transferable technique** — methods applicable to unseen problems

### 1.2 What MathPipe Is NOT

- Not a homework solver — it is a study tool designed around a "struggle-first" protocol
- Not a chatbot — it is a structured pipeline with typed artefacts
- Not a generic AI tutor — it targets formal university-level proof-based mathematics

---

## 2. Architecture

### 2.1 System Components

```
┌──────────────────────────────────────────────────────────────┐
│                        CLI / Interactive                      │
│  mathpipe.py (Click)          interactive.py (InquirerPy)    │
└──────────┬───────────────────────────┬───────────────────────┘
           │                           │
           ▼                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Pipeline Core                              │
│  sheet_parser.py   latex_parser.py   router.py                │
│  config_loader.py  pipeline_state.py  kb_writer.py            │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Agent Layer                                 │
│  agent_session.py → Claude Agent SDK                          │
│  Specialised agents: KB Builder, Solver, Verifier, Generator  │
│  Each agent gets: system prompt + task message + file tools    │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Claude Models (API)                         │
│  haiku (claude-haiku-4-5)  —  fast, cheap                     │
│  sonnet (claude-sonnet-4-5) — default, balanced               │
│  opus (claude-opus-4-5)    — highest quality                  │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| CLI framework | Click 8.x | Subcommand routing, option parsing |
| Interactive mode | InquirerPy (prompt_toolkit) | Arrow-key menus, checkboxes, file pickers |
| Display | Rich | Tables, panels, progress, colour |
| Agent runtime | Claude Agent SDK | Spawn sandboxed agents with file tools |
| LLM | Claude (Haiku/Sonnet/Opus) | KB extraction, solving, verification, generation |
| Config | PyYAML | Course configuration |
| Serialisation | JSON / JSONL | All intermediate artefacts |
| Security | Custom allowlist hooks | Bash command validation for autonomous agents |
| LaTeX parsing | Pure Python (regex) | Sheet and chapter splitting |
| KB retrieval | Pure Python (keyword scoring) | Two-phase retrieval, no embeddings |

### 2.3 Design Principles

1. **Human-in-the-loop** — Every pipeline step writes inspectable files. The student runs one step, checks the output, then proceeds.
2. **Confidence-graded** — Every extraction, solution, and verification carries a numeric confidence score with explicit uncertainty flagging.
3. **No hallucination of mathematics** — Agents are instructed never to fabricate theorems. KB extraction copies LaTeX verbatim. Solutions must cite specific KB entries.
4. **Genuine insight over paraphrase** — The "intuition", "mechanism", "triggers", and "pitfalls" fields are where real value is created — not by restating theorems but by explaining what they *really* mean.
5. **Struggle-first pedagogy** — Output modes implement progressive disclosure. Hints are hidden behind spoiler tags. Solution guides simulate the experience of being stuck before revealing the answer.

---

## 3. Course Organisation

### 3.1 Directory Structure

All course materials and outputs live under a self-contained course directory:

```
courses/
  functional_analysis/              # One directory per course
    course.yaml                     # Course configuration (anchor file)
    notes/                          # Input: lecture notes (.tex)
      chapter1.tex
      chapter2.tex
    sheets/                         # Input: problem sheets (.tex)
      sheet1.tex
      sheet2.tex
    kb/                             # Output: knowledge base (generated)
      chapter_1/
        kb.jsonl                    # Structured KB entries
        chapter_source.tex          # Preserved source
        preamble.tex                # LaTeX preamble for notation
      chapter_2/
        kb.jsonl
      logs/
        kb_build_1740000000.json    # Build logs
    solutions/                      # Output: solutions (generated)
      sheet_1/
        pipeline_state.json         # Pipeline manifest
        parsed_problems.json        # Parsed problems
        routing.json                # KB routing data
        context_1.txt               # Routed KB entries for problem 1
        problem_1.json              # Problem data for solver
        solution_1.json             # Solver output
        verification_1.json         # Verifier output
        output_solution_guide.md    # Final output document
    exports/                        # Output: study materials (generated)
      kb_all.jsonl                  # Merged KB
      study.md
      anki.csv
      tricks.jsonl
```

### 3.2 Course Configuration Schema (`course.yaml`)

```yaml
# Required
course_id: "func_analysis_2026"       # Machine-readable ID (used in KB record IDs)
course_name: "Functional Analysis"    # Human-readable name
chapters:
  - id: 1                             # Positive integer, unique
    title: "Normed Spaces and Banach Spaces"
    prerequisites: []                  # Chapter IDs this depends on
  - id: 2
    title: "Bounded Linear Operators"
    prerequisites: [1]

# Optional
term: "HT2026"
source_tex: "notes/chapter.tex"       # Default LaTeX source for KB building
sheets:
  - id: 1
    filename: "sheets/sheet1.tex"
    chapters: [1, 2]                   # Chapter hints for routing
notation_overrides:                    # Course-specific symbol meanings
  "\\mathcal{B}(X,Y)": "space of bounded linear operators from X to Y"
```

**Key design decision:** The config file's parent directory becomes the `base_dir` for all path resolution. All relative paths in the config and all generated outputs resolve from this anchor. This eliminates the need for separate `--output-dir` and `--kb-dir` flags.

### 3.3 Adding a New Course

```bash
mkdir -p courses/algebraic_topology/{notes,sheets}
# Drop .tex files into notes/ and sheets/
# Write courses/algebraic_topology/course.yaml
# Done — the interactive mode auto-discovers it
```

---

## 4. Pipeline

### 4.1 Pipeline Steps

The pipeline has five ordered steps. Each step reads the output of the previous step and writes new artefacts. Steps can be run individually (for inspection) or end-to-end.

```
parse ──► route ──► solve ──► verify ──► generate
  │         │         │         │           │
  ▼         ▼         ▼         ▼           ▼
parsed    routing   solution  verific-    output
problems  .json     _N.json   ation_N     _mode
.json     context            .json        .md/.csv
          _N.txt                          /.jsonl
```

### 4.2 Step 1: Parse

**Type:** Pure Python (no LLM)
**Input:** LaTeX problem sheet (.tex)
**Output:** `parsed_problems.json`

Extracts individual problems from a LaTeX source file. Handles multiple formats:

1. `\begin{problem}` / `\begin{question}` environments
2. Numbered headings: "1.", "Problem 1.", "Question 1:", "Q1."
3. `\begin{enumerate}` with `\item` splitting (respects nesting depth)
4. Fallback: treat entire document as one problem

Sub-parts are extracted from `(a)`, `(b)` patterns, Roman numerals `(i)`, `(ii)`, and nested `\begin{enumerate}` blocks.

**Output schema:**
```json
[
  {
    "id": 1,
    "statement": "Full LaTeX text of the problem",
    "parts": [
      {"label": "a", "statement": "Sub-part text"},
      {"label": "b", "statement": "Sub-part text"}
    ],
    "raw_latex": "Original LaTeX source"
  }
]
```

### 4.3 Step 2: Route

**Type:** Pure Python (no LLM)
**Input:** `parsed_problems.json` + KB (`kb/chapter_N/kb.jsonl`)
**Output:** `routing.json` + `context_N.txt` per problem

Maps each problem to the most relevant KB entries using a two-phase keyword retrieval algorithm (see Section 6.3 for details).

The output `context_N.txt` files are human-readable formatted bundles of relevant KB entries, ready for injection into the solver's prompt.

### 4.4 Step 3: Solve

**Type:** LLM agent (Claude)
**Input:** `problem_N.json` + `context_N.txt`
**Output:** `solution_N.json`

A dedicated solver agent reads the problem and its routed KB context, then produces a structured solution (see Section 5.2 for the full schema). Key outputs include:

- Problem classification by archetype
- 1–3 solution strategies, each with tiered hints
- Full rigorous solution with step-by-step KB references
- Postmortem analysis with key insight, transferable technique, and common errors

**Agent configuration:**
- System prompt: `prompts/solver_prompt.md`
- Tools: Read, Write, Glob, Grep (file access within the work directory)
- Max turns: 40
- Model: user-selected (default: Sonnet)

### 4.5 Step 4: Verify

**Type:** LLM agent (Claude)
**Input:** `solution_N.json` + `context_N.txt`
**Output:** `verification_N.json`

An adversarial verifier agent that ASSUMES the solution contains an error and tries to find it. Performs four layers of checking (see Section 5.3 for the full schema):

1. **Structural check** — KB references valid, conclusion matches problem
2. **Adversarial check** — step-by-step error hunting, hypothesis verification, inequality direction, quantifier order, edge cases
3. **Consistency check** — conclusion matches, all hypotheses used, no circularity, no type errors
4. **Confidence assessment** — overall score, human review determination

**Status determination:**
- `verified` (confidence ≥ 0.80, no critical issues) → human review NOT required
- `flagged` (confidence 0.50–0.79 or minor issues) → human review REQUIRED
- `rejected` (confidence < 0.50 or critical error) → solution should not be trusted

**Agent configuration:**
- System prompt: `prompts/verifier_prompt.md`
- Tools: Read, Write, Glob, Grep
- Max turns: 30
- Model: user-selected (default: Sonnet)

### 4.6 Step 5: Generate

**Type:** LLM agent (Claude)
**Input:** All `solution_N.json` and `verification_N.json` files
**Output:** `output_{mode}.{ext}`

Transforms solutions into one of five output formats (see Section 7 for full details):

| Mode | Extension | Description |
|------|-----------|-------------|
| `hints` | `.md` | Progressive disclosure with spoiler tags |
| `study` | `.md` | Structured study document from KB entries |
| `solution_guide` | `.md` | Deep intuition solution guide (most ambitious) |
| `anki` | `.csv` | Understanding-oriented Anki flashcards |
| `tricks` | `.jsonl` | Transferable technique bank |

**Agent configuration:**
- System prompt: `prompts/output_prompt.md` (or `prompts/solution_guide_prompt.md` for solution_guide mode)
- Tools: Read, Write, Glob, Grep
- Max turns: 40 (60 for solution_guide)
- Model: user-selected (default: Sonnet)

---

## 5. Data Schemas

### 5.1 Knowledge Base Entry (JSONL)

Each KB record is a single JSON object on one line of a `.jsonl` file.

```json
{
  "id": "func_analysis_2026.ch1.thm.3",
  "type": "definition|theorem|lemma|proposition|corollary|example|remark",
  "name": "Banach-Steinhaus Theorem",
  "aliases": ["Uniform Boundedness Principle"],
  "chapter_id": 1,

  "statement_latex": "Exact LaTeX from source, preserved verbatim",
  "statement_natural": "Natural language version readable without rendering",

  "hypotheses": [
    {
      "id": "h1",
      "content": "X is a Banach space",
      "type": "structural|membership|bound|regularity|topological|algebraic"
    }
  ],

  "conclusion": "What the result establishes (null for definitions)",

  "proof_skeleton": {
    "strategy": "Name of the proof technique",
    "steps": [
      {
        "step": 1,
        "action": "What is done",
        "justification": "Why it works"
      }
    ],
    "hard_step": 3,
    "hard_step_explanation": "Why this step is technically demanding"
  },

  "intuition": "Genuine conceptual explanation — not a paraphrase",
  "mechanism": "How the result works mechanically — the engine",
  "triggers": ["Recognisable patterns signalling when to use this"],
  "pitfalls": ["Common mistakes and traps"],

  "dependencies": ["IDs of other KB entries this depends on"],
  "used_by": [],

  "confidence": 0.92
}
```

**ID format:** `{course_id}.ch{chapter_id}.{type_abbrev}.{sequence}`
**Type abbreviations:** `def`, `thm`, `lem`, `prop`, `cor`, `eg`, `rmk`

**Confidence scoring:**
- 0.90–1.00: Formal LaTeX environment, high confidence in all fields
- 0.75–0.89: Clearly identifiable, some interpretation needed
- 0.50–0.74: Informal/ambiguous source, uncertain fields
- Below 0.50: Guessing — requires `extraction_notes` field

**Extracted types:**
| Type | LaTeX environments | Inline patterns |
|------|-------------------|-----------------|
| definition | `\begin{definition}`, `\begin{defn}` | "We define...", "Let X be..." |
| theorem | `\begin{theorem}`, `\begin{thm}` | Named results |
| lemma | `\begin{lemma}`, `\begin{lem}` | |
| proposition | `\begin{proposition}`, `\begin{prop}` | |
| corollary | `\begin{corollary}`, `\begin{cor}` | |
| example | `\begin{example}`, `\begin{eg}` | Key illustrative examples |
| remark | `\begin{remark}`, `\begin{rmk}` | Important warnings |

### 5.2 Solution Schema (JSON)

```json
{
  "problem_id": "sheet2.q3",
  "problem_statement": "...",
  "relevant_chapters": [2, 3],

  "classification": {
    "primary_archetype": "completeness/Baire",
    "secondary_archetypes": ["epsilon-delta estimation"],
    "confidence": 0.85,
    "reasoning": "Why this classification"
  },

  "strategies": [
    {
      "id": "s1",
      "approach_name": "Baire category argument",
      "confidence": 0.90,
      "attack_plan": ["Step-by-step plan (not the solution)"],
      "hints": {
        "tier1_conceptual": "A nudge — no specifics",
        "tier2_strategic": "Name the tool + why it applies",
        "tier3_outline": "Skeleton with key steps"
      },
      "solution": "Full clean solution with all details",
      "solution_steps": [
        {
          "step": 1,
          "action": "What to do",
          "justification": "Why",
          "kb_references": ["func_analysis_2026.ch3.thm.1"]
        }
      ],
      "potential_issues": ["Things that need double-checking"]
    }
  ],

  "recommended_strategy": "s1",

  "postmortem": {
    "key_insight": "The single most important idea",
    "transferable_technique": "What to remember for future problems",
    "common_errors": ["Mistakes students would make"],
    "variant_problems": ["How to modify into related exercises"],
    "deeper_connections": "How this connects to larger themes"
  }
}
```

**Classification archetypes (non-exhaustive):**
epsilon-delta estimation, compactness argument, completeness/Baire, duality, fixed point, spectral, approximation, contradiction, induction, construction, diagonalisation, extremal, category.

**Hint tiers (struggle-first protocol):**
| Tier | Name | Reveals |
|------|------|---------|
| 1 | Conceptual nudge | Right area of mathematics, no specific theorems |
| 2 | Strategic | Specific tool/theorem + why it's relevant |
| 3 | Outline | Step-by-step skeleton with key estimates |

### 5.3 Verification Schema (JSON)

```json
{
  "problem_id": "sheet2.q3",
  "strategy_verified": "s1",

  "structural_check": {
    "status": "PASS|FAIL|WARN",
    "all_references_valid": true,
    "conclusion_matches_problem": true,
    "external_results_used": [],
    "notes": "..."
  },

  "adversarial_check": {
    "status": "PASS|FLAG|FAIL",
    "errors_found": [
      {
        "step": 3,
        "issue": "Description of potential error",
        "severity": "critical|major|minor",
        "explanation": "Why this might be wrong"
      }
    ],
    "weakest_step": 3,
    "weakest_step_reasoning": "Why this is most suspect"
  },

  "consistency_check": {
    "status": "PASS|FAIL|WARN",
    "conclusion_matches": true,
    "all_hypotheses_used": true,
    "unused_hypotheses": [],
    "circularity_detected": false,
    "type_errors": []
  },

  "overall": {
    "confidence": 0.85,
    "status": "verified|flagged|rejected",
    "human_review_required": false,
    "human_review_reason": null,
    "summary": "One-paragraph assessment"
  }
}
```

### 5.4 Pipeline State Manifest (`pipeline_state.json`)

Tracks which steps have been completed for a problem sheet.

```json
{
  "sheet_id": 1,
  "sheet_file": "courses/functional_analysis/sheets/sheet1.tex",
  "config_file": "courses/functional_analysis/course.yaml",
  "course_id": "func_analysis_2026",
  "created": "2026-02-25T10:30:00+00:00",
  "steps": {
    "parse":    {"status": "done", "timestamp": "...", "problems_count": 8},
    "route":    {"status": "done", "timestamp": "...", "total_entries": 45},
    "solve":    {"status": "partial", "timestamp": "...", "done": [1,2,3], "pending": [4,5]},
    "verify":   {"status": "pending"},
    "generate": {"status": "pending"}
  }
}
```

**Step statuses:** `pending`, `done`, `partial`, `error`

---

## 6. Key Algorithms

### 6.1 LaTeX Chapter Splitting

Given a `.tex` source file and chapter titles from `course.yaml`:

1. **Title matching** (primary): Fuzzy-match config titles against `\chapter{}`, `\section{}`, and `\part{}` headings in the LaTeX. Matching uses normalised lowercase comparison with 70% word-overlap threshold.
2. **Sequential fallback**: If title matching fails, assign boundaries to chapters in order.
3. **Single-file fallback**: If no headings found, treat the entire file as one chapter.

Preamble (everything before `\begin{document}`) is extracted separately and provided to the KB builder for notation context.

### 6.2 Problem Sheet Parsing

Tried in order until one succeeds:

1. `\begin{problem}` / `\begin{question}` environments
2. Numbered heading patterns (`/Problem\s*(\d+)/i` etc.)
3. `\begin{enumerate}` with nesting-aware `\item` splitting
4. Entire document as a single problem

Sub-parts extracted from `(a)`, `(b)`, `(i)`, `(ii)`, or nested `\begin{enumerate}`.

### 6.3 Two-Phase KB Routing

Pure Python, no LLM calls, no embeddings.

**Phase 1 — Chapter identification:**
- Extract mathematical keywords from the problem statement using a curated taxonomy of 11 mathematical topic categories (compactness, completeness, continuity, convergence, duality, Baire, spectral, topology, linearity, measure, norm) with ~80 specific terms.
- Score each chapter by aggregate keyword overlap with its KB entries.
- Select chapters with score > 0.1, or top 3 if fewer qualify.
- If `sheet.chapters` is specified in config, use those directly (skip Phase 1).

**Phase 2 — Entry scoring:**
- For each KB entry in relevant chapters, compute keyword overlap with the problem.
- Apply type boosts: theorems ×1.4, lemmas/propositions ×1.2, definitions ×1.1, examples ×0.8, remarks ×0.7.
- Apply name boost: named results ×1.3.
- Return top 15 entries per problem, sorted by score.

**Keyword extraction:** LaTeX commands stripped, multi-word mathematical phrases matched against the taxonomy, case-insensitive.

---

## 7. Output Modes

### 7.1 Hints Mode (`output_hints.md`)

Progressive disclosure document implementing the struggle-first protocol. Each problem gets:

- Classification archetype
- Tier 1 conceptual nudge (visible)
- Tier 2 strategic hint (behind `<details>` spoiler)
- Tier 3 outline (behind `<details>` spoiler)
- Attack plan (behind `<details>` spoiler)
- Full solution (behind `<details>` spoiler)

Students must actively click to reveal each tier, encouraging genuine problem-solving attempts first.

### 7.2 Study Mode (`output_study.md`)

Structured study document generated from KB entries. For each entry:

- Statement (natural language + LaTeX)
- "What it really says" (intuition)
- "How it works" (mechanism)
- "When to use it" (triggers)
- "Watch out for" (pitfalls)
- Proof sketch with hard step highlighted

Entries are ordered by dependency (definitions before theorems that use them) and grouped thematically. Checkpoint questions inserted every 3–4 entries. Chapter summary at the end identifying the 3–5 most important results.

### 7.3 Solution Guide Mode (`output_solution_guide.md`)

The most pedagogically ambitious output. For each problem:

| Section | Purpose |
|---------|---------|
| **What This Problem Is Really Asking** | Plain-language restatement of the essential difficulty |
| **Before You Read the Solution** | Simulates being stuck: names first instinct, shows where naive attempts stall, frames the insight as a question |
| **The Insight** | The "aha" moment stated boldly, then explained: why it's hard to see, what would have led you to it |
| **The Solution** | Rigorous solution with every non-trivial step annotated with strategic reasoning |
| **What Could Go Wrong** | 2–3 realistic mistakes walked through in detail |
| **What To Remember** | One-liner, pattern trigger, deeper connection |

Ends with sheet-level patterns: recurring themes, what the sheet teaches as a whole, 3 key takeaways.

### 7.4 Anki Mode (`output_anki.csv`)

Understanding-oriented flashcards. CSV columns: `front,back,tags,card_type,difficulty,source_id`.

**Card types:**
| Type | Tests |
|------|-------|
| `application` | "You're in situation X. What theorem applies?" |
| `recognition` | "Given this setup, identify the argument type" |
| `construction` | "How would you construct X to achieve Y?" |
| `failure_mode` | "Why does X fail without hypothesis Y?" |

**Anti-pattern:** Cards like "State Theorem X" / "Theorem X says..." are explicitly forbidden — they test memorisation, not understanding.

### 7.5 Tricks Mode (`output_tricks.jsonl`)

Transferable technique bank extracted from postmortems. Each trick is a JSONL entry with:

```json
{
  "id": "trick.1",
  "name": "Baire upgrade pattern",
  "description": "How to execute the technique",
  "when_to_use": ["Recognisable patterns"],
  "example_problem": "Brief problem description",
  "example_application": "How the trick applies",
  "related_theorems": ["KB IDs"],
  "tags": ["topic tags"]
}
```

A trick is a TECHNIQUE, not a theorem. "Use Baire Category" is not a trick. "Express a pointwise condition as X = ∪Aₙ where each Aₙ is closed, then Baire gives interior, then transfer local bound to global via linearity" IS a trick.

---

## 8. Agent System

### 8.1 Agent Session Model

Each pipeline step that requires an LLM (solve, verify, generate, kb build) spawns a fresh Claude Agent SDK session:

```python
client = ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-sonnet-4-5-20250929",
        system_prompt=load_prompt("solver_prompt"),
        allowed_tools=["Read", "Write", "Glob", "Grep"],
        max_turns=40,
        cwd=str(work_dir),
    )
)
```

The agent has sandboxed file access within its working directory. It reads input files, processes them, and writes output files. The CLI then validates and registers the outputs.

### 8.2 Available Models

| Name | Model ID | Use Case |
|------|----------|----------|
| haiku | claude-haiku-4-5-20251001 | Fast/cheap, good for KB extraction |
| sonnet | claude-sonnet-4-5-20250929 | Default, balanced quality/speed |
| opus | claude-opus-4-5-20251101 | Highest quality, complex problems |

Users select models per-run via `--model` flag or interactive settings. The model applies to all agents in that run.

### 8.3 Agent Specialisations

| Agent | Prompt File | Max Turns | Purpose |
|-------|------------|-----------|---------|
| KB Builder | `kb_builder_prompt.md` | 60 | Extract all mathematical objects from LaTeX chapter |
| Solver | `solver_prompt.md` | 40 | Produce structured solutions with tiered hints |
| Verifier | `verifier_prompt.md` | 30 | Adversarial error-finding in solutions |
| Output Generator | `output_prompt.md` | 40 | Transform solutions into study materials |
| Solution Guide Writer | `solution_guide_prompt.md` | 60 | Deep intuition solution guides |

### 8.4 Agent Tools

All MathPipe agents receive these tools:
- **Read** — Read files in the working directory
- **Write** — Write files in the working directory
- **Glob** — Find files by pattern
- **Grep** — Search file contents

No Bash access. No network access. Agents can only interact with the filesystem within their assigned working directory.

### 8.5 Orchestrator System (Auxiliary)

The repo also contains an orchestrator framework (`agents/orchestrator.py`, `agents/definitions.py`) for a separate workflow-automation use case. This defines four specialised sub-agents:

| Agent | Model | Tools | Purpose |
|-------|-------|-------|---------|
| linear | Haiku | Linear API + file tools | Manage Linear issues and project status |
| github | Haiku | GitHub API + file tools + Bash | Git commits, branches, PRs |
| slack | Haiku | Slack API + file tools | Send progress notifications |
| coding | Sonnet | Full coding tools | Implement features and fix bugs |

These are orchestrated by a root agent that reads project state and delegates. Models are configurable via environment variables (`LINEAR_AGENT_MODEL`, etc.).

---

## 9. CLI Interface

### 9.1 Command Overview

```
mathpipe                         Launch interactive mode (default)
mathpipe interactive             Launch interactive mode (explicit)
mathpipe parse    --config ...   Parse problem sheet
mathpipe route    --config ...   Route problems to KB
mathpipe solve    --config ...   Solve problems (LLM)
mathpipe verify   --config ...   Verify solutions (LLM)
mathpipe generate --config ...   Generate output (LLM)
mathpipe status   --config ...   Show pipeline progress
mathpipe sheet    --config ...   Full pipeline end-to-end
mathpipe kb       --config ...   Build knowledge base (LLM)
mathpipe export   --config ...   Export study materials (LLM)
```

### 9.2 Common Options

| Option | Commands | Description |
|--------|----------|-------------|
| `--config` | All | Path to `course.yaml` (required) |
| `--sheet` | parse, sheet | Path to `.tex` sheet (relative to course dir or absolute) |
| `--sheet-id` | parse, route, solve, verify, generate, status, sheet | Sheet ID (inferred from filename if omitted) |
| `--model` | solve, verify, generate, sheet, kb, export | `haiku`, `sonnet`, or `opus` |
| `--problems` | solve, verify | Comma-separated problem IDs (e.g. `1,3,5`) |
| `--mode` | generate, sheet | Output mode: `hints`, `study`, `solution_guide`, `anki`, `tricks` |
| `--source` | kb | LaTeX source for KB building (defaults to `source_tex` from config) |
| `--chapters` | kb, export | Comma-separated chapter IDs |
| `--format` | export | Export format: `study`, `anki`, `tricks` |
| `--skip-verify` | sheet | Skip verification in full pipeline |

### 9.3 Interactive Mode

Launched by running `mathpipe` with no arguments. Features:

- **Arrow-key + j/k navigation** through all menus (InquirerPy with vim keybindings)
- **Session memory** — config, sheet, model persist between steps
- **File auto-discovery** — finds `courses/*/course.yaml` for configs, `courses/*/sheets/*.tex` for sheets, `courses/*/notes/*.tex` for notes
- **Checkbox multi-select** — pick specific problems to solve/verify (space to toggle)
- **Status hints** — completed steps shown in main menu
- **Settings menu** — change model, config, sheet mid-session

**Main menu:**
```
  ── Sheet Pipeline ──
▸ Parse         Extract problems from LaTeX sheet
  Route         Match problems to KB entries
  Solve         Generate solutions (LLM)
  Verify        Check solutions (LLM)
  Generate      Create output (hints/study/guide)
  ── Other ──
  Status        Show pipeline progress
  Build KB      Extract knowledge base from notes
  Settings      Change model, config, sheet
  Exit
```

---

## 10. Knowledge Base Building

### 10.1 Process

1. **Extract preamble** — custom LaTeX commands and package imports for notation context
2. **Split into chapters** — match course.yaml chapter titles against LaTeX headings
3. **Per chapter, spawn KB Builder agent** — reads chapter source + preamble, extracts all mathematical objects
4. **Validate output** — check JSONL format, required fields, unique IDs, confidence ranges
5. **Write log** — build statistics (records per chapter, confidence distribution)

### 10.2 Extraction Rules

- Extract EVERYTHING: formal environments AND inline statements
- Preserve LaTeX exactly in `statement_latex`
- NEVER invent mathematical content not in the source
- DO provide genuine insight in intuition/mechanism/triggers/pitfalls (drawing on mathematical knowledge)
- Number items sequentially within each type per chapter
- Cross-reference dependencies within the chapter
- Mark uncertain extractions with `extraction_notes` and lowered confidence

### 10.3 KB Validation

Post-extraction validation checks:
- File exists and is valid JSONL
- Each record has required fields (`id`, `type`)
- IDs are unique
- Types are from the valid set
- Confidence scores are in [0, 1]
- Issues reported with capped output (max 10)

---

## 11. Security

### 11.1 Bash Command Allowlist

The `security.py` module implements a pre-tool-use hook for the autonomous coding agent system. It uses an allowlist approach:

**Allowed commands:** `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `find`, `cp`, `mv`, `mkdir`, `rm`, `touch`, `chmod`, `unzip`, `pwd`, `cd`, `echo`, `printf`, `curl`, `which`, `env`, `python`, `python3`, `npm`, `npx`, `node`, `git`, `ps`, `lsof`, `sleep`, `pkill`, `init.sh`

**Extra validation for sensitive commands:**
- `pkill` — only dev-related processes (node, npm, npx, vite, next)
- `chmod` — only `+x` variants (making files executable)
- `rm` — blocks system directories (`/`, `/etc`, `/usr`, `/home`, etc.)
- `init.sh` — only `./init.sh` or paths ending in `/init.sh`

### 11.2 Command Parsing

Handles compound commands (`&&`, `||`, `;`), pipes (`|`), subshells, and variable assignments. Uses `shlex.split()` for safe parsing. Malformed commands that cannot be parsed are blocked (fail-safe).

### 11.3 MathPipe Agent Sandboxing

MathPipe agents (KB Builder, Solver, Verifier, Generator) have no Bash access. They only receive `Read`, `Write`, `Glob`, and `Grep` tools, restricted to their working directory. This prevents any command execution or network access.

---

## 12. Export System

The `export` command generates study materials from the knowledge base across chapters:

1. Loads KB entries from specified chapters
2. Merges into a single `kb_all.jsonl`
3. Spawns a generator agent to produce the requested format

| Format | Output | Description |
|--------|--------|-------------|
| `study` | `exports/study.md` | Structured study notes from KB entries |
| `anki` | `exports/anki.csv` | Understanding-oriented flashcards |
| `tricks` | `exports/tricks.jsonl` | Transferable technique bank |

Exports are course-wide (spanning chapters), whereas `generate` is per-sheet.

---

## 13. Error Handling and Edge Cases

### 13.1 Pipeline Recovery

- Pipeline state is written to disk after each step completes
- `solve` and `verify` support `--problems` to re-run specific problems without redoing everything
- State tracks `done` and `pending` problem IDs, enabling partial runs
- If an agent fails, the step is marked `partial` (not `error`) and remaining problems can still be processed

### 13.2 Parser Robustness

- Multiple parsing strategies tried in sequence (environments → numbered headings → enumerate → whole-document)
- Sub-part extraction handles lettered, Roman numeral, and nested enumerate formats
- Preamble stripping removes `\begin{document}`...`\end{document}` scaffolding

### 13.3 Routing Fallbacks

- If no chapters score above 0.1, falls back to top 3 chapters
- If KB is empty, returns clear error before solve step
- Config `sheet.chapters` hints bypass Phase 1 entirely for precise control

---

## 14. Dependencies

### 14.1 Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| anthropic | ≥0.52 | Claude API client |
| claude-agent-sdk | (bundled) | Agent orchestration |
| click | 8.3.1 | CLI framework |
| rich | ≥13.0 | Terminal display |
| InquirerPy | ≥0.3.4 | Interactive prompts |
| PyYAML | 6.0.2 | Config loading |
| python-dotenv | 1.1.1 | Environment variables |
| httpx | 0.28.1 | HTTP client |
| pydantic | 2.12.5 | Data validation |
| jsonschema | 4.26.0 | Schema validation |
| cryptography | 46.0.4 | Security utilities |
| PyJWT | 2.10.1 | JWT handling |

### 14.2 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `ARCADE_API_KEY` | No | Arcade MCP gateway (for orchestrator) |
| `ARCADE_GATEWAY_SLUG` | No | Arcade gateway slug |
| `ORCHESTRATOR_MODEL` | No | Override orchestrator model |
| `*_AGENT_MODEL` | No | Override per-agent models |

---

## 15. Glossary

| Term | Definition |
|------|-----------|
| **KB** | Knowledge Base — structured JSONL records extracted from lecture notes |
| **Routing** | Matching problems to relevant KB entries using keyword scoring |
| **Context bundle** | The set of KB entries routed to a specific problem |
| **Work directory** | `courses/<name>/solutions/sheet_<id>/` — where all per-sheet artefacts live |
| **Base directory** | The course root folder (parent of `course.yaml`) |
| **Struggle-first** | Pedagogical protocol: hints are progressively revealed, encouraging genuine attempts before showing answers |
| **Postmortem** | Analysis section of a solution: key insight, transferable technique, common errors, variant problems |
| **Archetype** | Classification of a problem by its primary proof technique |
| **Confidence score** | 0.0–1.0 rating of certainty in an extraction, solution, or verification |
