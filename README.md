# River Critters
A machine learning tool to predict the presence and density of woodland creatures images taken by trail cameras.
This data is taken from three trail cameras in Kansas throughout the year.

The project is broken into two pieces. The first piece is based on machine learning, and is used to predict which 
woodland animals are in which scenes. The second portion is based on computer vision, used to determine *where* the
creatures are in each scene.

# Introduction

Notes and commands used to contribute are contained in the documentation.

# Before running
Ensure your Python path is set to the local repository's source directory using:
`export PYTHONPATH=<path to repo>/src:$PYTHONPATH`.

# Documentation
Initially, documentation can be read from within the repository's `docs` folder,
found in: `<repository>/docs/build/index.html`. If `index.html` does not exist
yet, use the following two commands then try locating the `index.html` file.

```
python -m pip install ".[docs]" 
sphinx-build docs/source docs/build
```


# Installation
```
python -m pip install --upgrade pip setuptools wheel numpy
python -m pip install .[dev]
```

# Running the tool
(Needs completion)