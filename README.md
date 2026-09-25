# Fast4DRegPy

Fast4DRegPy is the Python implementation of
[Fast4DReg](https://github.com/CellMigrationLab/Fast4DReg), the Fiji tool for
correcting drift in 2D and 3D time-lapse microscopy and aligning channels in
multichannel images. It follows the same projection-based workflow and uses
[NanoPyx](https://github.com/HenriquesLab/NanoPyx) for cross-correlation, in
the role NanoJ has in the Fiji implementation.

The implementation has been checked against the complete published Fast4DReg
synthetic movie. Across all 25 timepoints, its drift table differs from a fresh
Fiji Fast4DReg run by at most 0.0047 pixels on any axis. The lowest whole-volume
Pearson correlation between the two corrected outputs is 0.9999993. The full
comparison, including per-frame errors and difference images, is in
[docs/validation.md](docs/validation.md).

## Installation

Fast4DRegPy supports Python 3.10–3.13.

```bash
python -m pip install "fast4dregpy @ git+https://github.com/CellMigrationLab/Fast4DRegPy"
```

The distribution is called `fast4dregpy`; the Python package is imported as
`fast4dreg`.

## Drift correction

```python
from fast4dreg import load_tiff, register_time, save_drift_csv, save_tiff

image = load_tiff("timelapse.tif")  # here: T, Z, Y, X

corrected, shifts = register_time(
    image,
    axes="TZYX",
    correct_xy=True,
    correct_z=True,
    workers=4,
)

save_tiff("timelapse_registered.tif", corrected, axes="TZYX")
save_drift_csv("timelapse_drift.csv", shifts)
```

The `axes` string is required. It tells Fast4DRegPy what each array dimension
means, for example `"TYX"`, `"TZYX"` or `"CTZYX"`. Dimensions are never
guessed from shape.

`shifts` has one row per timepoint. Values are the translation applied to the
frame, in `(dz, dy, dx)` pixel order. With multichannel time series, drift is
measured on `reference_channel` and the same translation is applied to every
channel.

For 3D data Fast4DRegPy follows the Fiji sequence: measure XY drift, correct
XY, build the axial projection from that corrected stack, then measure Z drift.

### Registration options

| Parameter | Default | Meaning |
| --- | --- | --- |
| `correct_xy`, `correct_z` | `True`, `False` | choose which drift components to correct |
| `projection` | `"max"` | `"max"` or `"mean"` projection |
| `reference` | `"first"` | compare with the first or previous frame |
| `time_averaging` | `1` | average frames in blocks before estimation |
| `max_expected_drift` | `0` | search radius in pixels; 0 uses the full correlation map |
| `axial_projection_axis` | `"Y"` | Fiji Top (`"Y"`) or Left (`"X"`) reslice |
| `crop_output` | `False` | crop to the region present in every frame |
| `extend_z` | `False` | pad Z before applying Z translations |
| `interpolation` | `"imagej"` | ImageJ-compatible bicubic; `"scipy"` is also available |
| `output_dtype` | `"float32"` | return float32 or explicitly round to the input dtype |
| `backend` | `"threaded"` | NanoPyx estimator backend for the direct estimation path |
| `workers` | `1` | number of independent volumes transformed concurrently |

The `unthreaded` NanoPyx backend is available when
`time_averaging=1` and `max_expected_drift=0`. Fiji-compatible time
averaging and bounded searches use NanoPyx's compiled correlation primitives
directly, so requesting `backend="unthreaded"` with either of those modes
raises an error rather than silently ignoring the setting.

Fiji exposes separate XY and Z values for projection, reference, averaging and
search radius. Fast4DRegPy currently uses one value for both. See
[docs/fiji_compatibility.md](docs/fiji_compatibility.md) for the exact mapping
and the remaining differences.

## Channel alignment

```python
from fast4dreg import register_channels

corrected, shifts = register_channels(
    image,
    axes="CZYX",
    reference_channel=0,
    correct_z=True,
)
```

All channels must be in one array with a `C` axis. Channel-shift estimation
expects a single timepoint.

## Registration quality

The package includes the measurements used in the Fast4DReg paper:

```python
from fast4dreg import evaluate_registration, save_validation_csv

rows = evaluate_registration(corrected, axes="TZYX", analysis="max")
save_validation_csv("registration_quality.csv", rows)
```

`evaluate_registration` reports mSSIM, PSNR, Pearson correlation, the
historical NRMSE calculation used in the paper, and a conventional NRMSE under
a separate name. Image-based helpers include temporal standard-deviation
projections, three-frame overlays, line profiles, kymographs and
signal-to-background ratios.

## Notebook

`notebooks/Fast4DRegApp.ipynb` is a small interface for loading a TIFF,
running registration, viewing the drift and saving the outputs.

```bash
python -m pip install "fast4dregpy[notebook] @ git+https://github.com/CellMigrationLab/Fast4DRegPy"
```

## Validation and performance

The published large-drift movie contains 25 timepoints, 69 Z planes and
416 × 416 pixels per plane. Fast4DRegPy has been compared frame by frame with
both the known synthetic drift and a fresh run of the original Fiji macro;
see [docs/validation.md](docs/validation.md).

On the 2-CPU GitHub Actions runner used for the recorded timing comparison,
Fast4DRegPy took 19.5 s with one transform worker and 14.9 s with four. The
Fiji macro reported 41 s on the same runner. These numbers describe that run,
not a general speed guarantee.

## Development

```bash
git clone https://github.com/CellMigrationLab/Fast4DRegPy
cd Fast4DRegPy
python -m pip install -e ".[dev]"
python -m ruff check src tests benchmarks validation
python -m pytest -q
```

The normal test suite runs on Python 3.10–3.13. The full published-movie
comparison is intentionally separate because it downloads a 1.5 GB archive;
instructions are in [validation/README.md](validation/README.md).

## Citation

If you use Fast4DRegPy, please cite Fast4DReg and NanoPyx:

> Pylvänäinen JW et al. **Fast4DReg – fast registration of 4D microscopy
> datasets.** *Journal of Cell Science* 136, jcs260728 (2023).
> https://doi.org/10.1242/jcs.260728

> Saraiva BM et al. **Efficiently accelerated bioimage analysis with NanoPyx,
> a Liquid Engine-powered Python framework.** *Nature Methods* 22, 283–286
> (2025). https://doi.org/10.1038/s41592-024-02562-6

Fast4DRegPy is released under the MIT license. See
[CHANGELOG.md](CHANGELOG.md) for release notes.
