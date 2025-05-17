# docs/conf.py
import os
import sys

sys.path.insert(0, os.path.abspath("../src"))  # Path to your source code

project = "junjo"
copyright = "2025, Matthew Rideout"
author = "Matthew Rideout"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",  # Core Sphinx library for auto html doc generation
    "sphinx.ext.napoleon",  # Support for NumPy and Google style docstrings
    "sphinx.ext.viewcode",  # Add links to highlighted source code
    "sphinx.ext.intersphinx",  # Link to other project's documentation (see mapping below)
    "sphinx.ext.doctest",  # Test code examples in docstrings
    "sphinx.ext.todo",  # Support for TODO items
    "sphinx.ext.coverage",  # Check documentation coverage
    "sphinx.ext.ifconfig",  # Conditional content based on configuration
]

# -- Options for HTML output -------------------------------------------------

html_theme = "furo"
html_title = "Junjo Docs"

# Furo theme options (see: https://pradyunsg.me/furo/customisation/)
html_theme_options = {
    # "light_css_variables": {
    #     "color-brand-primary": "red",
    #     "color-brand-content": "#CC3333",
    # },
    # "dark_css_variables": {
    #      "color-brand-primary": "orange",
    #     "color-brand-content": "#FF8800",
    # },
    "sidebar_hide_name": False,  # Show the project name in the sidebar
    # "navigation_with_keys": True, # Allow navigation with arrow keys
    # "announcement": "<em>Important</em> announcement!",  # Add a banner at the top
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

# -- Options for autodoc ----------------------------------------------------

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "undoc-members": True,
    "show-inheritance": True,
}

autoclass_content = "both"  # Include both class and __init__ docstrings

# -- Options for intersphinx ----------------------------------------------
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "requests": (
        "https://requests.readthedocs.io/en/latest/",
        None,
    ),  # Example: link to requests
    # Add other mappings as needed
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# The master toctree document.
master_doc = "index"
