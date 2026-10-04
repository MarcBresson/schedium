Contributing
============

Development install
-------------------

.. code-block:: bash

   git clone https://github.com/MarcBresson/schedium.git
   cd schedium
   python -m venv .venv && source .venv/bin/activate
   pip install -e . --group dev --group test --group docs
   pre-commit install

Running the tests
-----------------

.. code-block:: bash

   pytest

``asyncio_mode`` is set to ``auto`` in ``pyproject.toml``, so ``async def`` tests are
collected without needing a marker. If you're adding new behavior, add a test next to the
ones in ``tests/`` that cover the closest existing feature.

Pre-commit hooks
----------------

.. code-block:: bash

   pre-commit run --all-files

This repository runs ``ruff``, ``ruff-format``, ``pyupgrade`` (targeting Python 3.10+),
``mypy``, and ``numpydoc-validation`` on every commit. Public docstrings follow the
`numpydoc <https://numpydoc.readthedocs.io/>`_ style, as that is what the API reference is
generated from.

Submitting a change
-------------------

1. Fork the repository.
2. Create a feature branch (``git switch -c feature/my-feature``).
3. Make sure ``pytest`` passes and the pre-commit hooks are clean.
4. Open a pull request against ``main``.

Commit messages are prefixed with a category, such as ``ENH:`` (new feature), ``FIX:``,
``DOC:``, ``TST:``, ``CI:``, ``MAINT:``, ``DEP:`` or ``REL:`` (release). They end up in the
:doc:`changelog`, so keep them short and descriptive.

Continuous integration
----------------------

Four GitHub Actions workflows live in ``.github/workflows/``. The first two run on pull
requests and on pushes to ``main``, and only when files they care about changed. The last two
run when a ``v*`` tag is pushed.

**Tests** (``tests.yml``)
   Runs ``pytest`` on Python 3.10 to 3.15 (3.15 being a pre-release). Triggered by changes to
   ``schedium/``, ``tests/``, ``pyproject.toml`` or the workflow itself. Python 3.14 also
   measures coverage. On pull requests from the same repository, a ``coverage report`` job
   then posts (or updates) a comment comparing coverage and test duration with the latest
   successful run on ``main``. If no recent run is available, it measures the base commit
   instead. Results are kept for 90 days as workflow artifacts so that later PRs can compare
   against them.

**Docs** (``docs.yml``)
   Builds these docs with Sphinx using ``-W --keep-going``, so any warning fails the job.
   Triggered by changes to ``schedium/``, ``docs/``, ``pyproject.toml`` or the workflow
   itself. On pushes to ``main`` it can also trigger a Read the Docs build, if the
   ``READTHEDOCS_TOKEN`` and ``READTHEDOCS_PROJECT_SLUG`` secrets are set. Read the Docs
   itself rebuilds from ``.readthedocs.yaml``.

**Docs changelog refresh** (``docs-changelog.yml``)
   When a GitHub release is published, edited or deleted, triggers a Read the Docs build
   (same secrets as above) so that the :doc:`changelog` reflects the current release notes.

**Release** (``release.yml``)
   On a ``v*`` tag, builds the sdist and wheel and creates a GitHub release with
   auto-generated release notes and the distributions attached. These release notes are what
   the :doc:`changelog` is built from.

**Publish** (``publish.yml``)
   On a ``v*`` tag, builds the distributions and uploads them to PyPI through
   `trusted publishing <https://docs.pypi.org/trusted-publishers/>`_, using the ``pypi``
   environment. No API token is stored in the repository.

Releasing
~~~~~~~~~

Bump ``__version__`` in ``schedium/__init__.py`` (commit message ``REL: bump version to
X.Y.Z``), then push a ``vX.Y.Z`` tag. The release and publish workflows take it from there.

Building these docs locally
---------------------------

.. code-block:: bash

   pip install -r docs/requirements.txt
   sphinx-build -b html docs docs/_build/html

Then open ``docs/_build/html/index.html``.
