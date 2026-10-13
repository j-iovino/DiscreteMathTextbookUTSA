#!/usr/bin/env python3
"""
texsep.py — Normalize sectioning banners in LaTeX source (STYLE.md §5).

Places, and keeps consistent, a three-line comment "indentator" on the
lines immediately above each sectioning command.  The banner is an ASCII
drawing of a vertical bar plus a horizontal arm whose length is the
nesting depth:

    %#
    %## SECTION: Harmonic conjugates
    %#

  - line 1 and line 3 are just "%#" (the bar);
  - line 2 is "%" + "#"×depth + " ENVNAME: Title".

The environment name is upper-cased; the DOCUMENT banner takes its title
from the document's \title{…}.

Depth is relative to the document: `document` is 1, the shallowest
sectioning command present is 2, the next 3, and so on (so in an article
`section`=2, `subsection`=3; in a book `chapter`=2, `section`=3).  The arm
therefore grows to the right with depth and lines up within a level — a
left-anchored outline you can read with `grep '^%#'`.

The three-line block stands out from ordinary (possibly `%%`-prefixed)
commented-out code, and is chosen by the command name alone, so it needs no
manual sizing.  Idempotent: an existing banner directly above a command —
in this format OR the older box/rule formats — is replaced (not stacked),
and exactly one blank line is ensured above it.  Banners are ordinary
comments, so texwrap and latexindent never touch them.

Usage:
    python3 texsep.py [--check] file1.tex [file2.tex …]

    --check   Dry run: report files that would change, exit 1 if any.
"""

import argparse
import re
import sys
from pathlib import Path

# Sectioning command bodies are not banner-ized inside these environments.
VERBATIM_ENVS: frozenset = frozenset(
    {
        "verbatim",
        "verbatim*",
        "Verbatim",
        "lstlisting",
        "minted",
        "filecontents",
        "filecontents*",
        "comment",
        "BVerbatim",
        "SaveVerbatim",
    }
)

# LaTeX sectioning hierarchy (shallow -> deep); used to compute relative depth.
_LEVEL: dict = {
    "part": 0,
    "chapter": 1,
    "section": 2,
    "subsection": 3,
    "subsubsection": 4,
}

_BEGIN_RE = re.compile(r"\\begin\{([^}]+)\}")
_END_RE = re.compile(r"\\end\{([^}]+)\}")

# A sectioning command as the first token on the line: optional indent,
# \cmd, optional *, optional [short], then the opening { of the title.
# (Longest names first so \subsubsection is not mistaken for \section.)
_SEC_RE = re.compile(
    r"^(?P<indent>[ \t]*)"
    r"\\(?P<cmd>subsubsection|subsection|section|chapter|part)"
    r"\*?\s*(?:\[[^\]]*\])?\s*\{"
)
_DOC_RE = re.compile(r"^[ \t]*\\begin\{document\}")
_TITLE_RE = re.compile(r"^\s*\\title\s*(?:\[[^\]]*\])?\s*\{")  # \title{…} for DOCUMENT

# Recognizers used to strip an existing banner from the emitted output.
_NEW_BAR = re.compile(r"^%#[ \t]*$")  # "%#" bar line (top / bottom)
_NEW_MID = re.compile(r"^%#+ \S")  # "%##… envname: title" middle line
# …and the older formats, so a format change migrates cleanly:
_OLD_BOX_RULE = re.compile(r"^%{4,}\s*$")  # full %%%… rule line
_OLD_BOX_LABEL = re.compile(r"^%%\s+\S")  # box middle label line
_OLD_RULE = re.compile(r"^%%\s*[=-]{3,}\s")  # %% ===…  or  %% ---…


# ---------------------------------------------------------------------------
# Banner construction
# ---------------------------------------------------------------------------


def _title_across(lines: list[str], i: int, brace_pos: int) -> str:
    """Extract the balanced `{…}` title starting at lines[i][brace_pos].

    Reads across as many lines as needed until the braces balance (a
    semantically-wrapped title spans several source lines); a line break
    inside the title becomes a single space.  Nested braces are kept.
    Whitespace is collapsed.  Best-effort if the braces never close.
    """
    depth = 0
    buf: list[str] = []
    j, k = i, brace_pos
    while j < len(lines):
        s = lines[j]
        while k < len(s):
            ch = s[k]
            if ch == "{":
                depth += 1
                if depth > 1:
                    buf.append(ch)
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return re.sub(r"\s+", " ", "".join(buf)).strip()
                buf.append(ch)
            else:
                buf.append(ch)
            k += 1
        if depth >= 1:  # title continues on the next line
            buf.append(" ")
        j += 1
        k = 0
    return re.sub(r"\s+", " ", "".join(buf)).strip()


def _indentator(depth: int, envname: str, title: str) -> list[str]:
    """Build the three-line banner for a unit at the given relative depth.

    The environment name is upper-cased (DOCUMENT, SECTION, SUBSECTION, …).
    """
    bar = "%#"
    arm = "%" + "#" * depth
    name = envname.upper()
    mid = f"{arm} {name}: {title}" if title else f"{arm} {name}"
    return [bar, mid, bar]


def _strip_trailing_banner(out: list[str]) -> None:
    """Remove a banner block already sitting at the tail of *out*.

    Recognizes the current three-line indentator and the older box / rule
    formats, so a change of banner style replaces rather than stacks.
    """
    if (
        len(out) >= 3
        and _NEW_BAR.match(out[-1])
        and _NEW_MID.match(out[-2])
        and _NEW_BAR.match(out[-3])
    ):
        del out[-3:]
        return
    if (
        len(out) >= 3
        and _OLD_BOX_RULE.match(out[-1])
        and _OLD_BOX_LABEL.match(out[-2])
        and _OLD_BOX_RULE.match(out[-3])
    ):
        del out[-3:]
        return
    if out and _OLD_RULE.match(out[-1]):
        del out[-1]


# ---------------------------------------------------------------------------
# File processor
# ---------------------------------------------------------------------------


def _walk_verbatim(lines: list[str]):
    """Yield (index, line, in_verbatim) tracking verbatim environments."""
    env_stack: list[str] = []
    for i, line in enumerate(lines):
        in_verbatim = any(e in VERBATIM_ENVS for e in env_stack)
        yield i, line, in_verbatim
        for m in _BEGIN_RE.finditer(line):
            env_stack.append(m.group(1))
        for m in _END_RE.finditer(line):
            env = m.group(1)
            for k in range(len(env_stack) - 1, -1, -1):
                if env_stack[k] == env:
                    del env_stack[k]
                    break


def process(text: str) -> str:
    """Return *text* with sectioning banners normalized."""
    lines = text.split("\n")

    # Pass 1: the shallowest sectioning level actually present -> depth 2,
    # and the document title (from \title{…}) for the DOCUMENT banner.
    min_level: int | None = None
    doc_title = ""
    for j, line, in_verbatim in _walk_verbatim(lines):
        if in_verbatim:
            continue
        m = _SEC_RE.match(line)
        if m:
            lvl = _LEVEL[m.group("cmd")]
            min_level = lvl if min_level is None else min(min_level, lvl)
        elif not doc_title:
            tm = _TITLE_RE.match(line)
            if tm:
                doc_title = _title_across(lines, j, tm.end() - 1)

    # Pass 2: emit banners.
    out: list[str] = []
    for i, line, in_verbatim in _walk_verbatim(lines):
        sec = _SEC_RE.match(line) if not in_verbatim else None
        doc = _DOC_RE.match(line) if not in_verbatim else None

        if sec or doc:
            _strip_trailing_banner(out)
            while out and out[-1].strip() == "":
                out.pop()
            if out:
                out.append("")

            if doc:
                banner = _indentator(1, "document", doc_title)
            elif sec and min_level is not None:
                cmd = sec.group("cmd")
                depth = 2 + (_LEVEL[cmd] - min_level)
                title = _title_across(lines, i, sec.end() - 1)
                banner = _indentator(depth, cmd, title)
            else:  # unreachable
                banner = []

            out.extend(banner)
            out.append(line)
        else:
            out.append(line)

    return "\n".join(out)


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
        help="Dry run: report files that would change, exit 1 if any.",
    )
    args = ap.parse_args()

    changed: list[str] = []
    for path_str in args.files:
        path = Path(path_str)
        if not path.exists():
            print(f"texsep: {path}: file not found", file=sys.stderr)
            continue
        original = path.read_text(encoding="utf-8")
        result = process(original)
        if result != original:
            changed.append(str(path))
            if not args.check:
                path.write_text(result, encoding="utf-8")
                print(f"texsep: banners normalized {path}")
        else:
            if not args.check:
                print(f"texsep: unchanged          {path}")

    if args.check:
        if changed:
            print("texsep: the following files have out-of-date banners:")
            for f in changed:
                print(f"  {f}")
            return 1
        print("texsep: all sectioning banners are up to date")

    return 0


if __name__ == "__main__":
    sys.exit(main())
