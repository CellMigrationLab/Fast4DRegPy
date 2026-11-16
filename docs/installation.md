# Installation

[⬅️ Documentation index](index.md)

There are four ways to use Fast4DRegPy. They run the same code and give the
same results.

| | What you get | You need |
|---|---|---|
| [Desktop app](#desktop-app) | the Fast4DRegPy notebook, in its own JupyterLab | Windows, macOS or Linux; no Python |
| [napari and Fiji](#napari-and-fiji) | two tools on the image you have open | the desktop app, and the LabConstrictor plugin once |
| [Google Colab](#google-colab) | the notebook in the browser | a Google account |
| [Python](#python) | the `fast4dreg` package for your own scripts | Python 3.10–3.13 |

## Desktop app

The app is built with [LabConstrictor](https://cellmigrationlab.github.io/LabConstrictor-Site/):
it brings its own Python, so nothing else needs to be installed.

1. Open the [latest release](https://github.com/CellMigrationLab/Fast4DRegPy/releases)
   and download the installer for your computer: `.exe` for Windows, `.pkg`
   for macOS (Apple silicon or Intel), `.sh` for Linux.
2. Run it. Installing takes about 6–8 minutes and needs an internet
   connection; you do it once. Windows may show *Windows protected your PC*:
   click **More info**, then **Run anyway**.
3. Open **Fast4DRegPy** from the Start menu, Launchpad or your applications
   menu. JupyterLab opens with the Fast4DRegPy notebook.

The LabConstrictor website has the same steps with pictures for each system:
[Install an app](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/install/),
[Open and use an app](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/using-apps/) and
[If the app does not start](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/troubleshooting-installed-app/).

Then follow the [step-by-step workflow](workflow.md).

## napari and Fiji

Installing the desktop app also makes its two tools, **Correct drift
(time-lapse)** and **Align channels**, available to napari and Fiji. Each
program needs the LabConstrictor plugin, installed once per computer:

- napari: [Install the napari plugin](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/napari/)
- Fiji: [Install the Fiji plugin](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/fiji/)

The tools run in the app's own Python: napari and Fiji do not need
Fast4DRegPy, NanoPyx or anything else. How to use them:
[napari and Fiji](napari_fiji.md). (QuPath is not offered: drift correction
of time-lapse movies is not a QuPath task.)

This is separate from the original
[Fast4DReg Fiji plugin](https://github.com/CellMigrationLab/Fast4DReg), which
you can keep using; the two give the same drift (see [Validation](validation.md)).

## Google Colab

[Open the notebook in Colab](https://colab.research.google.com/github/CellMigrationLab/Fast4DRegPy/blob/main/notebooks/Fast4DRegApp/Fast4DRegApp.ipynb)
and run the cells from the top. The first cell installs Fast4DRegPy and
connects your Google Drive; put your TIFF files in your Drive and give their
path under `/content/gdrive/MyDrive/`.

## Python

Fast4DRegPy supports Python 3.10–3.13. Use a virtual environment or a conda
environment.

```bash
python -m pip install "fast4dregpy @ git+https://github.com/CellMigrationLab/Fast4DRegPy"
```

Once a release is published on PyPI:

```bash
python -m pip install fast4dregpy
```

Extras: `fast4dregpy[notebook]` adds JupyterLab, ipywidgets and matplotlib for
the notebook; `fast4dregpy[validation]` adds matplotlib for the validation
figures.

The distribution is called `fast4dregpy`; the package is imported as
`fast4dreg`. It depends on [NanoPyx](https://github.com/HenriquesLab/NanoPyx)
2.1.4 (exactly this version), NumPy 2, SciPy, scikit-image and tifffile.

Next: the [Python guide](python.md).
