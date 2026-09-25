# Fast4DRegPy

Fast4DRegPy is a Python implementation of
[Fast4DReg](https://github.com/CellMigrationLab/Fast4DReg), a tool that
corrects drift in 2D and 3D time-lapse microscopy and aligns channels in
multichannel images. Drift is estimated by cross-correlating image
projections, using [NanoPyx](https://github.com/HenriquesLab/NanoPyx) in the
role NanoJ plays in the Fiji plugin.

It reproduces the Fiji Fast4DReg results: on the published test movie, drift
estimates agree with Fiji within 0.005 pixels and the corrected images are
practically identical (see [Validation](docs/validation.md)).

## Installation

Requires Python 3.10–3.13.

```bash
python -m pip install "fast4dregpy @ git+https://github.com/CellMigrationLab/Fast4DRegPy"
```

The package is imported as `fast4dreg`.

## Correcting drift in a time-lapse

```python
from fast4dreg import load_tiff, register_time, save_drift_csv, save_tiff

image = load_tiff("timelapse.tif")          # a NumPy array, here T, Z, Y, X

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

`axes` must describe the array's dimensions, for example `"TYX"`, `"TZYX"` or
`"CTZYX"`. Nothing is guessed from the array shape. For multichannel data, the
drift is measured on `reference_channel` and applied to every channel.

`shifts` has one row per timepoint with the translation applied to that frame,
in the order `(dz, dy, dx)`, in pixels.

As in Fiji, XY drift is corrected first and Z drift is then measured on the
XY-corrected stack.

### Options

| Parameter | Default | Meaning | Fiji equivalent |
| --- | --- | --- | --- |
| `correct_xy`, `correct_z` | `True`, `False` | which drift to correct | xy- / z-drift correction |
| `projection` | `"max"` | `"max"` or `"mean"` projection used for estimation | Projection type |
| `reference` | `"first"` | compare with the first or the previous frame | Reference frame |
| `time_averaging` | `1` | average frames in blocks before estimating (1 = off) | Time averaging |
| `max_expected_drift` | `0` | search radius in pixels; 0 searches the whole image | Maximum expected drift |
| `axial_projection_axis` | `"Y"` | project over Y (`"Y"`) or X (`"X"`) to measure Z drift | Reslice mode Top / Left |
| `crop_output` | `False` | crop to the region covered in every frame | Crop output |
| `extend_z` | `False` | pad Z so shifted content is not cut off | Extend stack to fit |
| `output_dtype` | `"float32"` | `"float32"` or `"input"` (round to the input type) | Save RAM off / on |
| `workers` | `1` | volumes corrected in parallel | — |

In Fiji, XY and Z have separate settings; Fast4DRegPy uses one value for both.
See [Fiji compatibility](docs/fiji_compatibility.md) for details and the few
remaining differences.

## Aligning channels

```python
from fast4dreg import register_channels

corrected, shifts = register_channels(
    image, axes="CZYX", reference_channel=0, correct_z=True
)
```

All channels must be in one array with a `C` axis and a single timepoint.

## Measuring registration quality

`evaluate_registration` computes the metrics used in the Fast4DReg paper
(mSSIM, PSNR, Pearson correlation and the paper's NRMSE) between frames:

```python
from fast4dreg import evaluate_registration, save_validation_csv

rows = evaluate_registration(corrected, axes="TZYX", analysis="max")
save_validation_csv("registration_quality.csv", rows)
```

Also available: `temporal_standard_deviation`, `temporal_color_overlay`,
`line_intensity_profile`, `registration_kymograph` and
`signal_to_background_ratio`.

## Notebook

`notebooks/Fast4DRegApp.ipynb` provides a simple interface: load a TIFF,
register it, plot the drift and save the results. Install the notebook extras
with `pip install "fast4dregpy[notebook] @ git+https://github.com/CellMigrationLab/Fast4DRegPy"`.

## Speed and memory

On the published 25 × 69 × 416 × 416 test movie, registration took 19.5 s
with one worker and 14.9 s with four on a 2-CPU machine; Fiji Fast4DReg took
41 s on the same machine. Peak memory was about 7–10 times the size of
the input (4.4 GB with one worker, 6.2 GB with four).

Results do not depend on `workers`. Drift estimates can vary by about
0.001 pixel between runs unless the environment variable `OMP_NUM_THREADS=1`
is set.

## Citation

If you use Fast4DRegPy, please cite:

> Pylvänäinen JW et al. **Fast4DReg – fast registration of 4D microscopy
> datasets.** *Journal of Cell Science* 136, jcs260728 (2023).
> https://doi.org/10.1242/jcs.260728

> Saraiva BM et al. **Efficiently accelerated bioimage analysis with NanoPyx,
> a Liquid Engine-powered Python framework.** *Nature Methods* 22, 283–286
> (2025). https://doi.org/10.1038/s41592-024-02562-6

## Development

```bash
git clone https://github.com/CellMigrationLab/Fast4DRegPy
cd Fast4DRegPy
python -m pip install -e ".[dev]"
python -m ruff check src tests benchmarks validation
python -m pytest -q
```

See [CHANGELOG.md](CHANGELOG.md) for release notes. Fast4DRegPy is released
under the MIT license.
