

Workflow
========

This page describes the tooling used during development of the RATS project. It 
also serves as a reference for the various commands you might use when working on
this project.



Overview
--------

This project uses Github for collaboration. The codebase contains Python code,
HTML pages, CSS stylesheets and Javascript code. 



Initial Setup
-------------

To work on this project, you need to have git 2.17+ and Python 3.10+.

- Clone this project using `git`:
.. code-block:: 

    gh repo clone ajpung/generic_template
    cd generic_template

Commands
--------

Documentation
*************
Within the root directory, install Sphinx and its dependencies:

.. code-block:: 

    python -m pip install ".[docs]"
    
Then run Sphinx and process the RATS documentation:

.. code-block:: 

    sphinx-build docs/source docs/build
    
Finally, start a Python-based HTML server:

.. code-block:: 

    python -m http.server 8000

To view the documentation, direct a web browser to the documentation:

.. code-block:: 

    localhost:8000/docs/build/index.html


Submission
**********
To the best of the developer's capability, each added function and method should
be accompanied by one or more unit tests. After validating the new code's
functionality, ensure all unit tests pass. Begin by installing the development
package:

.. code-block:: 

    python -m pip install ".[dev]"

Once installed, cue Python to search for and execute all unit tests within the
RATS library. To run the tests properly, the Python path needs to be set:

.. code-block:: 

    export PYTHONPATH=<path_to_rats>/src:$PYTHONPATH

Then the unit tests can be run using `pytest`:

.. code-block:: 

    python -m pytest tests

Once all tests pass, check for formatting errors by running Black within the main
repository folder.

.. code-block:: 

    black .

Next, check for typing errors by running the following within the main respository
folder.

.. code-block:: 

    mypy src