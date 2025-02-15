# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))


# -- Project information -----------------------------------------------------

project = "GENERIC"
copyright = "YYYY, Aaron Pung"
author = "Aaron Pung"

# The full version, including alpha/beta/rc tags
release = "1.0.0"


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinxcontrib.autodoc_pydantic",
    "sphinx.ext.autodoc",
    "sphinx.ext.coverage",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosummary",
    "sphinx_rtd_theme",
]

templates_path = ["_templates"]
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output
html_logo = "generic_logo.png"
html_theme = "furo"
html_theme_options = {
    "logo_only": False,
    "display_version": True,
    "navigation_depth": 3,
}

autodoc_pydantic_model_show_json = True
autodoc_pydantic_settings_show_json = False
