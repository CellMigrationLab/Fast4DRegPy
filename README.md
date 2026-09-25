# Fast4DReg Python

**Fast4DReg Python** is the Python implementation of the Fast4DReg method for
projection-based drift correction and channel registration of 2D and 3D
microscopy data. It uses
[NanoPyx](https://github.com/HenriquesLab/NanoPyx) for the cross-correlation
drift estimator, in the same architectural role that NanoJ plays in the
original [Fast4DReg Fiji implementation](https://github.com/CellMigrationLab/Fast4DReg).

This project is distinct from
[`napari-fast4dreg`](https://github.com/COSC-Lab/napari-fast4dreg), which is a
separate Python interpretation of Fast4DReg with a napari plugin and additional
features. The goal here is a direct, testable Python implementation of the
original Fast4DReg workflow and algorithm, with an API suitable for scripts,
notebooks, pipelines, and headless execution.

Version `0.4.0` keeps registration, transformation, axes, I/O, scalar metrics,
and validation images in separate modules while exposing six direct
registration functions. The major remaining Fiji-parity gap is axial (Z)
reslice scaling; it is documented explicitly in
[`docs/parity_audit.md`](docs/parity_audit.md) rather than hidden behind an
unverified approximation. The complete previous audit and fix list is in
[`docs/code_audit_2026-08-08.md`](docs/code_audit_2026-08-08.md).

The package does not infer dimensions or silently change settings. Invalid
parameters, non-finite data, unavailable backends, and existing output files
raise descriptive exceptions.

## Reference datasets

The Fast4DReg datasets and reference outputs are archived on Zenodo:

- **Dataset record requested for this project:** https://zenodo.org/records/6534570
  (DOI: https://doi.org/10.5281/zenodo.6534570)
- Zenodo currently links that record to the expanded **version 2.0** record:
  https://zenodo.org/records/7514913

The archive contains synthetic-drift data, HUVEC data, channel-alignment data,
expected/reference outputs, and the original software archive. These data are
the preferred source for future Fiji-versus-Python regression fixtures; the
full multi-gigabyte archive is not vendored in this repository. See
[`docs/data.md`](docs/data.md).

## Supported inputs

| Task | Expected layout | Examples |
| --- | --- | --- |
| Time registration | A time series with explicit `T` | `TYX`, `TZYX`, `CTZYX`, `TZCYX` |
| Channel registration | Multiple channels, currently one timepoint | `CYX`, `CZYX` |

Axis strings are mandatory and must match the NumPy array dimensions. The
library never guesses whether a stack dimension represents channels, Z, or
time. Axis names are case-insensitive. Estimated translations are always
stored as `(dz, dy, dx)` and mean “translation to apply.”

## Installation

Python 3.12 is a good default for development; CI tests Python 3.10–3.13:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test,notebook]"
```

## Time registration

```python
import tifffile
from fast4dreg import register_time, save_drift_csv, save_tiff

image = tifffile.imread("timelapse.tif")  # shape: T,Z,Y,X

corrected, shifts = register_time(
    image,
    axes="TZYX",
    projection="max",
    reference="first",
    correct_xy=True,
    correct_z=True,
    backend="threaded",
    workers=4,
)

save_tiff("timelapse_registered.tif", corrected, axes="TZYX")
save_drift_csv("timelapse_drift.csv", shifts)
```

`correct_z=False` is the default so `TYX` data work without hidden dimension
logic. Set it to `True` only for data with a real Z axis and at least two
slices. When both corrections are enabled, XY is estimated and applied first;
the Z projection is then calculated from the XY-corrected volumes, matching
the Fast4DReg workflow.

`backend` must be either `"threaded"` or `"unthreaded"`. The selected NanoPyx
implementation is called directly; failures are propagated and never retried
with another backend. Corrected arrays default to `float32` to retain subpixel
interpolation. Pass `output_dtype="input"` explicitly if preserving the input
dtype is more important than avoiding integer quantization.

`workers` controls how many independent volumes are transformed concurrently.
It defaults to `1`, so library calls never choose a concurrency level silently.
Use `workers=4` or `workers=8` after benchmarking on the target machine. This
setting accelerates transform application and the XY-corrected preparation used
for Z estimation; it does not change NanoPyx's selected `backend`.

On a 9-logical-CPU test system, warmed XYZ registration of a float32
`20 x 16 x 256 x 256` stack decreased from 1.60 seconds with one worker to
0.51 seconds with four and 0.39 seconds with eight. These are illustrative
measurements, not performance guarantees. Run the included benchmark locally:

```bash
python benchmarks/benchmark_transforms.py --workers 1 2 4 8
```

For multichannel time series, supply `CTZYX` (or another explicit ordering)
and choose `reference_channel`. The estimated transform is applied identically
to every channel at each timepoint.

## Channel registration

All channels must be combined into a single `CYX` or `CZYX` array:

```python
from fast4dreg import register_channels

corrected, shifts = register_channels(
    image,
    axes="CZYX",
    reference_channel=0,
    projection="max",
    correct_z=True,
)
```

Separate `XYZ` channel files must be combined into one `XYZC` or `CZYX`
hyperstack before channel registration. A set of separate files has no channel
axis, so the library rejects it instead of interpreting Z slices as channels.

## Notebook app

Open `notebooks/Fast4DRegApp.ipynb`. The notebook is deliberately thin: it
loads a TIFF, calls the package API, plots the drift, and saves TIFF/CSV output.
For time registration it can also calculate the paper's validation metrics
before and after correction. Registration logic must remain in
`src/fast4dreg`.

## Registration validation

The validation API reproduces the methods used in the Fast4DReg paper:

- mSSIM, PSNR, Pearson correlation, and the archived notebook's historical
  value labelled NRMSE;
- a conventional Euclidean NRMSE reported separately;
- temporal standard-deviation projections using ImageJ's sample-standard-
  deviation convention;
- blue/green/red three-frame overlays, line profiles, kymographs, and the
  paper's mean-signal/mean-background SNR definition.

```python
from fast4dreg import evaluate_registration, save_validation_csv

rows = evaluate_registration(
    corrected,
    axes="TZYX",
    reference="first",       # use "previous" for adjacent-frame comparison
    analysis="slice",
    z_index=8,
)
save_validation_csv("registration_validation.csv", rows)
```

`paper_nrmse` exactly preserves the archived assessment notebook's
`sqrt(mean(abs(error)))` calculation. It is not the standard NRMSE definition;
use `standard_nrmse` for new reporting.

## Development

```bash
python -m ruff check src tests benchmarks
python -m pytest -q
```

The integration tests call NanoPyx 2.1.4 on known XYZ translations. They must
not be mocked or silently skipped when NanoPyx is unavailable.

All save functions refuse to overwrite existing files by default. Pass
`overwrite=True` deliberately when replacement is intended.

## Current non-goals

- True 3D correlation
- Rotation correction
- Dask or Zarr processing
- GPU selection
- Non-rigid registration
- A napari plugin or desktop installer (see the separate `napari-fast4dreg` project)

These should only be considered after comparison with reference outputs from
the original Fast4DReg Fiji macros.

See `docs/parity_audit.md` for the complete comparison and `CODEX_TASKS.md` for
the prioritized implementation backlog.

## Citation

If you use Fast4DReg Python, cite the original Fast4DReg publication and the
NanoPyx/NanoJ work that provides the underlying registration engine. The
Fast4DReg paper is:

> Pylvänäinen JW et al. **Fast4DReg – fast registration of 4D microscopy
> datasets.** *Journal of Cell Science* 136, jcs260728 (2023).
> https://doi.org/10.1242/jcs.260728

See [`docs/implementation_spec.md`](docs/implementation_spec.md) for the
algorithm mapping and [`docs/data.md`](docs/data.md) for the reference dataset.
