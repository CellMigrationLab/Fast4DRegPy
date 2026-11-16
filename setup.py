"""The Python package of the app, as the LabConstrictor installer installs it (src/, see .tools/docs/external_code_upload.md).

pyproject.toml describes the package fast4dregpy for pip and PyPI (name, version, Python versions, dependencies); when it is
present, its values win. The installer ships only this file and src/, so this file says just enough to install the code:
the import name, the version and where the packages are. Each release writes its version here (.tools/python/bump_version.py).

Unlike the template's setup.py, it gives no python_requires and no install_requires: those would override the ones of
pyproject.toml in the package on PyPI (the installer installs the dependencies itself, from requirements.txt).
"""
from setuptools import find_packages, setup

setup(
    name="fast4dreg",
    version="0.5.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
)
