# Makefile — single-paper ("export form") build and format targets.
# This repository holds ONE paper at its root; it is migrated later into a subdirectory
# of the consolidated repository (QuantumDI), whose Makefile is multi-paper.
#
#   make build    build the paper with latexmk (PDF here, intermediates in _build/)
#   make format   fashion + wrap + indent;  make check   dry-run;  make lint  chktex
#   make clean    remove build products

COLS    := 256
TEX_SRC := $(wildcard *.tex)
MAIN    := $(basename $(firstword $(shell grep -l '\\documentclass' *.tex)))

.PHONY: all build format reflow fashion wrap indent sep check lint clean install-hooks
all: build

build:
	latexmk $(MAIN)

format: fashion reflow
reflow: wrap indent
fashion:
	python3 _scripts/texfashion.py $(TEX_SRC)
wrap:
	python3 _scripts/texwrap.py --cols $(COLS) $(TEX_SRC)
indent:
	@for f in $(TEX_SRC); do latexindent -m -w -s -l latexindent.yaml "$$f" && echo "latexindent: $$f"; done
sep:
	python3 _scripts/texsep.py $(TEX_SRC)
check:
	@rc=0; python3 _scripts/texfashion.py --check $(TEX_SRC) || rc=1; \
	python3 _scripts/texwrap.py --check --cols $(COLS) $(TEX_SRC) || rc=1; exit $$rc
lint:
	@for f in $(TEX_SRC); do chktex -q -l .chktexrc "$$f"; done
clean:
	rm -rf _build *.bak[0-9] indent.log
install-hooks:
	bash _scripts/setup-hooks.sh
