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
    "sphinxext.opengraph",
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
html_theme_options = {
    "sidebar_hide_name": True,
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/MarcBresson/schedium",
            "html": """
                <svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path>
                </svg>
            """,
            "class": "",
        },
    ],
    "source_repository": "https://github.com/MarcBresson/schedium/",
    "source_branch": "main",
    "source_directory": "docs/",
}

html_copy_source = False
html_show_sourcelink = False

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
