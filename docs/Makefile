# Makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS   ?= -T
SPHINXBUILD  ?= sphinx-build
PAPER         =
BUILDDIR      = _build

ifneq ($(EXAMPLES_PATTERN),)
    EXAMPLES_PATTERN_OPTS := -D sphinx_gallery_conf.filename_pattern="$(EXAMPLES_PATTERN)"
endif

# Internal variables.
ALLSPHINXOPTS   = -d $(BUILDDIR)/doctrees $(SPHINXOPTS)\
    $(EXAMPLES_PATTERN_OPTS) .


.PHONY: help clean html dirhtml ziphtml changes linkcheck doctest optipng

all: html

help:
	@echo "Please use \`make <target>' where <target> is one of"
	@echo "  html      to make standalone HTML files"
	@echo "  dirhtml   to make HTML files named index.html in directories"
	@echo "  ziphtml   to make a ZIP of the HTML"
	@echo "  changes   to make an overview of all changed/added/deprecated items"
	@echo "  linkcheck to check all external links for integrity"
	@echo "  doctest   to run all doctests embedded in the documentation (if enabled)"

# Default to SPHINX_NUMJOBS=1 for full documentation build.
html: SPHINX_NUMJOBS ?= 1
html:
	@echo $(ALLSPHINXOPTS)
	# These two lines make the build a bit more lengthy, and the
	# the embedding of images more robust
	rm -rf $(BUILDDIR)/html/_images
	#rm -rf _build/doctrees/
	$(SPHINXBUILD) -b html $(ALLSPHINXOPTS) -j$(SPHINX_NUMJOBS) $(BUILDDIR)/html/stable
	@echo
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/html/stable"

dirhtml:
	$(SPHINXBUILD) -b dirhtml $(ALLSPHINXOPTS) $(BUILDDIR)/dirhtml
	@echo
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/dirhtml."

ziphtml:
	@if [ ! -d "$(BUILDDIR)/html/stable/" ]; then \
		make html; \
	fi
	# Optimize the images to reduce the size of the ZIP
	optipng $(BUILDDIR)/html/stable/_images/*.png
	# Exclude the output directory to avoid infinity recursion
	cd $(BUILDDIR)/html/stable; \
	zip -q -x _downloads \
	       -r _downloads/scikit-learn-docs.zip .
	@echo
	@echo "Build finished. The ZIP of the HTML is in $(BUILDDIR)/html/stable/_downloads."

changes:
	$(SPHINXBUILD) -b changes $(ALLSPHINXOPTS) $(BUILDDIR)/changes
	@echo
	@echo "The overview file is in $(BUILDDIR)/changes."

linkcheck:
	$(SPHINXBUILD) -b linkcheck $(ALLSPHINXOPTS) $(BUILDDIR)/linkcheck
	@echo
	@echo "Link check complete; look for any errors in the above output " \
	      "or in $(BUILDDIR)/linkcheck/output.txt."

doctest:
	$(SPHINXBUILD) -b doctest $(ALLSPHINXOPTS) $(BUILDDIR)/doctest
	@echo "Testing of doctests in the sources finished, look at the " \
	      "results in $(BUILDDIR)/doctest/output.txt."

dist: html ziphtml
