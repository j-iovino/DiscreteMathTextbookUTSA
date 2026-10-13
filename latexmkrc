# latexmkrc — shared latexmk configuration for ALL papers in this repository.
#
# Each paper lives in its own subdirectory (e.g. my-paper/my-paper.tex). Build
# a paper by running latexmk from inside its directory (a one-line latexmkrc
# there loads this file), or from the repo root with `make my-paper`.
# VS Code (LaTeX Workshop) passes this file explicitly via `latexmk -r`.
#
# Engine: pdfLaTeX (uniform across the group; STIX Two fonts).
#
# Output layout (relative to the paper's directory): the PDF lands next to the
# source; intermediates (.aux, .log, .bbl, …) go to _build/. Both are gitignored.
#
# NOTE: this governs latexmk only. A manual `pdflatex; bibtex; pdflatex` run
# ignores this file; it still works (each paper's .tex finds the shared files
# via ../_packages/ and ../references.bib) but leaves intermediates beside the
# source.

use File::Basename qw(dirname);
use Cwd qw(abs_path);

# Absolute path of the repo root (the directory containing THIS file), so the
# configuration is independent of which paper directory latexmk runs in.
$_repo_root = abs_path(dirname(__FILE__));

# Vendored shared packages (di-base-*, …) and the shared bibliography.
ensure_path('TEXINPUTS', "$_repo_root/_packages//");
ensure_path('BIBINPUTS', $_repo_root);

$aux_dir = '_build';
$out_dir = '.';

$pdf_mode = 1;   # pdflatex → PDF
$pdflatex = 'pdflatex -interaction=nonstopmode -synctex=1 %O %S';

# Monographs \include chapter files; $emulate_aux lets latexmk manage their
# per-file .aux inside $aux_dir without "cannot find .aux" complaints.
$emulate_aux = 1;

# Run bibtex from the paper's directory (not from inside _build/), so that
# \bibliography{../references} resolves exactly as in a manual run.
$bibtex_fudge = 0;
