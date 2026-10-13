# DO NOT EDIT THE `.sty` FILES IN THIS DIRECTORY

These `di-*.sty` files are **vendored** — pristine, byte-for-byte copies of the
shared style files from the [`LaTeX-shared-files`](https://github.com/eduenez/LaTeX-shared-files)
repository, pinned to a specific commit recorded in [`vendor.lock`](vendor.lock).

This is a deliberate **"poor man's submodule"**: clone this repo (or a project
started from it) and build immediately, with no `git submodule` steps. The
trade-off is that these files must stay identical to upstream so that a future
sync can diff them cleanly.

## Rules

- **Do not edit any `.sty` file here.** Edits will be silently overwritten on the
  next re-sync and will break the clean-diff guarantee.
- **Need to change shared notation or packages?** Change it *upstream* in
  `LaTeX-shared-files`, then re-vendor (copy the new file here and bump its commit
  hash in `vendor.lock`). Ask the maintainer (Eduardo).
- **Project-specific additions** go in the project style file
  (`../<paper>/<paper>.sty`, the
  "Project-specific additions" section), never here.

## What loads these

- An article's `<paper>.sty` loads `di-base-article` (amsart, section-scoped numbering).
- A monograph's `<paper>.sty` loads `di-base-monograph` (memoir, chapter-scoped numbering).

Both `\RequirePackage{di-base-core}` internally. Each paper's main `.tex` points `\input@path` here (and `../latexmkrc` sets
`TEXINPUTS`), so no path prefix is needed. All papers in the repository share these files. Files present but **not**
loaded (their `\usepackage` line commented out in a project `.sty`) are kept here
only for convenient future activation — this is the pattern a new project copied
from this template should follow: vendor what you need, comment the rest.

> Note: `references.bib` lives at the repo root, not here, because it is
> vendored-but-editable (add citations directly); its pin is still tracked in
> `vendor.lock`.
