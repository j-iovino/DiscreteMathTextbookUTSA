#!/usr/bin/env python3
"""
texwrap.py — Semantic line wrapper for LaTeX source files.

Wraps prose lines at semantic boundaries, enforcing an upper limit on
*content* width (--cols, default 255) measured with the line's leading
indentation removed — so the limit is independent of nesting depth.

texwrap changes only WHERE line breaks fall.  It preserves indentation
and blank lines verbatim, leaving all whitespace normalization (indent
depth, blank-line policy, trailing whitespace) to latexindent.  Because
its break decisions ignore leading whitespace, wrapping composes with
latexindent into an idempotent `reflow` (wrap → indent).

Break rules apply ONLY in text mode.  Inline math ($…$, $$…$$, \\(…\\),
\\[…\\]) and comments (% to end of line) are never broken — inside a
formula a ";" or ":" separates arguments (e.g. $H(p, q; c, d)$) and must
not force a line break.  The mandatory clause/sentence breaks (rules 1–2)
are likewise suppressed inside a braced macro argument — the ";" in
\\subjclass{Primary; Secondary} or the ":" in \\title{Foo: Bar} is
punctuation *within* an argument, not a prose clause boundary (brace
nesting is tracked per line).  Break-point rules (in order of priority):

  1. MANDATORY — Sentence end (". ", "? ", "! ", etc.): always ends a
     file line, even if the sentence is short.
  2. MANDATORY — Semicolon / colon ("; ", ": "): always ends a file
     line (splits compound sentences).
  3. CONDITIONAL — Applied only when a line produced by rules 1–2 still
     exceeds --cols:
     3.1  Inline-math span boundary (break *before* the opening "$" or
          *after* the closing "$"), or a parenthetical / em-dash boundary.
     3.2  Comma ", " (lower priority).
     3.3  Word boundary (space).
     3.4  Semicolon *inside* a formula (allowed for very long formulas,
          lowest priority — normally never used).
     3.5  Hard cut at column 80 (last resort).

For rule-3 breaks, the scanner looks from column 50 forward to --cols,
picking the *first* (leftmost) candidate at the *highest* priority
level.  Lower-priority rules are used only when all higher-priority
rules find no candidate.

List items use a *standalone* \\item: any body content on the same line as
\\item (or \\item[label]) is dropped to the next line, so \\item stands
alone and its body follows below.  A bare \\item / \\item[label] is left as
is.

Content inside display-math regions (\\[ … \\], equation, align, …),
verbatim-style environments, and pure comment lines is never modified.
Indentation and blank lines are never changed (latexindent owns them).

Usage:
    python3 texwrap.py [--check] [--cols N] file1.tex [file2.tex …]

    --check   Dry run: report files that would change, exit 1 if any.
    --cols N  Content-width limit, excluding indentation (default: 255).
"""

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

DEFAULT_COLS: int = 255
SCAN_START: int = 50  # start scanning for rule-3 breaks here
HARD_CUT: int = 80  # absolute last-resort break column

# Bodies of these environments are never touched (treated as verbatim)
VERBATIM_ENVS: frozenset = frozenset(
    {
        "verbatim",
        "Verbatim",
        "lstlisting",
        "minted",
        "filecontents",
        "comment",
        "BVerbatim",
        "SaveVerbatim",
    }
)

# Display-math environments: content is not prose, skip line-break insertion
MATH_ENVS: frozenset = frozenset(
    {
        "equation",
        "equation*",
        "align",
        "align*",
        "gather",
        "gather*",
        "multline",
        "multline*",
        "eqnarray",
        "eqnarray*",
        "split",
        "aligned",
        "alignedat",
        "gathered",
        "array",
        "matrix",
        "pmatrix",
        "bmatrix",
        "vmatrix",
        "Vmatrix",
        "Bmatrix",
        "cases",
        "subequations",
        "tikzpicture",
        "tabular",
        "tabular*",
        "tabularx",
        "longtable",
    }
)

PROTECTED_ENVS: frozenset = VERBATIM_ENVS | MATH_ENVS

# ---------------------------------------------------------------------------
# Sentence-end detection
# ---------------------------------------------------------------------------

_ABBREV_RE = re.compile(
    r"(?:"
    r"[A-Z]"
    r"|[Ss]ect|[Ff]ig|[Tt]hm|[Pp]rop"
    r"|[Dd]ef|[Cc]or|[Ll]em|[Ee]q"
    r"|[Cc]f|vs|[Ee]d|[Tt]rans"
    r"|[Vv]ol|[Nn]o|[Pp]p|[Pp]"
    r"|i\.e|e\.g|viz|etc|et\sal|[Aa]pprox"
    r")\.$"
)


# ---------------------------------------------------------------------------
# Math / comment region scan
# ---------------------------------------------------------------------------

# Region codes returned by _scan_regions
_R_TEXT = 0
_R_MATH = 1
_R_COMMENT = 2


def _scan_regions(s: str, start_in_math: bool = False) -> list[int]:
    """Classify every character of *s* as text / inline-math / comment.

    Returns a list of region codes (_R_TEXT, _R_MATH, _R_COMMENT), one per
    character.  Tracks inline math opened *within* the line — ``$…$``,
    ``$$…$$``, ``\\(…\\)``, ``\\[…\\]`` — backslash escapes (so ``\\$`` and
    ``\\%`` are literal, not delimiters), and ``%`` comments (to end of
    line).  This lets the break rules avoid firing inside a formula (where,
    e.g., ``;`` separates arguments) or inside a comment.

    Display-math *environments* and standalone ``\\[`` lines are handled at
    the file level (whole lines are skipped), so this per-line scan sees
    only inline math in practice; ``start_in_math`` exists for completeness.
    """
    n = len(s)
    region = [_R_TEXT] * n
    in_math = start_in_math
    in_comment = False
    i = 0
    while i < n:
        c = s[i]
        if in_comment:
            region[i] = _R_COMMENT
            i += 1
            continue
        if c == "\\":
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt in "([":  # \( or \[ opens math
                in_math = True
                region[i] = _R_MATH
                if i + 1 < n:
                    region[i + 1] = _R_MATH
                i += 2
                continue
            if nxt in ")]":  # \) or \] closes math
                region[i] = _R_MATH
                if i + 1 < n:
                    region[i + 1] = _R_MATH
                in_math = False
                i += 2
                continue
            # escaped char / control word: not a delimiter, keep current state
            cur = _R_MATH if in_math else _R_TEXT
            region[i] = cur
            if i + 1 < n:
                region[i + 1] = cur
            i += 2 if nxt else 1
            continue
        if c == "%":  # comment to end of line (even inside math)
            in_comment = True
            region[i] = _R_COMMENT
            i += 1
            continue
        if c == "$":  # $ …$  or  $$ …$$
            if i + 1 < n and s[i + 1] == "$":
                region[i] = region[i + 1] = _R_MATH
                in_math = not in_math
                i += 2
                continue
            region[i] = _R_MATH
            in_math = not in_math
            i += 1
            continue
        region[i] = _R_MATH if in_math else _R_TEXT
        i += 1
    return region


def _brace_depth_map(s: str, region: list[int]) -> list[int]:
    """Return the brace-group nesting depth at each character of *s*.

    Counts unescaped ``{`` / ``}`` outside comments (``\\{`` and ``\\}`` are
    literal, not delimiters; braces inside a comment are ignored).  For an
    opening ``{`` the recorded depth is the level *outside* the group; for a
    closing ``}`` it is the level *after* closing — so a character strictly
    inside a group has depth ≥ 1.

    Used to keep the mandatory clause/sentence breaks (rules 1–2) out of
    braced macro arguments: a ``;`` in ``\\subjclass{Primary; Secondary}`` or
    a ``:`` in ``\\title{Foo: Bar}`` is punctuation *inside* an argument, not a
    prose clause boundary, and must not force a line break.  Tracking is
    per-line (a group opened on an earlier source line is not carried over).
    """
    n = len(s)
    depth = [0] * n
    d = 0
    i = 0
    while i < n:
        if region[i] == _R_COMMENT:
            depth[i] = d
            i += 1
            continue
        c = s[i]
        if c == "\\":  # escape: this char and the next are literal
            depth[i] = d
            if i + 1 < n:
                depth[i + 1] = d
            i += 2
            continue
        if c == "{":
            depth[i] = d
            d += 1
            i += 1
            continue
        if c == "}":
            d = max(0, d - 1)
            depth[i] = d
            i += 1
            continue
        depth[i] = d
        i += 1
    return depth


def _depth_at(depth: list[int], idx: int, n: int) -> int:
    """Brace depth at *idx*; a break position at end-of-line (idx ≥ n) counts
    as top level (0) — there is no dangling open group to protect."""
    return depth[idx] if idx < n else 0


def _is_sentence_end(text: str, i: int) -> bool:
    """Return True if text[i] is sentence-ending punctuation before a space.

    Also returns True when the punctuation is followed by ``}`` then
    a space (common in LaTeX footnotes like ``...theory.}\n``), or when
    it sits at the very end of the string (end of line).
    """
    if text[i] not in ".?!":
        return False
    # Allow: punct + space, punct + "}" + space, punct at EOL,
    # punct + "}" at EOL.
    after = i + 1
    # Skip optional closing braces / brackets
    while after < len(text) and text[after] in "}]":
        after += 1
    # Now after points at first char after the punct+closing group.
    # Accept if followed by space, newline, or at end-of-string.
    if after >= len(text):
        return True  # punctuation at end of line
    if text[after] not in (" ", "\n"):
        return False
    if text[i] == ".":
        start = i - 1
        while start >= 0 and (text[start].isalnum() or text[start] == "."):
            start -= 1
        word = text[start + 1 : i + 1]
        if _ABBREV_RE.match(word):
            return False
        if word.replace(".", "").isdigit():
            return False
    return True


def _break_after_sentence_end(text: str, i: int) -> int:
    """Given that text[i] is sentence-ending punctuation, return the index
    of the first character of the next line (skip closing braces and the
    following space)."""
    after = i + 1
    while after < len(text) and text[after] in "}]":
        after += 1
    # Skip the space
    if after < len(text) and text[after] == " ":
        after += 1
    return after


# ---------------------------------------------------------------------------
# Em-dash / parenthesis detection helpers
# ---------------------------------------------------------------------------

_EM_DASH = "\u2014"


def _is_emdash_boundary(line: str, i: int) -> int | None:
    """If position *i* starts an em-dash pattern, return the index of the
    first character after the dash+space (i.e. the continuation position).
    Recognised patterns (best-effort):
      — (Unicode em-dash)
      --- (LaTeX triple-dash)
      -- (surrounded by spaces — treated as em-dash)
    Returns None if no match."""
    n = len(line)
    # Unicode em-dash: "—" possibly followed/preceded by space
    if line[i] == _EM_DASH:
        end = i + 1
        if end < n and line[end] == " ":
            end += 1
        return end
    # LaTeX ---
    if line[i] == "-" and i + 2 < n and line[i + 1] == "-" and line[i + 2] == "-":
        end = i + 3
        if end < n and line[end] == " ":
            end += 1
        return end
    # Spaced -- (em-dash stand-in): " -- "
    if (
        line[i] == "-"
        and i + 1 < n
        and line[i + 1] == "-"
        and (i + 2 >= n or line[i + 2] != "-")  # not ---
        and i > 0
        and line[i - 1] == " "
    ):
        end = i + 2
        if end < n and line[end] == " ":
            end += 1
        return end
    return None


def _is_open_paren_boundary(line: str, i: int) -> int | None:
    """If line[i] == '(' and it looks like it opens a parenthetical clause,
    return *i* (break so the paren starts the new line).  None otherwise."""
    if line[i] != "(":
        return None
    # Must be preceded by a space (or start of line after indent)
    if i > 0 and line[i - 1] != " ":
        return None
    return i


def _is_close_paren_boundary(line: str, i: int) -> int | None:
    """If line[i] == ')' followed by a space, return the index after the
    space (the continuation).  None otherwise."""
    if line[i] != ")":
        return None
    n = len(line)
    after = i + 1
    # skip optional punctuation after )
    while after < n and line[after] in ".,;:":
        after += 1
    if after < n and line[after] == " ":
        return after + 1
    return None


# ---------------------------------------------------------------------------
# Phase 1: mandatory breaks (rules 1 & 2)
# ---------------------------------------------------------------------------


def _mandatory_split(line: str) -> list[str]:
    """Split *line* at every sentence end (rule 1) and every semicolon /
    colon (rule 2).  Returns a list of sub-lines (without trailing spaces).
    """
    indent = line[: len(line) - len(line.lstrip())]
    pieces: list[str] = []
    start = 0
    i = 0
    n = len(line)
    # Only break in text mode: never inside inline math or a comment.
    region = _scan_regions(line)
    # …and never at a boundary that lands inside a braced macro argument.
    depth = _brace_depth_map(line, region)

    while i < n:
        # Rule 1: sentence end (text mode, at top level only)
        if region[i] == _R_TEXT and _is_sentence_end(line, i):
            bp = _break_after_sentence_end(line, i)
            # Suppress if the continuation is still inside a brace group — the
            # sentence ends *within* a macro argument, not in running text.
            if _depth_at(depth, bp, n) != 0:
                i += 1
                continue
            pieces.append(line[start:bp].rstrip())
            start = bp
            # Continuation gets the original indent
            if start < n and not line[start:].startswith(indent.lstrip() or " "):
                pass  # we prepend indent below
            i = start
            continue

        # Rule 2: semicolon or colon (text mode, at top level only)
        if region[i] == _R_TEXT and line[i] in ";:" and i + 1 < n and line[i + 1] == " ":
            if line[i] == ":":
                # Exclude := and ::
                nxt = line[i + 2] if i + 2 < n else ""
                if nxt in ("=", ":"):
                    i += 1
                    continue
            # Suppress a clause break inside a braced argument, e.g. the ";" in
            # \subjclass{Primary; Secondary} or the ":" in \title{Foo: Bar}.
            if depth[i] != 0:
                i += 1
                continue
            bp = i + 2
            pieces.append(line[start:bp].rstrip())
            start = bp
            i = start
            continue

        i += 1

    if start < n:
        pieces.append(line[start:].rstrip())

    # Re-apply indent to continuation lines
    result: list[str] = []
    for idx, p in enumerate(pieces):
        if idx == 0:
            result.append(p)
        else:
            stripped = p.lstrip()
            if stripped:
                result.append(indent + stripped)
            # skip empty pieces
    return result


# ---------------------------------------------------------------------------
# Phase 2: conditional breaks (rule 3) — only for lines > max_cols
# ---------------------------------------------------------------------------

# Priority levels for rule-3 candidates (lower number = preferred)
_R3_MATH_BOUNDARY = 1  # break just before / after an inline-math span
_R3_PAREN = 1  # 3.1 parentheses
_R3_EMDASH = 1  # 3.2 em-dashes (same priority as parens)
_R3_COMMA = 2  # 3.3.1
_R3_SPACE = 3  # 3.3.2
_R3_MATH_SEMI = 4  # semicolon *inside* math — allowed, but lowest priority
# 3.3.4 hard cut is handled separately


def _collect_rule3_candidates(
    line: str, lo: int, hi: int, region: list[int]
) -> list[tuple[int, int]]:
    """Collect rule-3 break candidates in line[lo:hi].

    Returns (priority, break_position) pairs where break_position is the
    index of the first character of the continuation line.
    Scans left-to-right from *lo* to *hi*.

    Math-aware: breaks are never placed inside a formula, except a
    semicolon (a common argument separator) which is offered at the lowest
    priority for very long formulas.  The preferred candidates near a
    formula are the span boundaries — break *before* the opening ``$`` or
    *after* the closing ``$``.
    """
    hi = min(hi, len(line))
    cands: list[tuple[int, int]] = []

    i = lo
    while i < hi:
        r = region[i]

        # Math-span boundaries (preferred: break at the edge, not inside)
        if i > 0 and r == _R_MATH and region[i - 1] != _R_MATH and line[i - 1] == " ":
            cands.append((_R3_MATH_BOUNDARY, i))  # before opening delimiter
        if i > 0 and r != _R_MATH and region[i - 1] == _R_MATH and line[i] == " ":
            cands.append((_R3_MATH_BOUNDARY, i + 1))  # after closing delimiter

        if r == _R_MATH:
            # Inside a formula: only a "; " is a (very low priority) candidate.
            if line[i] == ";" and i + 1 < len(line) and line[i + 1] == " ":
                cands.append((_R3_MATH_SEMI, i + 2))
            i += 1
            continue
        if r == _R_COMMENT:
            i += 1  # never break inside a comment
            continue

        # ── text mode (r == _R_TEXT) ──────────────────────────────────
        # 3.2 Em-dash
        em = _is_emdash_boundary(line, i)
        if em is not None:
            # Break before the dash (new line starts at dash)
            # If preceded by space, break at the space
            bp = i
            if i > 0 and line[i - 1] == " ":
                bp = i  # new line starts at the dash
            cands.append((_R3_EMDASH, bp))
            i = em
            continue

        # 3.1 Open paren
        op = _is_open_paren_boundary(line, i)
        if op is not None:
            cands.append((_R3_PAREN, op))
            i += 1
            continue

        # 3.1 Close paren
        cp = _is_close_paren_boundary(line, i)
        if cp is not None:
            cands.append((_R3_PAREN, cp))
            i += 1
            continue

        # 3.3.1 Comma
        if line[i] == "," and i + 1 < len(line) and line[i + 1] == " ":
            cands.append((_R3_COMMA, i + 2))

        # 3.3.2 Word boundary
        elif line[i] == " ":
            cands.append((_R3_SPACE, i + 1))

        i += 1

    return cands


def _break_long_line(line: str, max_cols: int) -> list[str]:
    """Apply rule-3 breaking to a single line that exceeds *max_cols*."""
    indent = line[: len(line) - len(line.lstrip())]
    pieces: list[str] = []
    cur = line

    while len(cur) > max_cols:
        lo = SCAN_START
        hi = max_cols
        cands = _collect_rule3_candidates(cur, lo, hi, _scan_regions(cur))

        if cands:
            # Pick the first (leftmost) candidate at the best (lowest)
            # priority level.
            best_prio = min(p for p, _ in cands)
            # Among best-priority, pick leftmost
            bp = min(pos for p, pos in cands if p == best_prio)
        else:
            # 3.3.3 Hard cut
            bp = HARD_CUT

        if bp >= len(cur):
            break

        pieces.append(cur[:bp].rstrip())
        rest = cur[bp:].lstrip(" ") if bp > 0 and cur[bp - 1] == " " else cur[bp:]
        cur = indent + rest if rest else ""

    if cur:
        pieces.append(cur)
    return pieces


# ---------------------------------------------------------------------------
# Top-level line wrapper
# ---------------------------------------------------------------------------


def _wrap_line(line: str, max_cols: int) -> list[str]:
    """Wrap one prose line using the two-phase strategy.

    Width limits are measured against the *de-indented* content: the line
    is stripped of its leading whitespace, wrapped as if it began at column
    0, and the original indentation is restored on every resulting line.
    Wrapping decisions are therefore independent of indentation depth, so
    re-indentation (by latexindent) can never move a break — the property
    that makes `reflow` idempotent.
    """
    stripped = line.lstrip(" \t")
    indent = line[: len(line) - len(stripped)]

    # Phase 1: mandatory splits (sentence ends, semicolons, colons),
    # on the de-indented content.
    segments = _mandatory_split(stripped)

    # Phase 2: break any segment whose content still exceeds max_cols.
    pieces: list[str] = []
    for seg in segments:
        if len(seg) > max_cols:
            pieces.extend(_break_long_line(seg, max_cols))
        else:
            pieces.append(seg)

    # Restore the original indentation on every line.
    return [indent + p for p in pieces]


# ---------------------------------------------------------------------------
# Environment / display-math state tracking
# ---------------------------------------------------------------------------

_BEGIN_RE = re.compile(r"\\begin\{([^}]+)\}")
_END_RE = re.compile(r"\\end\{([^}]+)\}")
_DISPLAY_OPEN = re.compile(r"^\s*\\\[")
_DISPLAY_CLOSE = re.compile(r"^\s*\\\]")
_COMMENT_LINE = re.compile(r"^\s*%")

# An \item (optionally \item[label]) carrying inline body content on the same
# line.  House style is a *standalone* \item: the body drops to the next line
# (and latexindent then indents it one level).  A bare \item / \item[label]
# with nothing after it does not match and is left alone.
_ITEM_INLINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)\\item(?P<opt>\[[^\]]*\])?[ \t]+(?P<rest>\S.*)$"
)


# ---------------------------------------------------------------------------
# File processor
# ---------------------------------------------------------------------------


def process(text: str, max_cols: int) -> str:
    """Return reformatted content for one .tex file."""
    env_stack: list[str] = []
    in_display_math = False
    out: list[str] = []

    for raw in text.splitlines():
        line = raw.rstrip()

        # ── Blank / whitespace-only lines ────────────────────────────
        if line == "" or line.isspace():
            # Preserve blank lines verbatim; latexindent owns blank-line policy.
            out.append("")
            continue

        if _DISPLAY_OPEN.match(line):
            in_display_math = True
            out.append(line)
            continue

        if in_display_math:
            out.append(line)
            if _DISPLAY_CLOSE.match(line):
                in_display_math = False
            continue

        for m in _BEGIN_RE.finditer(line):
            env_stack.append(m.group(1))

        in_protected = any(e in PROTECTED_ENVS for e in env_stack)

        for m in _END_RE.finditer(line):
            env = m.group(1)
            for i in range(len(env_stack) - 1, -1, -1):
                if env_stack[i] == env:
                    del env_stack[i]
                    break

        if in_protected or _COMMENT_LINE.match(line):
            out.append(line)
        else:
            item = _ITEM_INLINE_RE.match(line)
            if item:
                # Standalone \item: keep \item (with any [label]) on its own
                # line, drop the body to the next line (indented by latexindent).
                indent = item.group("indent")
                out.append(indent + "\\item" + (item.group("opt") or ""))
                out.extend(_wrap_line(indent + item.group("rest"), max_cols))
            else:
                out.extend(_wrap_line(line, max_cols))

    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("files", nargs="+", metavar="FILE")
    ap.add_argument(
        "--check",
        action="store_true",
        help="Dry run: report files that need changes, exit 1 if any.",
    )
    ap.add_argument(
        "--cols",
        type=int,
        default=DEFAULT_COLS,
        metavar="N",
        help=f"Target column width (default: {DEFAULT_COLS}).",
    )
    args = ap.parse_args()

    changed: list[str] = []
    for path_str in args.files:
        path = Path(path_str)
        if not path.exists():
            print(f"texwrap: {path}: file not found", file=sys.stderr)
            continue
        original = path.read_text(encoding="utf-8")
        result = process(original, args.cols)
        if result != original:
            changed.append(str(path))
            if not args.check:
                path.write_text(result, encoding="utf-8")
                print(f"texwrap: formatted  {path}")
        else:
            if not args.check:
                print(f"texwrap: unchanged   {path}")

    if args.check:
        if changed:
            print("texwrap: the following files need formatting:")
            for f in changed:
                print(f"  {f}")
            return 1
        print("texwrap: all files are properly formatted")

    return 0


if __name__ == "__main__":
    sys.exit(main())
