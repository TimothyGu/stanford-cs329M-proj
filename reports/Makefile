.PHONY: all
all: proposal.pdf progress.pdf report.pdf

%.pdf: %.tex
	latexmk --pdf -shell-escape $<

.PHONY: clean
clean:
	rm -rf *.aux *.bbl *.blg *.fdb_latexmk *.fls *.log *.out *.pdf _minted*
