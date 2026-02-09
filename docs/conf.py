from __future__ import annotations

import os
import sys
from datetime import date
from urllib.parse import quote

# Ensure the project root is importable when building docs.
DOCS_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(DOCS_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

project = "schedium"
author = "Marc Bresson"
copyright = f"{date.today().year}, {author}"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.doctest",
    "numpydoc",
    "sphinx_copybutton",
    "sphinx.ext.linkcode",
]

autosummary_generate = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# Numpy-style docstrings
numpydoc_show_class_members = False

html_theme = os.environ.get("SPHINX_HTML_THEME", "furo")
html_static_path = ["_static"]
html_logo = "logo.svg"
html_favicon = "favicon.svg"

# Make the API output a bit cleaner.
autodoc_member_order = "bysource"
autodoc_typehints = "description"


def linkcode_resolve(domain, info):
    # print(f"domain={domain}, info={info}")
    if domain != "py":
        return None
    if not info["module"]:
        return None
    filename = quote(info["module"].replace(".", "/"))
    if not filename.startswith("tests"):
        filename = "src/" + filename
    if "fullname" in info:
        anchor = info["fullname"]
        anchor = "#:~:text=" + quote(anchor.split(".")[-1])
    else:
        anchor = ""

    # github
    result = "https://github.com/MarcBresson/schedium/blob/master/{}.py{}".format(
        filename,
        anchor,
    )
    return result
