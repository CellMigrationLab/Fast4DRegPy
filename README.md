# Fast4DRegPy

**Fast4DRegPy** is the Python implementation of the Fast4DReg method for
projection-based drift correction and channel registration of 2D and 3D
microscopy data. It uses
[NanoPyx](https://github.com/HenriquesLab/NanoPyx) for cross-correlation in
the same architectural role that NanoJ plays in the original
[Fast4DReg Fiji implementation](https://github.com/CellMigrationLab/Fast4DReg).

This project is distinct from
[`napari-fast4dreg`](https://github.com/COSC-Lab/napari-fast4dreg), a separate
Python interpretation of Fast4DReg with a napari plugin. The goal here is a
direct, testable reimplementation of the original Fast4DReg workflow and
algorithm, with an API for scripts, notebooks, pipelines and headless use.

| Name | Value |
| --- | --- |
| Project / repository | Fast4DRegPy |
| Distribution | `fast4dregpy` |
| Python import | `fast4dreg` |

## Validation status

The parity target is the original Fiji macro `time_estimate+apply.ijm` (v2.1).
What has been validated, and how:

| Evidence | Result |
| --- | --- |
| **Real Fiji runs.** The original macro was run headless in ImageJ 1.53t on a synthetic movie for 8 settings: default, previous + average, Left reslice, time averaging including a partial block, bounded windows, crop + extend (`tests/test_fiji_macro_parity.py`). | Drift tables agree to ≤0.004 px; corrected stacks Pearson > 0.9999 with identical geometry |
| **ImageJ interpolation.** `translate` and `Scale` outputs from ImageJ (`tests/test_imagej_parity.py`). | Equal to float32 rounding |
| **Published ground truth**, compact fixtures (`tests/test_zenodo_*.py`). | XY ≤0.071 px on frames 6/12/18/24; frame-6 XYZ within 0.1 px |
| **Archived Fiji output**, frame 6 of the published movie. | Given Fiji's translation, 99.99% of voxels are bit-identical after uint16 conversion; Fast4DRegPy's own estimate is within 0.005 px of Fiji and the end-to-end Pearson is 0.9999989 |
| **Complete published movie**, 25 frames x 69 planes (checksum-verified Zenodo data, run in GitHub Actions). | Drift within 0.11 px of the added ground truth on every frame (Fiji: same 0.11 px); within 0.005 px of Fiji's applied translations; corrected volumes Pearson ≥ 0.9999993 and SSIM ≥ 0.9999997 vs archived Fiji on all 25 frames. Report: [`docs/full_movie_validation.md`](docs/full_movie_validation.md) |
| Archived output crop. | Fiji's published crop formula gives 277 x 354; the archived file is 275 x 352 at the same origin (unexplained; documented) |
| Channel registration, other voxel geometries, Fiji "Save RAM" mode. | Not yet compared with Fiji |

The audit behind these results, including the defects fixed in 0.5.0, is in
[`docs/audit_2026-09-25.md`](docs/audit_2026-09-25.md). The per-feature
comparison is in [`docs/parity_audit.md`](docs/parity_audit.md).

## Installation

Python 3.10–3.13 (CI tests all four):

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "fast4dregpy @ git+https://github.com/CellMigrationLab/Fast4DRegPy"
```

For development:

```bash
git clone https://github.com/CellMigrationLab/Fast4DRegPy
cd Fast4DRegPy
python -m pip install -e ".[dev]"
```

NanoPyx is pinned to 2.1.4, the version whose correlation code has been
validated.

## Supported inputs

| Task | Expected layout | Examples |
| --- | --- | --- |
| Time registration | A time series with explicit `T` | `TYX`, `TZYX`, `CTZYX`, `TZCYX` |
| Channel registration | Multiple channels, one timepoint | `CYX`, `CZYX` |

Axis strings are mandatory and must match the array dimensions. The library
never guesses whether a stack dimension represents channels, Z or time.
Estimated translations are always stored as `(dz, dy, dx)` and mean
"translation to apply". This is the same quantity as the Fiji/NanoJ drift
table.

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
    workers=4,
)

save_tiff("timelapse_registered.tif", corrected, axes="TZYX")
save_drift_csv("timelapse_drift.csv", shifts)
```

- **Order of operations (as in Fiji):** XY drift is estimated from a Z
  projection and applied; the axial projection (over Y for
  `axial_projection_axis="Y"` = Fiji "Top", over X for `"X"` = "Left") is then
  built from the XY-corrected stack and stretched by Fiji's integer factor
  `round(lateral/axial)`; the Z drift is estimated and divided by that factor.
  Like Fiji, the stretch factor comes from pixel geometry, not from voxel
  calibration. `correct_z=False` is the default.
- **Interpolation.** The default `interpolation="imagej"` reproduces Fiji
  exactly: ImageJ bicubic (Catmull-Rom) translation of every Z plane and then
  every axial plane, with zero fill outside the image. `interpolation="scipy"`
  (with `interpolation_order` and `cval`) uses a single SciPy spline shift
  instead; it does not match Fiji voxel for voxel.
- **Output.** float32 by default, as Fiji with "Save RAM" off.
  `output_dtype="input"` rounds half-up and clips once.
- **Cropping and Z extension** are off by default. `crop_output=True`
  reproduces Fiji's "Crop output", including its effect on Z estimation, since
  Fiji crops before building the axial projection. `extend_z=True` reproduces
  "Extend stack to fit". `fiji_crop_bounds()` and `fiji_z_padding()` return
  the same rectangle and padding for other uses.
- **Time averaging** (`time_averaging > 1`) follows NanoJ: blocks of frames,
  the trailing partial block kept, each block compared with the raw first
  frame, and linear interpolation of the block drift. At least two blocks are
  required.
- **Bounded search** (`max_expected_drift = r > 0`) uses Fiji's centred
  `2r+1` correlation window. When the correlation peak reaches the edge of the
  window, Fiji writes NaN or a clamped value; Fast4DRegPy raises `ValueError`
  instead. For Z the radius is in stretched axial pixels, as in Fiji.
  `max_expected_drift=0` (automatic) searches the whole image.
- **Shared XY/Z settings.** Fiji exposes projection, reference, averaging and
  maximum drift separately for XY and Z; Fast4DRegPy currently uses one value
  for both.
- `backend` (`"threaded"` or `"unthreaded"`) selects the NanoPyx
  DriftEstimator implementation. It is called directly and never retried with
  another backend.

For multichannel time series, supply `CTZYX` (or another explicit ordering)
and choose `reference_channel`. The estimated transform is applied identically
to every channel at each timepoint.

## Channel registration

```python
from fast4dreg import register_channels

corrected, shifts = register_channels(
    image, axes="CZYX", reference_channel=0, projection="max", correct_z=True
)
```

Separate channel files must be combined into one `CZYX` array first.

## Performance and reproducibility

`workers` controls how many volumes are transformed concurrently. It defaults
to `1` and is never inferred. On a 4-CPU container, the full published
geometry (25 x 69 x 416 x 416) registers in 64 s with `workers=1` and 22.5 s
with `workers=4` ([`docs/performance.md`](docs/performance.md)). Transform
results are identical for any worker count.

NanoPyx 2.1.4's OpenMP reductions make drift estimates differ by ~0.001 px
between runs when more than one OpenMP thread is used. Set
`OMP_NUM_THREADS=1` for bit-reproducible estimates.

## Registration validation metrics

`fast4dreg.validation` reproduces the paper's assessment: mSSIM, PSNR,
Pearson correlation, the archived notebook's value labelled NRMSE (kept as
`paper_nrmse`, which is `sqrt(mean(abs(error)))`), a conventional
`standard_nrmse`, temporal standard-deviation projections (ImageJ `n-1`),
three-frame overlays, line profiles, kymographs and the paper's SNR.

```python
from fast4dreg import evaluate_registration, save_validation_csv

rows = evaluate_registration(corrected, axes="TZYX", reference="first",
                             analysis="slice", z_index=8)
save_validation_csv("registration_validation.csv", rows)
```

## Reference data and validation tooling

The Fast4DReg data are archived on Zenodo (record
[6534570](https://zenodo.org/records/6534570); expanded version
[7514913](https://zenodo.org/records/7514913), CC BY 4.0). Compact fixtures
derived from them are committed with their provenance, see
[`docs/data.md`](docs/data.md). Two further validation tools live in
[`validation/`](validation/README.md):

- a headless runner for the original Fiji macro, used to generate the
  real-Fiji fixtures;
- a full-movie validation that downloads the published movie (pinned
  checksum), registers all frames and writes CSV/JSON/PNG results. It is
  available as the manually dispatched **full-movie validation** workflow.

## Development

```bash
python -m ruff check src tests benchmarks validation
python -m pytest -q
```

The tests call the real NanoPyx 2.1.4; do not mock it or skip integration
tests. Save functions refuse to overwrite existing files unless
`overwrite=True`.

## Current non-goals

True 3D correlation, rotation correction, Dask/Zarr, GPU selection, non-rigid
registration, and a napari plugin or desktop installer (see
`napari-fast4dreg`).

## Citation

If you use Fast4DRegPy, cite the Fast4DReg paper and NanoPyx/NanoJ:

> Pylvänäinen JW et al. **Fast4DReg – fast registration of 4D microscopy
> datasets.** *Journal of Cell Science* 136, jcs260728 (2023).
> https://doi.org/10.1242/jcs.260728

> Saraiva BM et al. **Efficiently accelerated bioimage analysis with NanoPyx,
> a Liquid Engine-powered Python framework.** *Nature Methods* 22, 283–286
> (2025). https://doi.org/10.1038/s41592-024-02562-6
