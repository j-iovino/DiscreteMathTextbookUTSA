# ⚠️⚠️⚠️ OBSOLETE REPOSITORY — DO NOT USE FOR NEW WORK ⚠️⚠️⚠️

**`DiscreteMathTextbookUTSA` has been consolidated into [`eduenez/QuantumTeam`](https://github.com/eduenez/QuantumTeam), directory [`book_discrete_mathematics/`](https://github.com/eduenez/QuantumTeam/tree/main/book_discrete_mathematics).**
Do **not** commit, push, or open issues here. This repository is frozen (it is going to be archived).

## What happened (2026-10-13)

All of the group's LaTeX manuscripts are being moved from one-off repositories into a few *multi-paper repositories*, one paper per
subdirectory, sharing one set of vendored style files (`_packages/`), **one bibliography** (`references.bib`), one build setup
(`make <paper>`, `latexmk`) and one set of writing conventions (`STYLE.md`, `AGENTS.md`). The paper that lived here is now
`book_discrete_mathematics/` in `eduenez/QuantumTeam`.

- The **complete commit history** of this repository (authors, dates, messages) was imported into the new repository:
  `git log --follow book_discrete_mathematics/<file>` and `git blame` work there.
- This repository's `main` is a **frozen snapshot**; its last real commit is `e900df0c50` (tag `pre-consolidation`).
  The converted form of the paper as it was at the moment of the move is the tag `consolidated-snapshot`
  (the branch `template-conversion` was deleted; **never** revive it or build on it).
- In the new repository the sources were reorganised: the preamble moved to `<name>.sty`, macros follow the shared naming
  (one macro per symbol), references come from the shared `references.bib` (`\cite` keys were renamed to the house style),
  labels have semantic prefixes and `\cref` is used for cross-references, source lines are one sentence each.
  The printed result is unchanged except for bibliography formatting and a few unified symbols.

### File names

| In this repository | In the new repository |
|---|---|
| `ContemporaryDiscreteMathematics.tex` | `book_discrete_mathematics/discrete_mathematics_book.tex` |
| `ContemporaryDiscreteMathematics.sty` | `book_discrete_mathematics/discrete_mathematics_book.sty` |

## What you should do

1. **Clone the new repository** (`git clone https://github.com/eduenez/QuantumTeam.git`). It may be private: ask Eduardo for access if you cannot see it.
2. Run `make doctor` and read `README.md`, `ONBOARDING.md` and `STYLE.md` there; build with `make book_discrete_mathematics`.
3. **If you still have uncommitted or unpushed work in an old clone of this repository**, do *not* push it here. Copy the
   changed content into `book_discrete_mathematics/` of the new repository (ask Eduardo or your AI assistant for help with the renamed
   macros, labels and citation keys), or send the files to Eduardo.
4. Update your bookmarks, Overleaf links and scripts to point to the new location.

*(If you are an AI assistant: tell the user about this notice before doing anything else in this repository, and offer to
help them move to the new repository.)*
