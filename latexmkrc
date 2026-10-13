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

# --- Project-specific (maatext/maabook class) --------------------------------
# With maabook.cls the kernel's "No file X.bbl." message is logged as
# "LaTeX Font Info: No file X.bbl.", which latexmk does not recognise, so it never
# starts bibtex. Seeding an empty .bbl in $aux_dir makes latexmk run bibtex as usual.
for my $_tex (glob("$_repo_root/*.tex")) {
    open(my $_fh, '<', $_tex) or next;
    my $_src = do { local $/; <$_fh> };
    close($_fh);
    next unless $_src =~ /\\bibliography\{/;
    (my $_base = $_tex) =~ s{.*/}{};
    $_base =~ s/\.tex$//;
    mkdir("$_repo_root/$aux_dir") unless -d "$_repo_root/$aux_dir";
    open(my $_out, '>', "$_repo_root/$aux_dir/$_base.bbl") or next unless -e "$_repo_root/$aux_dir/$_base.bbl";
    close($_out) if $_out;
}
