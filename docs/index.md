# Fast4DRegPy documentation

Whether you want to correct one movie with a few clicks or build drift
correction into your own analysis, start here.

## Choose your path

### 🔬 I want to correct my images

1. **Install it:** [Installation](installation.md): the desktop app, Google
   Colab, or the napari / Fiji tools.
2. **Prepare your image and run it:** [Step-by-step workflow](workflow.md),
   which also explains every setting.
3. **Something looks wrong?** [Troubleshooting and known issues](troubleshooting.md).

Working in napari or Fiji? See [napari and Fiji](napari_fiji.md).

### 🐍 I write Python

1. [Installation](installation.md#python)
2. [Python guide](python.md): `register_time`, `register_channels`, measuring
   and applying separately, registration quality.
3. [Fiji compatibility](fiji_compatibility.md): how each Fiji setting maps to
   Fast4DRegPy, and the few deliberate differences.

### 🧪 I want to know how close it is to Fiji

[Validation and speed](validation.md): the complete published Fast4DReg movie,
frame by frame, against Fiji and against the known drift, and timings on the
same computer.

### 🛠️ I maintain Fast4DRegPy

[Development and releases](development.md): tests, the napari / Fiji tools,
building the app and publishing on PyPI.

## Full documentation map

- [Installation](installation.md)
- [Step-by-step workflow and settings](workflow.md)
- [napari and Fiji](napari_fiji.md)
- [Python guide](python.md)
- [Troubleshooting and known issues](troubleshooting.md)
- [Fiji compatibility](fiji_compatibility.md)
- [Validation and speed](validation.md)
- [Development and releases](development.md)

Fast4DRegPy is the Python version of
[Fast4DReg](https://github.com/CellMigrationLab/Fast4DReg) (Fiji). The desktop
app and the napari / Fiji tools are built with
[LabConstrictor](https://cellmigrationlab.github.io/LabConstrictor-Site/).
