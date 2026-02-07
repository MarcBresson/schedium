@ECHO OFF

REM Command file for Sphinx documentation

set SPHINXBUILD=sphinx-build
set BUILDDIR=_build
set ALLSPHINXOPTS=-d %BUILDDIR%/doctrees %SPHINXOPTS% .

if "%1" == "help" (
	:help
	echo.Please use `make ^<target^>` where ^<target^> is one of
	echo.  html      to make standalone HTML files
	echo.  dirhtml   to make HTML files named index.html in directories
	echo.  changes   to make an overview over all changed/added/deprecated items
	echo.  linkcheck to check all external links for integrity
	echo.  doctest   to run all doctests embedded in the documentation if enabled
	goto end
)

if "%1" == "html" (
	%SPHINXBUILD% -b html %ALLSPHINXOPTS% %BUILDDIR%/html
	echo.
	echo.Build finished. The HTML pages are in %BUILDDIR%/html.
	goto end
)

if "%1" == "dirhtml" (
	%SPHINXBUILD% -b dirhtml %ALLSPHINXOPTS% %BUILDDIR%/dirhtml
	echo.
	echo.Build finished. The HTML pages are in %BUILDDIR%/dirhtml.
	goto end
)

if "%1" == "changes" (
	%SPHINXBUILD% -b changes %ALLSPHINXOPTS% %BUILDDIR%/changes
	echo.
	echo.The overview file is in %BUILDDIR%/changes.
	goto end
)

if "%1" == "linkcheck" (
	%SPHINXBUILD% -b linkcheck %ALLSPHINXOPTS% %BUILDDIR%/linkcheck
	echo.
	echo.Link check complete; look for any errors in the above output ^
or in %BUILDDIR%/linkcheck/output.txt.
	goto end
)

if "%1" == "doctest" (
	%SPHINXBUILD% -b doctest %ALLSPHINXOPTS% %BUILDDIR%/doctest
	echo.
	echo.Testing of doctests in the sources finished, look at the ^
results in %BUILDDIR%/doctest/output.txt.
	goto end
)

:end
