# Getting Started Example

This is the example Junjo workflow from the Junjo Python API docs.

```bash
# Run commands from this directory
#   - (Using uv package manager https://docs.astral.sh/uv/)
#
# Create a virtual environment if one doesn't exist yet (tested down to python 3.11)
$ uv venv --python 3.11

# Make sure the backend virtual environment is activated
$ source .venv/bin/activate

# Ensure all packages are installed
$ uv pip install -e .

# Run from this directory
$ python -m main
$ uv run -m main
```