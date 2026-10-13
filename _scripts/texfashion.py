#!/usr/bin/env python3
"""
texfashion.py — Typographic modernizer for LaTeX source files.

Rewrites three classes of "old-fashioned" input into their modern
equivalents, but **only in text mode** — never inside math, verbatim,
or the delimiter of a comment-example.  In math mode ``'`` is a prime
(``\\cprime`` and friends), so touching it there would be catastrophic;
the scanner tracks math state precisely and leaves it alone.

What it changes (text mode only):

  1. Archaic TeX accents / diacritics  ->  composed Unicode.
       \\'e \\'{e}          ->  é          \\~n \\~{n}   ->  ñ
       \\`e                 ->  è          \\"o         ->  ö
       \\^o                 ->  ô          \\c{c}       ->  ç
       \\v{s} \\H{o} \\u{g} \\r{a} \\k{a} \\=o \\.z  ->  š ő ğ å ą ō ż
       \\o \\O \\l \\L \\aa \\AA \\ae \\AE \\oe \\OE \\ss \\i \\j
                            ->  ø Ø ł Ł å Å æ Æ œ Œ ß ı ȷ
     Accents on \\i / \\j collapse to the dotted base (\\'{\\i} -> í).

  2. "Ugly" ASCII quotes  ->  curly Unicode quotes (standard LaTeX
     direction: backticks open, apostrophes close).
       `   ->  ‘        '   ->  ’
       ``  ->  “        ''  ->  ”

  3. Tabs  ->  two spaces (everywhere except verbatim environments).

Everything else — including math, verbatim/lstlisting/minted, and the
bodies of comments — is copied through untouched (a comment keeps its
quotes; only its tabs are expanded).

Usage:
    python3 texfashion.py [--check] file1.tex [file2.tex …]

    --check   Dry run: report files that would change, exit 1 if any.
"""

import argparse
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Environments
# ---------------------------------------------------------------------------

# Bodies copied byte-for-byte (not even tabs are touched).
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

# True math environments — substitutions are suppressed inside them, but
# they are still scanned (for nested $, \end{…}, etc.).  NOTE: tabular /
# longtable are deliberately NOT here — their cells are prose and DO get
# modernized.  tikzpicture is included because its syntax is not prose.
MATH_ENVS: frozenset = frozenset(
    {
        "math",
        "displaymath",
        "equation",
        "equation*",
        "align",
        "align*",
        "alignat",
        "alignat*",
        "flalign",
        "flalign*",
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
        "smallmatrix",
        "cases",
        "dcases",
        "tikzpicture",
    }
)

# Macros whose braced argument LaTeX later feeds through \MakeUppercase to
# build a running head (amsart uses \title and \author this way).  TeX's
# \uppercase primitive operates on raw character tokens, so a *composed*
# Unicode glyph (curly quote “”, en/em dash, accented letter) is split into
# its orphaned UTF-8 continuation bytes there, and inputenc then aborts with
# "Invalid UTF-8 byte" / "Unicode character … not set up".  We therefore copy
# these arguments VERBATIM — leaving ASCII ligatures (``…'' , ---) and \'e-style
# accents untouched.  Those render identically (`` `` '' `` are curly quotes via
# TeX's font ligatures) but survive \uppercase.  Quotes/accents everywhere else
# (body, footnotes, section headings) are still modernized normally.
PROTECTED_ARG_MACROS: frozenset = frozenset({"title", "author"})

# ---------------------------------------------------------------------------
# Accent tables
# ---------------------------------------------------------------------------

# command -> combining mark (applied over the following base letter)
_COMBINING: dict = {
    # control-symbol accents  (\'e  \`e  \^e  \"o  \~n  \=o  \.z)
    "'": "́",  # acute
    "`": "̀",  # grave
    "^": "̂",  # circumflex
    '"': "̈",  # diaeresis / umlaut
    "~": "̃",  # tilde
    "=": "̄",  # macron
    ".": "̇",  # dot above
    # control-word accents  (\v{s} \H{o} \u{g} \c{c} \k{a} \r{a} \d{s} \b{s})
    "v": "̌",  # caron / háček
    "H": "̋",  # double acute
    "u": "̆",  # breve
    "c": "̧",  # cedilla
    "k": "̨",  # ogonek
    "r": "̊",  # ring above
    "d": "̣",  # dot below
    "b": "̱",  # macron below
}

_SYMBOL_ACCENTS: frozenset = frozenset("'`^\"~=.")
_WORD_ACCENTS: frozenset = frozenset("vHuckrdb")

# control words that ARE a letter (no argument)
_SPECIAL_LETTERS: dict = {
    "i": "ı",
    "j": "ȷ",
    "o": "ø",
    "O": "Ø",
    "l": "ł",
    "L": "Ł",
    "aa": "å",
    "AA": "Å",
    "ae": "æ",
    "AE": "Æ",
    "oe": "œ",
    "OE": "Œ",
    "ss": "ß",
    "dh": "ð",
    "DH": "Ð",
    "th": "þ",
    "TH": "Þ",
}


def _compose(base: str, cmd: str) -> str:
    """base letter + accent command -> NFC-composed Unicode string."""
    return unicodedata.normalize("NFC", base + _COMBINING[cmd])


def _resolve_base(inner: str):
    """Resolve the braced argument of an accent to a single base letter.

    Accepts ``e``, ``{e}``-stripped ``e``, ``\\i`` / ``\\j`` (dotted i/j
    is the correct accent base).  Returns the base char or None.
    """
    s = inner.strip()
    if s == "\\i":
        return "i"
    if s == "\\j":
        return "j"
    if len(s) == 1 and (s.isalpha()):
        return s
    return None


def _read_accent_arg(text: str, p: int):
    """Starting at *p* (just past an accent command), read its argument.

    Returns (base_char, next_index) or (None, p) if it cannot be resolved
    (in which case the caller should emit the command unchanged).
    """
    n = len(text)
    # A control-word accent (\v, \c, …) may be separated from its arg by a
    # space; a control-symbol accent (\', \`, …) usually is not, but allow it.
    while p < n and text[p] == " ":
        p += 1
    if p >= n:
        return None, p

    if text[p] == "{":
        depth = 1
        q = p + 1
        while q < n and depth:
            if text[q] == "{":
                depth += 1
            elif text[q] == "}":
                depth -= 1
            q += 1
        if depth != 0:
            return None, p  # unbalanced — bail
        inner = text[p + 1 : q - 1]
        base = _resolve_base(inner)
        return (base, q) if base else (None, p)

    if text[p] == "\\":
        q = p + 1
        while q < n and text[q].isalpha():
            q += 1
        name = text[p + 1 : q]
        if name in ("i", "j"):
            return name, q
        return None, p  # accent on some other macro — leave it

    ch = text[p]
    if ch.isalpha():
        return ch, p + 1
    return None, p


# ---------------------------------------------------------------------------
# Core transform
# ---------------------------------------------------------------------------


def transform(text: str) -> str:
    """Return the modernized text (see module docstring)."""
    n = len(text)
    out: list[str] = []
    i = 0

    env_stack: list[str] = []
    in_comment = False
    dollar = False  # inside $ … $
    ddollar = False  # inside $$ … $$
    paren = False  # inside \( … \)
    bracket = False  # inside \[ … \]

    def in_verbatim() -> bool:
        return any(e in VERBATIM_ENVS for e in env_stack)

    def in_math() -> bool:
        return (
            dollar
            or ddollar
            or paren
            or bracket
            or any(e in MATH_ENVS for e in env_stack)
        )

    while i < n:
        # ── verbatim: copy literally up to the matching \end{env} ─────────
        if in_verbatim():
            venv = next(e for e in reversed(env_stack) if e in VERBATIM_ENVS)
            endtok = "\\end{" + venv + "}"
            idx = text.find(endtok, i)
            if idx == -1:
                out.append(text[i:])  # unterminated; copy the rest
                i = n
            else:
                out.append(text[i:idx])
                out.append(endtok)
                env_stack.reverse()
                env_stack.remove(venv)
                env_stack.reverse()
                i = idx + len(endtok)
            continue

        c = text[i]

        # ── inside a comment: only expand tabs ────────────────────────────
        if in_comment:
            if c == "\n":
                in_comment = False
                out.append(c)
            elif c == "\t":
                out.append("  ")
            else:
                out.append(c)
            i += 1
            continue

        if c == "\n":
            out.append(c)
            i += 1
            continue

        # ── backslash: commands, escapes, math delimiters, accents ───────
        if c == "\\":
            # control word (letters) or control symbol (single non-letter)
            if i + 1 < n and text[i + 1].isalpha():
                j = i + 1
                while j < n and text[j].isalpha():
                    j += 1
                name = text[i + 1 : j]

                if name in ("begin", "end"):
                    k = j
                    while k < n and text[k] in " \t":
                        k += 1
                    if k < n and text[k] == "{":
                        close = text.find("}", k)
                        if close != -1:
                            env = text[k + 1 : close]
                            if name == "begin":
                                env_stack.append(env)
                            else:
                                for idx2 in range(len(env_stack) - 1, -1, -1):
                                    if env_stack[idx2] == env:
                                        del env_stack[idx2]
                                        break
                            out.append(text[i : close + 1])
                            i = close + 1
                            continue
                    out.append(text[i:j])
                    i = j
                    continue

                if name == "verb":
                    # \verb<d>…<d>  (or \verb*<d>…<d>) — copy literally
                    p = j
                    if p < n and text[p] == "*":
                        p += 1
                    if p < n:
                        delim = text[p]
                        end = text.find(delim, p + 1)
                        if end != -1:
                            out.append(text[i : end + 1])
                            i = end + 1
                            continue
                    out.append(text[i:j])
                    i = j
                    continue

                # word-accent (\v \c \H …) — text mode only
                if (not in_math()) and name in _WORD_ACCENTS:
                    base, nxt = _read_accent_arg(text, j)
                    if base is not None:
                        out.append(_compose(base, name))
                        i = nxt
                        continue
                    out.append(text[i:j])
                    i = j
                    continue

                # standalone special letter (\o \ss \ae \i …) — text mode only
                if (not in_math()) and name in _SPECIAL_LETTERS:
                    out.append(_SPECIAL_LETTERS[name])
                    i = j
                    # TeX gobbles one separating space or an empty {} group
                    if text[i : i + 2] == "{}":
                        i += 2
                    elif i < n and text[i] == " ":
                        i += 1
                    continue

                # running-head macros (\title, \author): copy the whole
                # invocation verbatim so composed Unicode never reaches
                # \MakeUppercase.  See PROTECTED_ARG_MACROS.
                if (not in_math()) and name in PROTECTED_ARG_MACROS:
                    p = j
                    # skip whitespace, then any optional [...] arguments
                    while True:
                        while p < n and text[p] in " \t":
                            p += 1
                        if p < n and text[p] == "[":
                            depth = 0
                            while p < n:
                                if text[p] == "\\":
                                    p += 2
                                    continue
                                if text[p] == "[":
                                    depth += 1
                                elif text[p] == "]":
                                    depth -= 1
                                    if depth == 0:
                                        p += 1
                                        break
                                p += 1
                            continue
                        break
                    # copy the mandatory {...} argument verbatim
                    if p < n and text[p] == "{":
                        depth = 0
                        q = p
                        while q < n:
                            if text[q] == "\\":
                                q += 2
                                continue
                            if text[q] == "{":
                                depth += 1
                            elif text[q] == "}":
                                depth -= 1
                                if depth == 0:
                                    q += 1
                                    break
                            q += 1
                        out.append(text[i:q])
                        i = q
                        continue
                    # no braced argument found — copy just the control word
                    out.append(text[i:j])
                    i = j
                    continue

                # any other macro: copy the control word, leave args alone
                out.append(text[i:j])
                i = j
                continue

            # control symbol (single char after backslash)
            sym = text[i + 1] if i + 1 < n else ""
            if sym == "(":
                paren = True
                out.append("\\(")
                i += 2
                continue
            if sym == ")":
                paren = False
                out.append("\\)")
                i += 2
                continue
            if sym == "[":
                bracket = True
                out.append("\\[")
                i += 2
                continue
            if sym == "]":
                bracket = False
                out.append("\\]")
                i += 2
                continue

            # symbol accent (\' \` \^ \" \~ \= \.) — text mode only
            if (not in_math()) and sym in _SYMBOL_ACCENTS:
                base, nxt = _read_accent_arg(text, i + 2)
                if base is not None:
                    out.append(_compose(base, sym))
                    i = nxt
                    continue

            # escaped char (\$ \% \{ \} \& \_ \# \\ \- …): copy both verbatim
            out.append(text[i : i + 2] if sym else text[i:])
            i += 2 if sym else 1
            continue

        # ── comment start (also inside math: % is still a comment) ────────
        if c == "%":
            out.append("%")
            in_comment = True
            i += 1
            continue

        # ── math toggles ──────────────────────────────────────────────────
        if c == "$":
            if i + 1 < n and text[i + 1] == "$":
                ddollar = not ddollar
                out.append("$$")
                i += 2
            else:
                dollar = not dollar
                out.append("$")
                i += 1
            continue

        # ── tabs: two spaces, in any (non-verbatim) mode ─────────────────
        if c == "\t":
            out.append("  ")
            i += 1
            continue

        # ── math body: copy verbatim (this is where ' stays a prime) ─────
        if in_math():
            out.append(c)
            i += 1
            continue

        # ── text mode: curly quotes ──────────────────────────────────────
        if c == "`":
            if i + 1 < n and text[i + 1] == "`":
                out.append("“")  # “ opening double
                i += 2
            else:
                out.append("‘")  # ‘ opening single
                i += 1
            continue
        if c == "'":
            if i + 1 < n and text[i + 1] == "'":
                out.append("”")  # ” closing double
                i += 2
            else:
                out.append("’")  # ’ closing single
                i += 1
            continue

        out.append(c)
        i += 1

    return "".join(out)


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
            print(f"texfashion: {path}: file not found", file=sys.stderr)
            continue
        original = path.read_text(encoding="utf-8")
        result = transform(original)
        if result != original:
            changed.append(str(path))
            if not args.check:
                path.write_text(result, encoding="utf-8")
                print(f"texfashion: modernized {path}")
        else:
            if not args.check:
                print(f"texfashion: unchanged  {path}")

    if args.check:
        if changed:
            print("texfashion: the following files have old-fashioned input:")
            for f in changed:
                print(f"  {f}")
            return 1
        print("texfashion: all files use modern typography")

    return 0


if __name__ == "__main__":
    sys.exit(main())
