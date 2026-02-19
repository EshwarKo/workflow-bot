#!/usr/bin/env python3
"""
Solution PDF Compiler (LaTeX)
=============================

Reads solution_N.json, verification_N.json, and problem_N.json files from a
MathPipe solutions directory, generates a beautifully formatted LaTeX document,
and compiles it to PDF via pdflatex.

Usage:
    python compile_pdf.py solutions/linalg_ii_ht2026/sheet_5356765
    python compile_pdf.py solutions/linalg_ii_ht2026/sheet_5356765 -o my_solutions.pdf
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from jinja2 import Environment


# ── Jinja2 environment with LaTeX-safe delimiters ────────────────────

_JINJA_ENV = Environment(
    block_start_string="<%",
    block_end_string="%>",
    variable_start_string="<<",
    variable_end_string=">>",
    comment_start_string="<#",
    comment_end_string="#>",
    autoescape=False,
)


# ── Text processing: Markdown+LaTeX mix → clean LaTeX ────────────────

_MATH_SENTINEL = "\x00"

# ── Unicode → LaTeX mapping tables ──────────────────────────────────

_UNICODE_SUPERSCRIPTS = {
    '\u00b0': '0', '\u00b9': '1', '\u00b2': '2', '\u00b3': '3',
    '\u2074': '4', '\u2075': '5', '\u2076': '6',
    '\u2077': '7', '\u2078': '8', '\u2079': '9',
    '\u207a': '+', '\u207b': '-', '\u207f': 'n', '\u2071': 'i',
    '\u1d48': 'd', '\u1d49': 'e', '\u02b0': 'h',
    '\u02b2': 'j', '\u1d4f': 'k', '\u02e1': 'l',
    '\u1d50': 'm', '\u1d52': 'o', '\u1d56': 'p',
    '\u02b3': 'r', '\u02e2': 's', '\u1d57': 't',
    '\u1d58': 'u', '\u1d5b': 'v', '\u02b7': 'w',
    '\u02e3': 'x', '\u1d5d': 'y',  # no standard z
    '\u1d2c': 'A', '\u1d2e': 'B', '\u1d30': 'D',
    '\u1d31': 'E', '\u1d33': 'G', '\u1d34': 'H',
    '\u1d35': 'I', '\u1d36': 'J', '\u1d37': 'K',
    '\u1d38': 'L', '\u1d39': 'M', '\u1d3a': 'N',
    '\u1d3c': 'O', '\u1d3e': 'P', '\u1d3f': 'R',
    '\u1d40': 'T', '\u1d41': 'U', '\u2c7d': 'V',
    '\u1d42': 'W',
    '\u1d43': 'a', '\u1d47': 'b', '\u1d9c': 'c',
    '\u1da0': 'f', '\u1d4d': 'g',
}

_UNICODE_SUBSCRIPTS = {
    '\u2080': '0', '\u2081': '1', '\u2082': '2', '\u2083': '3',
    '\u2084': '4', '\u2085': '5', '\u2086': '6',
    '\u2087': '7', '\u2088': '8', '\u2089': '9',
    '\u2090': 'a', '\u2091': 'e', '\u2092': 'o',
    '\u2093': 'x', '\u2095': 'h', '\u2096': 'k',
    '\u2097': 'l', '\u2098': 'm', '\u2099': 'n',
    '\u209a': 'p', '\u209b': 's', '\u209c': 't',
    '\u1d62': 'i', '\u2c7c': 'j', '\u1d63': 'r',
    '\u1d64': 'u', '\u1d65': 'v',
    '\u208a': '+', '\u208b': '-', '\u208c': '=',
    '\u208d': '(', '\u208e': ')',
}

_UNICODE_GREEK = {
    '\u03b1': '\\alpha', '\u03b2': '\\beta', '\u03b3': '\\gamma',
    '\u03b4': '\\delta', '\u03b5': '\\varepsilon', '\u03b6': '\\zeta',
    '\u03b7': '\\eta', '\u03b8': '\\theta', '\u03b9': '\\iota',
    '\u03ba': '\\kappa', '\u03bb': '\\lambda', '\u03bc': '\\mu',
    '\u03bd': '\\nu', '\u03be': '\\xi', '\u03c0': '\\pi',
    '\u03c1': '\\rho', '\u03c3': '\\sigma', '\u03c4': '\\tau',
    '\u03c5': '\\upsilon', '\u03c6': '\\varphi', '\u03c7': '\\chi',
    '\u03c8': '\\psi', '\u03c9': '\\omega',
    '\u0393': '\\Gamma', '\u0394': '\\Delta', '\u0398': '\\Theta',
    '\u039b': '\\Lambda', '\u039e': '\\Xi', '\u03a0': '\\Pi',
    '\u03a3': '\\Sigma', '\u03a6': '\\Phi', '\u03a8': '\\Psi',
    '\u03a9': '\\Omega',
}

_UNICODE_SYMBOLS = {
    '\u211d': '\\mathbb{R}', '\u2102': '\\mathbb{C}',
    '\u2115': '\\mathbb{N}', '\u2124': '\\mathbb{Z}',
    '\u211a': '\\mathbb{Q}',
    '\u2208': '\\in', '\u2209': '\\notin',
    '\u2282': '\\subset', '\u2283': '\\supset',
    '\u2286': '\\subseteq', '\u2287': '\\supseteq',
    '\u222a': '\\cup', '\u2229': '\\cap',
    '\u2295': '\\oplus', '\u2297': '\\otimes',
    '\u22a5': '\\perp', '\u221e': '\\infty', '\u2205': '\\emptyset',
    '\u2264': '\\leq', '\u2265': '\\geq',
    '\u2260': '\\neq', '\u2261': '\\equiv',
    '\u2248': '\\approx', '\u223c': '\\sim', '\u2245': '\\cong',
    '\u2192': '\\to', '\u2190': '\\leftarrow', '\u21a6': '\\mapsto',
    '\u21d2': '\\Rightarrow', '\u21d0': '\\Leftarrow',
    '\u21d4': '\\Leftrightarrow',
    '\u2200': '\\forall', '\u2203': '\\exists',
    '\u00b7': '\\cdot', '\u22c5': '\\cdot',
    '\u00d7': '\\times', '\u00f7': '\\div',
    '\u00b1': '\\pm', '\u2213': '\\mp',
    '\u220f': '\\prod', '\u2211': '\\sum', '\u222b': '\\int',
    '\u221a': '\\sqrt', '\u2202': '\\partial', '\u2207': '\\nabla',
    '\u2026': '\\ldots', '\u22ef': '\\cdots',
    '\u22ee': '\\vdots', '\u22f1': '\\ddots',
    # Miscellaneous
    '\u2713': '\\checkmark', '\u2714': '\\checkmark',  # ✓ ✔
    '\u2717': '\\times', '\u2718': '\\times',  # ✗ ✘
    '\u25b3': '\\triangle', '\u25bd': '\\triangledown',
    '\u22c6': '\\star', '\u2606': '\\star',
    '\u2016': '\\|',  # ‖ double vertical line
    '\u27e8': '\\langle', '\u27e9': '\\rangle',  # ⟨ ⟩
    '\u2039': '\\langle', '\u203a': '\\rangle',  # ‹ ›
}

# Unicode box-drawing and bracket characters → LaTeX equivalents
_UNICODE_MISC = {
    '\u2502': '|', '\u2503': '|',  # │ ┃
    '\u250c': '', '\u2510': '', '\u2514': '', '\u2518': '',  # box corners
    '\u2500': '-', '\u2501': '-',  # ─ ━
    '\u2523': '|', '\u252b': '|',  # ┣ ┫
    '\u253c': '+',  # ┼
    '\u23a1': '[', '\u23a2': '[', '\u23a3': '[',  # ⎡ ⎢ ⎣
    '\u23a4': ']', '\u23a5': ']', '\u23a6': ']',  # ⎤ ⎥ ⎦
    '\u23a7': '\\{', '\u23a8': '\\{', '\u23a9': '\\{',  # ⎧ ⎨ ⎩
    '\u23ab': '\\}', '\u23ac': '\\}', '\u23ad': '\\}',  # ⎫ ⎬ ⎭
    '\u239b': '(', '\u239c': '(', '\u239d': '(',  # ⎛ ⎜ ⎝
    '\u239e': ')', '\u239f': ')', '\u23a0': ')',  # ⎞ ⎟ ⎠
    '\u22c5': '\\cdot', '\u2022': '\\bullet',  # · •
    # Dashes and quotation marks
    '\u2014': '---', '\u2013': '--',  # — –  (em/en dashes)
    '\u2018': '`', '\u2019': "'",  # ' '  (curly single quotes)
    '\u201c': '``', '\u201d': "''",  # " "  (curly double quotes)
    '\u2032': "'", '\u2033': "''",  # ′ ″  (prime marks)
    '\u2010': '-', '\u2011': '-', '\u2012': '-',  # various hyphens
    '\u00a0': '~',  # non-breaking space
    '\u2009': '\\,', '\u200a': '',  # thin/hair space
    '\u200b': '', '\u200c': '', '\u200d': '',  # zero-width chars
    '\ufeff': '',  # BOM
}

# Characters that signal "this must be in math mode"
_MATH_TRIGGER_RE = re.compile(
    r'(?<!\\)[_^]'
    r'|\\(?:alpha|beta|gamma|delta|varepsilon|epsilon|zeta|eta|theta'
    r'|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|varphi|phi'
    r'|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Phi|Psi|Omega'
    r'|leq|geq|neq|in|notin|subset|supset|subseteq|supseteq'
    r'|cup|cap|oplus|otimes|to|mapsto|cdot|times|div|pm|mp'
    r'|infty|emptyset|partial|nabla|ldots|cdots|vdots|ddots'
    r'|frac|sqrt|sum|prod|int|det|ker|dim|rank|tr|diag|sgn'
    r'|mathbb|mathcal|mathfrak|operatorname'
    r'|checkmark|triangle'
    r'|Rightarrow|Leftarrow|Leftrightarrow|forall|exists)\b'
)

# LaTeX commands that are math-operator/relation (used for Pattern 2b)
_LATEX_MATH_OPS = (
    r'\\(?:leq|geq|neq|in|notin|subset|supset|subseteq|supseteq'
    r'|to|mapsto|equiv|approx|sim|cong|cdot|times|div|pm|mp'
    r'|oplus|otimes|cup|cap'
    r'|Rightarrow|Leftarrow|Leftrightarrow)'
)

# A "math token": variable or command with optional subscripts/superscripts
_MATH_TOKEN = (
    r'(?:\d*(?:[A-Za-z]+|\\[a-zA-Z]+(?:\{[^}]*\})?)'
    r'(?:(?<!\\)[_^](?:\{[^}]*\}|[A-Za-z0-9]))*'
    r'(?:\([^)]*\))?)'
)

# Number token (possibly negative, with optional decimal)
_NUM_TOKEN = r'(?:-?\d+(?:\.\d+)?)'


def _has_math_trigger(s: str) -> bool:
    """Return True if string contains something that must be in math mode."""
    return bool(_MATH_TRIGGER_RE.search(s))


def _unicode_to_latex(text: str) -> str:
    """Convert Unicode math characters to their LaTeX command equivalents.

    This is a pre-processing step: it turns Unicode Greek letters, sub/super-
    scripts, double-struck letters, and math symbols into LaTeX notation so
    that downstream wrapping can detect them as math content.
    """
    result = text

    # Replace runs of Unicode superscript characters → ^{...}
    sup_chars_re = '[' + ''.join(re.escape(c) for c in _UNICODE_SUPERSCRIPTS) + ']+'
    def _sup_repl(m: re.Match) -> str:
        return '^{' + ''.join(_UNICODE_SUPERSCRIPTS.get(c, c) for c in m.group(0)) + '}'
    result = re.sub(sup_chars_re, _sup_repl, result)

    # Replace runs of Unicode subscript characters → _{...}
    sub_chars_re = '[' + ''.join(re.escape(c) for c in _UNICODE_SUBSCRIPTS) + ']+'
    def _sub_repl(m: re.Match) -> str:
        return '_{' + ''.join(_UNICODE_SUBSCRIPTS.get(c, c) for c in m.group(0)) + '}'
    result = re.sub(sub_chars_re, _sub_repl, result)

    # Replace Greek letters; add space after only if followed by an ASCII letter
    # (to prevent \alphax being parsed as one command)
    for uchar, cmd in _UNICODE_GREEK.items():
        # re.sub replacement must escape backslashes
        result = re.sub(
            re.escape(uchar) + r'(?=[A-Za-z])',
            cmd.replace('\\', '\\\\') + ' ',
            result,
        )
        result = result.replace(uchar, cmd)

    # Replace double-struck and other symbol characters
    for uchar, cmd in _UNICODE_SYMBOLS.items():
        # If cmd is a \command, use re.sub to add space before following letters
        if cmd.startswith('\\') and cmd[1:].isalpha():
            result = re.sub(
                re.escape(uchar) + r'(?=[A-Za-z])',
                cmd.replace('\\', '\\\\') + ' ',
                result,
            )
        result = result.replace(uchar, cmd)

    # Replace box-drawing / bracket characters
    for uchar, repl in _UNICODE_MISC.items():
        result = result.replace(uchar, repl)

    return result


def _sanitize_non_ascii(text: str) -> str:
    """Strip or replace any remaining non-ASCII characters that would cause
    'Text line contains an invalid character' errors in LaTeX.

    This is a last-resort pass after all known Unicode→LaTeX conversions.
    It preserves standard ASCII and common safe Latin-1 characters that
    LaTeX can handle with T1 encoding.
    """
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if cp < 128:
            # Standard ASCII — always safe
            out.append(ch)
        elif ch in ('\u00e0', '\u00e1', '\u00e2', '\u00e3', '\u00e4',  # àáâãä
                     '\u00e8', '\u00e9', '\u00ea', '\u00eb',  # èéêë
                     '\u00ec', '\u00ed', '\u00ee', '\u00ef',  # ìíîï
                     '\u00f2', '\u00f3', '\u00f4', '\u00f5', '\u00f6',  # òóôõö
                     '\u00f9', '\u00fa', '\u00fb', '\u00fc',  # ùúûü
                     '\u00e7', '\u00f1', '\u00df', '\u00ff',  # çñßÿ
                     '\u00c0', '\u00c1', '\u00c2', '\u00c3', '\u00c4',  # ÀÁÂÃÄ
                     '\u00c8', '\u00c9', '\u00ca', '\u00cb',  # ÈÉÊË
                     '\u00cc', '\u00cd', '\u00ce', '\u00cf',  # ÌÍÎÏ
                     '\u00d2', '\u00d3', '\u00d4', '\u00d5', '\u00d6',  # ÒÓÔÕÖ
                     '\u00d9', '\u00da', '\u00db', '\u00dc',  # ÙÚÛÜ
                     '\u00c7', '\u00d1',  # ÇÑ
                     ):
            # Common accented characters — T1 encoding handles these
            out.append(ch)
        else:
            # Unknown character — drop it to prevent LaTeX errors
            pass
    return ''.join(out)


def _split_math_text(text: str) -> list[str]:
    """Split *text* into alternating [non-math, math, non-math, …] segments.

    Math segments (odd indices) are already-delimited: $…$, $$…$$,
    \\(…\\), \\[…\\], or LaTeX environments.
    """
    return re.split(
        r'(\$\$.*?\$\$'
        r'|\$(?!\$).*?(?<!\$)\$'
        r'|\\\(.*?\\\)'
        r'|\\\[.*?\\\]'
        r'|\\begin\{(?:v|b|p|V|B)?matrix\}.*?\\end\{(?:v|b|p|V|B)?matrix\}'
        r'|\\begin\{(?:align\*?|equation\*?|gather\*?|cases)\}'
        r'.*?\\end\{(?:align\*?|equation\*?|gather\*?|cases)\})',
        text,
        flags=re.DOTALL,
    )


def _apply_to_non_math(text: str, fn) -> str:
    """Split by $…$ (and other math delimiters), apply *fn* only to the
    non-math segments, and reassemble."""
    parts = _split_math_text(text)
    return ''.join(
        part if i % 2 == 1 else fn(part)
        for i, part in enumerate(parts)
    )


def _pattern_subscript_superscript(text: str) -> str:
    """Pattern 1: wrap variables/commands that have subscripts or superscripts.

    Matches D_n, D_{n-1}, C_{11}, x^2, A^T, 2D_{n-1}, \\chi_J,
    1^n, (r-1)^{2}, (-1)^{1+j}, etc.
    Does NOT match bare commands like \\geq or \\lambda (no script) —
    those are handled by Pattern 2 or 3.
    """
    # Base can be: letters, digits, LaTeX command, or parenthesized expression
    _BASE = (
        r'(?:\d+|[A-Za-z]+|\\[a-zA-Z]+(?:\{[^}]*\})?|\([^)]*\))'
    )
    # Subscript/superscript argument: {braced}, single char, or (parenthesized)
    _SCRIPT_ARG = r'(?:\{[^}]*\}|[A-Za-z0-9]|\([^)]*\))'
    # Optional digit prefix (e.g. 2D_{n-1})
    _TOKEN_WITH_SCRIPT = (
        r'(?:\d*' + _BASE +
        r'(?:(?<!\\)[_^]' + _SCRIPT_ARG + r')+'
        r'(?:\([^)]*\))?)'
    )
    return re.sub(
        r'(' + _TOKEN_WITH_SCRIPT + r')',
        r'$\1$',
        text,
    )


def _pattern_standalone_commands(text: str) -> str:
    """Pattern 2: wrap standalone math 'nouns' (Greek letters, blackboard bold).

    Does NOT include relational/binary operators (\\leq, \\in, etc.) — those
    are handled by Pattern 3 together with their operands.
    """
    _STANDALONE = (
        r'alpha|beta|gamma|delta|varepsilon|epsilon|zeta|eta|theta'
        r'|iota|kappa|lambda|mu|nu|xi|pi|rho|sigma|tau|upsilon|varphi|phi'
        r'|chi|psi|omega|Gamma|Delta|Theta|Lambda|Xi|Pi|Sigma|Phi|Psi|Omega'
        r'|infty|emptyset|partial|nabla|ldots|cdots|vdots|ddots'
        r'|checkmark|triangle'
        r'|mathbb\{[^}]*\}|mathcal\{[^}]*\}|mathfrak\{[^}]*\}'
    )
    return re.sub(
        r'(\\(?:' + _STANDALONE + r')'
        r'(?:(?<!\\)[_^](?:\{[^}]*\}|[A-Za-z0-9]|\([^)]*\)))*'
        r')'
        r'(?![a-zA-Z])',
        r'$\1$',
        text,
    )


def _pattern_operator_expressions(text: str) -> str:
    """Pattern 3: wrap ``token OP token`` where OP is a math operator.

    Catches: n \\geq 3, v \\neq 0, x \\in V, A \\oplus B, n = 1, etc.
    """
    _GENERAL_TOKEN = r'(?:' + _NUM_TOKEN + r'|' + _MATH_TOKEN + r')'
    _ALL_OPS = r'(?:[=<>]|' + _LATEX_MATH_OPS + r')'

    def _wrap_op_expr(m: re.Match) -> str:
        left, op, right = m.group(1), m.group(2), m.group(3)
        # Always wrap if operator is a LaTeX command (\leq, \in, etc.)
        if op.startswith('\\'):
            return f'${left} {op} {right}$'
        # Wrap if either side has a math trigger
        if _has_math_trigger(left) or _has_math_trigger(right):
            return f'${left} {op} {right}$'
        # Wrap if one side is a single letter and other is a number or single letter
        ls, rs = left.strip(), right.strip()
        if (len(ls) == 1 and ls.isalpha()
                and (rs.lstrip('-').replace('.', '').isdigit()
                     or (len(rs) <= 2 and rs[0].isalpha()))):
            return f'${left} {op} {right}$'
        return m.group(0)

    return re.sub(
        r'(' + _GENERAL_TOKEN + r')'
        r'\s*(' + _ALL_OPS + r')\s*'
        r'(' + _GENERAL_TOKEN + r')',
        _wrap_op_expr,
        text,
    )


def _merge_math_blocks(text: str) -> str:
    """Merge adjacent $…$ blocks connected by operators or bare numbers/vars.

    Uses _split_math_text to properly identify $…$ boundaries (avoiding the
    ambiguity where a closing $ could be mistaken for an opening $ of a
    phantom block).
    """
    # ── helpers ───────────────────────────────────────────────────────
    _GAP_OPERATOR_RE = re.compile(
        r'[=+\-*/<>^_()]'
        r'|\\(?:cdot|times|div|pm|mp|leq|geq|neq|in|to|mapsto)'
    )

    def _is_inline_math(s: str) -> bool:
        """True if *s* is an inline $…$ block (not display math)."""
        return (s.startswith('$') and s.endswith('$')
                and not s.startswith('$$')
                and not s.startswith('\\['))

    def _inner(s: str) -> str:
        """Strip the outer $ delimiters from an inline $…$ block."""
        return s[1:-1]

    def _should_merge_gap(gap: str) -> bool:
        stripped = gap.strip()
        if not stripped or len(stripped) > 80:
            return False
        if not _GAP_OPERATOR_RE.search(stripped):
            return False
        # Remove LaTeX commands before checking for English words
        text_only = re.sub(r'\\[a-zA-Z]+', '', stripped)
        if re.search(r'[A-Za-z]{3,}', text_only):
            return False
        return True

    _BARE_ATOM = r'(?:-?\d+(?:\.\d+)?[A-Za-z]?|[A-Za-z])'
    _ANY_OP = r'(?:[=+\-*/<>]|' + _LATEX_MATH_OPS + r')'

    # ── iterative merge loop ─────────────────────────────────────────
    result = text
    changed = True
    iters = 0
    while changed and iters < 40:
        changed = False
        iters += 1

        parts = _split_math_text(result)
        # parts = [text0, math1, text1, math2, text2, ...]
        # Odd indices are math segments.
        if len(parts) < 3:
            break  # nothing to merge (0 or 1 math blocks)

        merged: list[str] = []
        i = 0
        while i < len(parts):
            if i % 2 == 0:
                # Non-math segment
                merged.append(parts[i])
                i += 1
                continue

            # parts[i] is a math segment
            cur_math = parts[i]

            # Only merge inline $…$ blocks (not display math / environments)
            if not _is_inline_math(cur_math):
                merged.append(cur_math)
                i += 1
                continue

            # Try to merge with subsequent math blocks
            while i + 2 < len(parts):
                gap = parts[i + 1]   # text between this and next math
                nxt = parts[i + 2]   # next math block

                if not _is_inline_math(nxt):
                    break

                # (a) Whitespace-only gap → merge
                if gap.strip() == '':
                    cur_math = '$' + _inner(cur_math) + ' ' + _inner(nxt) + '$'
                    changed = True
                    i += 2
                    continue

                # (b) Math-like gap (operators, single letters, digits)
                if _should_merge_gap(gap):
                    cur_math = '$' + _inner(cur_math) + ' ' + gap.strip() + ' ' + _inner(nxt) + '$'
                    changed = True
                    i += 2
                    continue

                break  # gap is English text, stop merging

            # Try to absorb bare atoms from surrounding text
            # Right side: $A$ op atom  →  $A op atom$
            if merged and i + 1 < len(parts):
                right_text = parts[i + 1] if i + 1 < len(parts) else ''
                m_right = re.match(
                    r'(\s*)(' + _ANY_OP + r')(\s*)(' + _BARE_ATOM + r')(?![A-Za-z_^$\\])',
                    right_text,
                )
                if m_right and _is_inline_math(cur_math):
                    cur_math = '$' + _inner(cur_math) + ' ' + m_right.group(2) + ' ' + m_right.group(4) + '$'
                    parts[i + 1] = right_text[m_right.end():]
                    changed = True

            # Left side: atom op $B$  →  $atom op B$
            if merged and _is_inline_math(cur_math):
                left_text = merged[-1]
                m_left = re.search(
                    r'(?<![A-Za-z_^$\\])(' + _BARE_ATOM + r')(\s*)(' + _ANY_OP + r')(\s*)$',
                    left_text,
                )
                if m_left:
                    cur_math = '$' + m_left.group(1) + ' ' + m_left.group(3) + ' ' + _inner(cur_math) + '$'
                    merged[-1] = left_text[:m_left.start()]
                    changed = True

            merged.append(cur_math)
            i += 1

        result = ''.join(merged)

    return result


def _safety_wrap_bare_commands(text: str) -> str:
    """Safety net: wrap any remaining bare LaTeX math commands in $...$
    to prevent 'Undefined control sequence' and 'Missing $ inserted' errors.

    This is applied only to non-math segments via _apply_to_non_math.
    """
    _MATH_ONLY_CMDS = (
        r'\\(?:cdot|times|div|pm|mp|vdots|ddots|ldots|cdots'
        r'|leq|geq|neq|in|notin|subset|supset|subseteq|supseteq'
        r'|to|mapsto|oplus|otimes|cup|cap'
        r'|Rightarrow|Leftarrow|Leftrightarrow|forall|exists'
        r'|checkmark|triangle|infty|emptyset|partial|nabla)'
    )
    result = re.sub(
        r'(' + _MATH_ONLY_CMDS + r')(?![a-zA-Z])',
        r'$\1$',
        text,
    )
    # Wrap bare ^{…}, _{…}, ^(…) that escaped processing
    result = re.sub(
        r'((?<!\\)[_^](?:\{[^}]*\}|[A-Za-z0-9]|\([^)]*\))(?:(?<!\\)[_^](?:\{[^}]*\}|[A-Za-z0-9]|\([^)]*\)))*)',
        r'$\1$',
        result,
    )
    return result


def _wrap_remaining_math_segments(text: str) -> str:
    """Wrap non-math segments that are entirely math-like (no English words).

    After the main pattern passes and merge, some segments may still contain
    bare math operators/symbols with no prose.  This catches them.
    """
    def _wrap_segment(seg: str) -> str:
        stripped = seg.strip()
        if not stripped:
            return seg
        # Must contain a math trigger
        if not _has_math_trigger(stripped):
            return seg
        # Remove LaTeX commands before checking for English words
        text_only = re.sub(r'\\[a-zA-Z]+(?:\{[^}]*\})?', '', stripped)
        # If no 3+ letter English words remain, wrap in $...$
        if not re.search(r'[A-Za-z]{3,}', text_only):
            return ' $' + stripped + '$ '
        return seg

    return _apply_to_non_math(text, _wrap_segment)


def _wrap_bare_math(text: str) -> str:
    """Find undelimited math expressions in *text* and wrap them in $...$,
    while leaving already-delimited math untouched.

    Each pattern step re-splits the text so that earlier $…$ insertions
    are respected by later patterns.
    """
    # Step 1: Subscripts & superscripts  (D_n, x^2, \chi_{1}(\lambda), …)
    text = _apply_to_non_math(text, _pattern_subscript_superscript)
    # Step 2: Standalone math nouns       (\lambda, \mathbb{R}, \infty, …)
    text = _apply_to_non_math(text, _pattern_standalone_commands)
    # Step 3: Operator expressions        (n \geq 3, v \neq 0, x \in V, …)
    text = _apply_to_non_math(text, _pattern_operator_expressions)
    # Step 4: Safety net — wrap any remaining bare math commands
    text = _apply_to_non_math(text, _safety_wrap_bare_commands)
    # Step 5: Merge adjacent $…$ blocks   ($D_n$ = $n+1$  →  $D_n = n+1$)
    text = _merge_math_blocks(text)
    # Step 6: Wrap any remaining non-math segments that are entirely math
    text = _wrap_remaining_math_segments(text)
    # Step 7: Final merge pass (step 6 may have created new adjacent blocks)
    text = _merge_math_blocks(text)
    return text


def text_to_latex(text: str) -> str:
    """Convert solver output (English prose with embedded LaTeX math and
    optional Markdown formatting) into clean LaTeX source.

    The solver writes a mix of:
      • Plain English text
      • LaTeX math ($...$, \\[...\\], \\(...\\), $$...$$, environments)
      • Markdown formatting (**bold**, *italic*, ``- list``, ``### heading``)
      • LaTeX commands (\\textbf{}, \\emph{}, \\quad, etc.)

    This function protects all math content, escapes problematic characters
    in the non-math text, converts Markdown → LaTeX, and restores the math.
    """
    if not text:
        return ""

    result = text

    # ── Pre-processing: normalise Unicode math & wrap bare math ──────
    result = _unicode_to_latex(result)

    # Escape underscores in reference-like identifiers (e.g.
    # "linalg_ii_ht2026.ch3.prop.2") BEFORE math wrapping, so they
    # aren't mistaken for subscripts.
    result = re.sub(
        r'([A-Za-z]\w*(?:_\w+)+(?:\.\w+)+)',
        lambda m: m.group(0).replace('_', r'\_'),
        result,
    )

    # Strip existing inline $…$ delimiters from solver output so that
    # _wrap_bare_math can handle all math uniformly (prevents mismatched
    # $ pairs and fragmented expressions like "$D_n$ = $A + Bn$").
    # Preserve display math (\[…\], $$…$$) and \(…\) from templates.
    _EARLY_SENTINEL = "\x01"

    # Phase 1: protect display math and \(…\) from stripping
    _early_store: list[str] = []

    def _early_protect(m: re.Match) -> str:
        idx = len(_early_store)
        _early_store.append(m.group(0))
        return f"{_EARLY_SENTINEL}E{idx}{_EARLY_SENTINEL}"

    result = re.sub(r"\\\[.*?\\\]", _early_protect, result, flags=re.DOTALL)
    result = re.sub(r"\$\$.*?\$\$", _early_protect, result, flags=re.DOTALL)
    result = re.sub(r"\\\(.*?\\\)", _early_protect, result, flags=re.DOTALL)
    result = re.sub(
        r"\\begin\{((?:v|b|p|V|B)?matrix|smallmatrix|array|"
        r"align\*?|aligned|equation\*?|gather\*?|gathered|"
        r"multline\*?|split|flalign\*?|cases)\}.*?\\end\{\1\}",
        _early_protect,
        result,
        flags=re.DOTALL,
    )

    # Phase 2: strip inline $…$ delimiters (keep content)
    result = re.sub(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)',
                    r' \1 ', result, flags=re.DOTALL)
    # Collapse multiple spaces and fix ^ / _ separated from their argument
    result = re.sub(r'  +', ' ', result)
    result = re.sub(r'([_^])\s+(?=\{|[A-Za-z0-9])', r'\1', result)

    # Phase 3: restore display math
    for idx, frag in enumerate(_early_store):
        result = result.replace(f"{_EARLY_SENTINEL}E{idx}{_EARLY_SENTINEL}", frag)

    result = _wrap_bare_math(result)
    result = _sanitize_non_ascii(result)

    math_store: list[str] = []

    def _protect(m: re.Match) -> str:
        idx = len(math_store)
        math_store.append(m.group(0))
        return f"{_MATH_SENTINEL}M{idx}{_MATH_SENTINEL}"

    # ── Protect delimited math (order matters — explicit delimiters first) ──

    # Display  \[ ... \]
    result = re.sub(r"\\\[.*?\\\]", _protect, result, flags=re.DOTALL)
    # Display  $$ ... $$
    result = re.sub(r"\$\$.*?\$\$", _protect, result, flags=re.DOTALL)
    # Inline  \( ... \)
    result = re.sub(r"\\\(.*?\\\)", _protect, result, flags=re.DOTALL)
    # Inline  $ ... $  (but not $$)
    result = re.sub(
        r"(?<!\$)\$(?!\$).*?(?<!\$)\$(?!\$)", _protect, result, flags=re.DOTALL
    )
    # Bare display environments (only those NOT already inside a delimiter)
    result = re.sub(
        r"\\begin\{((?:v|b|p|V|B)?matrix|smallmatrix|array|"
        r"align\*?|aligned|equation\*?|gather\*?|gathered|"
        r"multline\*?|split|flalign\*?|cases)\}.*?\\end\{\1\}",
        _protect,
        result,
        flags=re.DOTALL,
    )

    # ── Escape characters that are problematic in LaTeX text mode ──
    result = result.replace("%", r"\%")
    result = result.replace("#", r"\#")
    # & outside of math or tabular — escape only bare &
    result = re.sub(r"(?<!\\)&", r"\\&", result)

    # ── Convert Markdown formatting to LaTeX equivalents ──
    result = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", result)
    result = re.sub(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\\textit{\1}", result
    )

    # Markdown headers → LaTeX sections
    result = re.sub(
        r"(?:^|\n)###\s+(.+)", r"\n\\subsubsection*{\1}", result
    )
    result = re.sub(r"(?:^|\n)##\s+(.+)", r"\n\\subsection*{\1}", result)

    # Markdown bullet lists → itemize
    def _replace_list(m: re.Match) -> str:
        items = re.findall(r"^- (.+)$", m.group(0), re.MULTILINE)
        if not items:
            return m.group(0)
        inner = "\n".join(f"  \\item {it}" for it in items)
        return f"\n\\begin{{itemize}}[nosep]\n{inner}\n\\end{{itemize}}"

    result = re.sub(r"(?:^|\n)(- .+(?:\n- .+)*)", _replace_list, result)

    # Collapse excessive blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)

    # ── Restore protected math content ──
    for idx, frag in enumerate(math_store):
        result = result.replace(f"{_MATH_SENTINEL}M{idx}{_MATH_SENTINEL}", frag)

    return result.strip()


def _escape_tex(text: str) -> str:
    """Escape a plain-text string for safe inclusion in LaTeX (no math)."""
    for old, new in [
        ("\\", r"\textbackslash{}"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("$", r"\$"),
        ("%", r"\%"),
        ("#", r"\#"),
        ("&", r"\&"),
        ("_", r"\_"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]:
        text = text.replace(old, new)
    return text


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

    solution_files = sorted(work_dir.glob("solution_*.json"))
    if not solution_files:
        print(f"No solution files found in {work_dir}")
        return []

    for sf in solution_files:
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


# ── Verification helpers ─────────────────────────────────────────────


def verification_badge(verification: dict[str, Any] | None) -> dict[str, str]:
    """Return a badge colour name and label for the verification status."""
    if not verification:
        return {"colour": "gray", "label": "Not verified"}

    overall = verification.get("overall", {})
    status = overall.get("status", "unknown")
    confidence = overall.get("confidence", 0)
    pct = f"{confidence * 100:.0f}\\%"

    if status == "verified":
        return {"colour": "passgreen", "label": f"Verified ({pct})"}
    elif status == "flagged":
        return {"colour": "warnamber", "label": f"Flagged ({pct})"}
    elif status == "rejected":
        return {"colour": "failred", "label": f"Rejected ({pct})"}
    else:
        return {"colour": "gray", "label": status.title()}


def _check_colour(status: str) -> str:
    """Map a verification check status to a LaTeX colour name."""
    return {
        "PASS": "passgreen",
        "WARN": "warnamber",
        "FLAG": "warnamber",
    }.get(status, "failred")


# ── Preamble extraction (custom macros from course LaTeX source) ─────


def _extract_preamble_macros(work_dir: Path) -> str:
    """Try to find the course's .tex source and extract \\newcommand defs.

    Returns a string of LaTeX \\newcommand lines (empty if none found).
    """
    # Walk up from work_dir looking for .tex files with \\newcommand
    for parent in [work_dir, *work_dir.parents]:
        for tex in parent.glob("**/*.tex"):
            # Skip our own generated output files to prevent a
            # self-referencing loop (broken macros from a previous run
            # being re-extracted and re-inserted).
            if tex.name == "solutions.tex":
                continue
            try:
                src = tex.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            # Extract everything before \begin{document}
            doc_start = src.find(r"\begin{document}")
            if doc_start < 0:
                continue
            preamble = src[:doc_start]

            # Pull out \newcommand and \DeclareMathOperator lines
            # Use a pattern that handles one level of nested braces in the body,
            # e.g. \newcommand{\R}{\mathbb{R}} where the body contains inner {}.
            _BODY = r"\{(?:[^{}]|\{[^}]*\})*\}"  # body with one level of nesting
            cmds = re.findall(
                r"(\\(?:re)?newcommand\s*\{[^}]+\}(?:\[[^\]]*\])?" + _BODY + r")",
                preamble,
            )
            ops = re.findall(
                r"(\\DeclareMathOperator\*?\s*\{[^}]+\}" + _BODY + r")",
                preamble,
            )

            # Filter out non-math formatting macros that shouldn't be
            # re-defined (e.g. \headrulewidth, \footrulewidth, etc.)
            _SKIP = {
                r"\headrulewidth", r"\footrulewidth", r"\arraystretch",
                r"\baselinestretch", r"\parindent", r"\parskip",
            }
            cmds = [
                c for c in cmds
                if not any(s in c for s in _SKIP)
            ]

            if cmds or ops:
                return "\n".join(cmds + ops)

        # Stop at the repo root
        if (parent / ".git").exists():
            break

    return ""


# ── LaTeX template ───────────────────────────────────────────────────

LATEX_TEMPLATE = _JINJA_ENV.from_string(r"""\documentclass[11pt, a4paper]{article}

% ── Encoding & fonts ────────────────────────────────────
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{microtype}

% ── Mathematics ─────────────────────────────────────────
\usepackage{amsmath, amssymb, amsthm, amsfonts, mathtools}

% ── Layout ──────────────────────────────────────────────
\usepackage[margin=2.2cm]{geometry}
\usepackage{fancyhdr}
\usepackage{titlesec}
\usepackage[shortlabels]{enumitem}
\usepackage{parskip}

% ── Colours & boxes ─────────────────────────────────────
\usepackage[dvipsnames]{xcolor}
\usepackage[breakable, skins]{tcolorbox}
\usepackage{hyperref}

\definecolor{accent}{HTML}{1a3a5c}
\definecolor{accentlight}{HTML}{e8f0f8}
\definecolor{passgreen}{HTML}{1a7a3a}
\definecolor{passgreenlight}{HTML}{e6f5ec}
\definecolor{warnamber}{HTML}{8a6d00}
\definecolor{warnamberlight}{HTML}{fff8e1}
\definecolor{failred}{HTML}{a82020}
\definecolor{failredlight}{HTML}{fde8e8}
\definecolor{lightgrey}{HTML}{f5f5f5}
\definecolor{graylight}{HTML}{f0f0f0}

% ── tcolorbox styles ───────────────────────────────────
\newtcolorbox{problembox}{
  colback=accentlight, colframe=accent,
  fontupper=\itshape, breakable,
  left=6pt, right=6pt, top=6pt, bottom=6pt,
  boxrule=0.6pt,
}

\newtcolorbox{hintone}{
  colback=passgreenlight, colframe=passgreen, breakable,
  left=5pt, right=5pt, top=4pt, bottom=4pt, boxrule=0pt,
  borderline west={2.5pt}{0pt}{passgreen},
  title={\small\sffamily\bfseries\textsc{Tier 1 --- Conceptual Nudge}},
  fonttitle=\color{passgreen},
  attach boxed title to top left={yshift=-2mm, xshift=4mm},
  boxed title style={colback=passgreenlight, colframe=passgreenlight},
}

\newtcolorbox{hinttwo}{
  colback=warnamberlight, colframe=warnamber, breakable,
  left=5pt, right=5pt, top=4pt, bottom=4pt, boxrule=0pt,
  borderline west={2.5pt}{0pt}{warnamber},
  title={\small\sffamily\bfseries\textsc{Tier 2 --- The Tool}},
  fonttitle=\color{warnamber},
  attach boxed title to top left={yshift=-2mm, xshift=4mm},
  boxed title style={colback=warnamberlight, colframe=warnamberlight},
}

\newtcolorbox{hintthree}{
  colback=accentlight, colframe=accent, breakable,
  left=5pt, right=5pt, top=4pt, bottom=4pt, boxrule=0pt,
  borderline west={2.5pt}{0pt}{accent},
  title={\small\sffamily\bfseries\textsc{Tier 3 --- Outline}},
  fonttitle=\color{accent},
  attach boxed title to top left={yshift=-2mm, xshift=4mm},
  boxed title style={colback=accentlight, colframe=accentlight},
}

\newtcolorbox{insightbox}[1][]{
  colback=white, colframe=accent!40, breakable,
  left=5pt, right=5pt, top=4pt, bottom=4pt, boxrule=0.5pt,
  fonttitle=\small\sffamily\bfseries\color{accent},
  title={#1},
}

\newtcolorbox{postmortembox}{
  colback=lightgrey, colframe=gray!50, breakable,
  left=6pt, right=6pt, top=6pt, bottom=6pt, boxrule=0.5pt,
}

\newtcolorbox{stepbox}{
  colback=blue!2, colframe=accent, breakable,
  left=5pt, right=5pt, top=3pt, bottom=3pt,
  boxrule=0pt, borderline west={2.5pt}{0pt}{accent},
}

% ── Headers / footers ──────────────────────────────────
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\textcolor{accent}{\textit{<< title_esc >>}}}
\fancyhead[R]{\small\textcolor{accent}{\textit{<< subtitle_esc >>}}}
\fancyfoot[C]{\small\thepage}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\footrulewidth}{0pt}

% ── Section formatting ─────────────────────────────────
\titleformat{\section}
  {\Large\bfseries\color{accent}}{}{0pt}{}
  [\vspace{-0.4em}\textcolor{accent}{\rule{\textwidth}{0.8pt}}]
\titleformat{\subsection}
  {\large\bfseries\color{accent}}{}{0pt}{}
\titleformat{\subsubsection}
  {\normalsize\bfseries}{}{0pt}{}
\titlespacing*{\section}{0pt}{1.2em}{0.5em}
\titlespacing*{\subsection}{0pt}{0.8em}{0.3em}

% ── Custom macros (from course preamble) ───────────────
<< preamble_macros >>

% ── Common math shortcuts ──────────────────────────────
\providecommand{\R}{\mathbb{R}}
\providecommand{\N}{\mathbb{N}}
\providecommand{\Z}{\mathbb{Z}}
\providecommand{\Q}{\mathbb{Q}}
\providecommand{\C}{\mathbb{C}}
\providecommand{\F}{\mathbb{F}}
% Operator names (safe even if already defined)
\providecommand{\rank}{\operatorname{rank}}
\providecommand{\nullity}{\operatorname{nullity}}
\providecommand{\Span}{\operatorname{span}}
\renewcommand{\Im}{\operatorname{Im}}
\providecommand{\tr}{\operatorname{tr}}
\providecommand{\diag}{\operatorname{diag}}
\providecommand{\adj}{\operatorname{adj}}
\providecommand{\sgn}{\operatorname{sgn}}
\providecommand{\norm}[1]{\left\|#1\right\|}
\providecommand{\abs}[1]{\left|#1\right|}
\providecommand{\inner}[2]{\langle #1,\, #2 \rangle}

\begin{document}

% ═══════════════════ TITLE PAGE ═══════════════════════
\begin{titlepage}
\centering
\vspace*{3cm}

{\Huge\bfseries\color{accent} << title_esc >>}

\vspace{0.5cm}
{\color{accent}\rule{0.6\textwidth}{1.5pt}}
\vspace{0.5cm}

{\Large\color{gray} << subtitle_esc >>}

\vspace{2cm}

\begin{tabular}{r l}
\textcolor{accent}{\textbf{Problems}} & << num_problems >> \\[4pt]
\textcolor{accent}{\textbf{Verified}} & << num_verified >> passed, << num_flagged >> flagged, << num_rejected >> rejected \\[4pt]
\textcolor{accent}{\textbf{Generated by}} & MathPipe \\
\end{tabular}

\vfill
{\small\color{gray} Compiled << generated_date >>}
\end{titlepage}

% ═══════════════════ PROBLEMS ═════════════════════════
<% for entry in entries %>
<% set sol = entry.solution %>
<% set ver = entry.verification %>
<% set prob = entry.problem %>
<% set badge = entry.badge %>
<% set rec_id = sol.get("recommended_strategy", "s1") %>
<% set strategies = sol.get("strategies", []) %>

\clearpage
% ─── Problem << entry.num >> ───────────────────────────
\noindent
\colorbox{accent}{%
  \parbox{\dimexpr\textwidth-2\fboxsep}{%
    \color{white}\large\bfseries Problem << entry.num >>%
    \hfill
    \small\colorbox{<< badge.colour >>light}{\textcolor{<< badge.colour >>}{\textsf{<< badge.label >>}}}%
  }%
}
\vspace{0.4em}

% Problem statement
<% if prob %>
\begin{problembox}
<< t(prob.get("statement", sol.get("problem_statement", ""))) >>
\end{problembox}
<% else %>
\begin{problembox}
<< t(sol.get("problem_statement", "Problem statement not available.")) >>
\end{problembox}
<% endif %>

% Classification
<% set cls = sol.get("classification", {}) %>
<% if cls %>
\subsection*{Classification}

\textbf{<< cls.get("primary_archetype", "---") >>}%
<% if cls.get("secondary_archetypes") %>
\enspace$|$\enspace Also: << cls.get("secondary_archetypes", [])|join(", ") >>%
<% endif %>
<% if cls.get("confidence") is not none %>
\enspace$|$\enspace Confidence: << "%.0f"|format(cls.get("confidence", 0) * 100) >>\%%
<% endif %>

<% if cls.get("reasoning") %>

{\small\color{gray} << t(cls.get("reasoning", "")) >>}
<% endif %>
<% endif %>

% Hints
<% for strat in strategies %>
<% if strat.get("id") == rec_id and strat.get("hints") %>
<% set hints = strat["hints"] %>
\subsection*{Hints}

<% if hints.get("tier1_conceptual") %>
\begin{hintone}
<< t(hints["tier1_conceptual"]) >>
\end{hintone}
\vspace{0.3em}
<% endif %>
<% if hints.get("tier2_strategic") %>
\begin{hinttwo}
<< t(hints["tier2_strategic"]) >>
\end{hinttwo}
\vspace{0.3em}
<% endif %>
<% if hints.get("tier3_outline") %>
\begin{hintthree}
<< t(hints["tier3_outline"]) >>
\end{hintthree}
<% endif %>
<% endif %>
<% endfor %>

% Solution (recommended strategy)
<% for strat in strategies %>
<% if strat.get("id") == rec_id %>
\subsection*{Solution<% if strategies|length > 1 %>: << strat.get("approach_name", "Primary") >><% endif %>}

<% if strat.get("confidence") is not none %>
{\small\color{gray} Strategy confidence: << "%.0f"|format(strat.get("confidence", 0) * 100) >>\%}
\medskip
<% endif %>

<% if strat.get("solution") %>
<< t(strat["solution"]) >>
<% endif %>

% Step-by-step breakdown
<% if strat.get("solution_steps") %>
\subsubsection*{Step-by-step breakdown}
<% for step in strat["solution_steps"] %>

\begin{stepbox}
\textbf{\textcolor{accent}{Step << step.get("step", loop.index) >>.}} << t(step.get("action", "")) >>
<% if step.get("justification") %>

{\small\color{gray} << t(step["justification"]) >>}
<% endif %>
<% if step.get("kb_references") %>

{\footnotesize\color{gray!70} Refs: << step["kb_references"]|join(", ")|replace("_", "\\_") >>}
<% endif %>
\end{stepbox}
<% endfor %>
<% endif %>

<% endif %>
<% endfor %>

% Alternative strategies
<% if strategies|length > 1 %>
\subsection*{Alternative Approaches}
<% for strat in strategies %>
<% if strat.get("id") != rec_id %>
\subsubsection*{<< strat.get("approach_name", "Strategy " + strat.get("id", "?")) >><% if strat.get("confidence") is not none %> (<< "%.0f"|format(strat.get("confidence", 0) * 100) >>\%)<% endif %>}

<% if strat.get("solution") %>
<< t(strat["solution"]) >>
<% elif strat.get("attack_plan") %>
\begin{enumerate}[nosep]
<% for step in strat["attack_plan"] %>
  \item << t(step) >>
<% endfor %>
\end{enumerate}
<% endif %>
<% endif %>
<% endfor %>
<% endif %>

% Verification
<% if ver %>
<% set overall = ver.get("overall", {}) %>
\vspace{0.5em}
\noindent\textbf{Verification Report}
\vspace{0.2em}

\noindent
\begin{tabular}{@{}l r@{}}
<% set sc = ver.get("structural_check", {}).get("status", "---") %>
Structural check & \textcolor{<< check_colour(sc) >>}{\textsf{<< sc >>}} \\
<% set ac = ver.get("adversarial_check", {}).get("status", "---") %>
Adversarial check & \textcolor{<< check_colour(ac) >>}{\textsf{<< ac >>}} \\
<% set cc = ver.get("consistency_check", {}).get("status", "---") %>
Consistency check & \textcolor{<< check_colour(cc) >>}{\textsf{<< cc >>}} \\
\end{tabular}

<% if overall.get("summary") %>
\smallskip
{\small << t(overall["summary"]) >>}
<% endif %>
<% if overall.get("human_review_required") and overall.get("human_review_reason") %>

{\small\color{warnamber} $\triangle$ << t(overall["human_review_reason"]) >>}
<% endif %>
<% endif %>

% Postmortem
<% set pm = sol.get("postmortem", {}) %>
<% if pm %>
\vspace{0.5em}
\begin{postmortembox}
{\large\bfseries\color{gray!80!black} Postmortem}
\vspace{0.3em}

<% if pm.get("key_insight") %>
\begin{insightbox}[Key Insight]
<< t(pm["key_insight"]) >>
\end{insightbox}
<% endif %>

<% if pm.get("transferable_technique") %>
\begin{insightbox}[Transferable Technique]
<< t(pm["transferable_technique"]) >>
\end{insightbox}
<% endif %>

<% if pm.get("common_errors") %>
\vspace{0.3em}
\textbf{Common Errors}
\begin{itemize}[nosep]
<% for err in pm["common_errors"] %>
  \item \textcolor{failred}{$\bullet$} << t(err) >>
<% endfor %>
\end{itemize}
<% endif %>

<% if pm.get("deeper_connections") %>
\vspace{0.3em}
\textbf{Deeper Connections}

<< t(pm["deeper_connections"]) >>
<% endif %>

<% if pm.get("variant_problems") %>
\vspace{0.3em}
\textbf{Variant Problems}
\begin{itemize}[nosep]
<% for v in pm["variant_problems"] %>
  \item << t(v) >>
<% endfor %>
\end{itemize}
<% endif %>

\end{postmortembox}
<% endif %>

<% endfor %>

\end{document}
""")


# ── Title inference ──────────────────────────────────────────────────


def _prettify_course_id(course_id: str) -> str:
    """Turn a course_id like 'linalg_ii_ht2026' into 'Linear Algebra II — HT 2026'."""
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
        term_match = re.match(r"^(ht|mt|tt)(\d{4})$", p)
        if term_match:
            term_part = f"{_TERMS[term_match.group(1)]} {term_match.group(2)}"
            continue
        if p in _ROMAN:
            course_parts.append(p.upper())
            continue
        if p in _ABBREVS:
            course_parts.append(_ABBREVS[p])
            continue
        if re.match(r"^\d{4}$", p):
            term_part = term_part or p
            continue
        course_parts.append(p.capitalize())

    name = " ".join(course_parts)
    if term_part:
        name += f" --- {term_part}"
    return name


def _infer_title_from_config(work_dir: Path) -> str | None:
    """Try to find the course config and return the course_name."""
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
        if (parent / ".git").exists():
            break
    return None


# ── LaTeX compiler ───────────────────────────────────────────────────


def _find_latex_compiler() -> str | None:
    """Return the path to a usable LaTeX compiler, or None."""
    for cmd in ("latexmk", "pdflatex", "xelatex", "lualatex"):
        path = shutil.which(cmd)
        if path:
            return cmd
    return None


def _compile_tex(tex_path: Path, output_dir: Path) -> Path:
    """Compile a .tex file to PDF and return the output PDF path."""
    compiler = _find_latex_compiler()
    if compiler is None:
        raise RuntimeError(
            "No LaTeX compiler found. Install a TeX distribution:\n"
            "  macOS:  brew install --cask mactex   (or basictex)\n"
            "  Linux:  sudo apt install texlive-full\n"
            "  Windows: install MiKTeX from https://miktex.org\n\n"
            f"The .tex source has been written to: {tex_path}"
        )

    if compiler == "latexmk":
        cmd = [
            "latexmk", "-pdf", "-interaction=nonstopmode",
            "-output-directory=" + str(output_dir),
            str(tex_path),
        ]
    else:
        cmd = [
            compiler, "-interaction=nonstopmode",
            "-output-directory=" + str(output_dir),
            str(tex_path),
        ]

    # Run twice for cross-references (latexmk handles this itself)
    passes = 1 if compiler == "latexmk" else 2

    for i in range(passes):
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 and i == passes - 1:
            # Extract the most relevant error lines from the log
            log_file = output_dir / tex_path.with_suffix(".log").name
            error_lines = ""
            if log_file.exists():
                log = log_file.read_text(errors="replace")
                # Find lines starting with "!" (LaTeX errors)
                errors = [
                    ln for ln in log.splitlines() if ln.startswith("!")
                ]
                if errors:
                    error_lines = "\n  ".join(errors[:10])

            msg = f"LaTeX compilation failed ({compiler})."
            if error_lines:
                msg += f"\n  {error_lines}"
            msg += f"\n\nTeX source: {tex_path}"
            msg += f"\nFull log:   {log_file}"
            print(msg, file=sys.stderr)
            # Don't raise — we still wrote the .tex file

    pdf_name = tex_path.with_suffix(".pdf").name
    return output_dir / pdf_name


# ── Main compile function ────────────────────────────────────────────


def compile_pdf(
    work_dir: Path,
    output_path: Path | None = None,
    title: str | None = None,
    subtitle: str | None = None,
) -> Path:
    """Compile solution files from work_dir into a PDF via LaTeX.

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

    # Infer title
    parts = work_dir.resolve().parts
    if not title:
        title = _infer_title_from_config(work_dir)
        if not title and len(parts) >= 2:
            title = _prettify_course_id(parts[-2])
        elif not title:
            title = "Solutions"

    if not subtitle:
        if len(parts) >= 2:
            sheet_dir = parts[-1]
            sheet_match = re.search(r"(\d+)", sheet_dir)
            if sheet_match:
                subtitle = f"Problem Sheet {sheet_match.group(1)}"
            else:
                subtitle = sheet_dir.replace("_", " ").title()
        else:
            subtitle = f"{len(entries)} Problems"

    # Count verification stats
    n_verified = n_flagged = n_rejected = 0
    for e in entries:
        v = e.get("verification")
        if v:
            st = v.get("overall", {}).get("status", "")
            if st == "verified":
                n_verified += 1
            elif st == "flagged":
                n_flagged += 1
            elif st == "rejected":
                n_rejected += 1

    # Extract custom macros from course preamble
    preamble_macros = _extract_preamble_macros(work_dir)

    # Render the LaTeX template
    tex_source = LATEX_TEMPLATE.render(
        title_esc=_escape_tex(title),
        subtitle_esc=_escape_tex(subtitle),
        num_problems=len(entries),
        num_verified=n_verified,
        num_flagged=n_flagged,
        num_rejected=n_rejected,
        generated_date=date.today().strftime("%d %B %Y"),
        entries=entries,
        preamble_macros=preamble_macros,
        t=text_to_latex,
        check_colour=_check_colour,
    )

    # Write .tex file alongside the solutions
    tex_path = work_dir / "solutions.tex"
    tex_path.write_text(tex_source, encoding="utf-8")
    print(f"TeX source written: {tex_path}")

    # Compile to PDF
    if output_path is None:
        output_path = work_dir / "solutions.pdf"

    try:
        pdf_out = _compile_tex(tex_path, work_dir)
        # Move to the desired output path if different
        if pdf_out.resolve() != output_path.resolve():
            shutil.move(str(pdf_out), str(output_path))
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        # Even if compilation fails, the .tex file is available
        return tex_path

    # Clean up LaTeX auxiliary files
    for ext in (".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".synctex.gz"):
        aux = work_dir / f"solutions{ext}"
        if aux.exists():
            aux.unlink()

    return output_path


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile MathPipe solution files into a formatted PDF via LaTeX.",
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
        if out.suffix == ".pdf" and out.exists():
            size_kb = out.stat().st_size / 1024
            print(f"PDF compiled: {out} ({size_kb:.0f} KB)")
        elif out.suffix == ".tex":
            print(f"TeX source available at: {out}")
            print("Compile manually: pdflatex solutions.tex")
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
