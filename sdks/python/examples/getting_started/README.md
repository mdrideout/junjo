# Getting Started Example

This is the example Junjo workflow from the Junjo Python API docs.

```bash
# Run commands from this directory
#   - Using uv package manager https://docs.astral.sh/uv/
#
# This repo is a `uv` workspace. The virtual environment lives at the repo root
# (`../../.venv` from here), not inside this example directory.
#
# Note: workspace syncs are exact — syncing one example package removes the
# other examples' packages from the shared root venv, so re-run the sync
# below when switching between examples.
#
# Ensure all packages are installed (Python 3.13)
$ uv sync --python 3.13 --package getting-started

# Run from this directory
$ uv run --package getting-started -m main
```
