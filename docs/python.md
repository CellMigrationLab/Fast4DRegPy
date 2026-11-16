# Python guide

[⬅️ Documentation index](index.md)

Install the package (see [Installation](installation.md)). The distribution is
called `fast4dregpy`; the Python package is imported as `fast4dreg`.

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
frame, in `(dz, dy, dx)` pixel order: the same quantity as Fiji's drift table
(`X-Drift` = `dx`, `Y-Drift` = `dy`, Z table `Y-Drift` = `dz`). With
multichannel time series, drift is measured on `reference_channel` and the
same translation is applied to every channel.

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
| `output_dtype` | `"float32"` | return float32 or explicitly round to the input dtype (`"input"`) |
| `backend` | `"threaded"` | NanoPyx estimator backend for the direct estimation path |
| `workers` | `1` | number of independent volumes transformed concurrently; never changes the result |

What each setting does, in words: [Workflow and settings](workflow.md#the-settings).

The `unthreaded` NanoPyx backend is available when `time_averaging=1` and
`max_expected_drift=0`. Fiji-compatible time averaging and bounded searches use
NanoPyx's compiled correlation primitives directly, so requesting
`backend="unthreaded"` with either of those modes raises an error rather than
silently ignoring the setting.

Fiji exposes separate XY and Z values for projection, reference, averaging and
search radius. Fast4DRegPy currently uses one value for both. See
[Fiji compatibility](fiji_compatibility.md) for the exact mapping and the
remaining differences.

### Measure and apply separately

`register_time` is `estimate_time_drift` followed by `apply_drift`. Call them
separately to measure the drift on one channel or file and apply it to
another, as Fiji's `time_apply` does:

```python
from fast4dreg import apply_drift, estimate_time_drift, load_drift_csv

shifts = estimate_time_drift(reference_movie, axes="TZYX", correct_z=True)
other_corrected = apply_drift(other_channel, shifts, axes="TZYX")

shifts = load_drift_csv("timelapse_drift.csv")  # a table saved earlier
```

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
expects a single timepoint. `estimate_channel_shifts` and
`apply_channel_shifts` split the two steps, as `channel_estimate+apply` and
`channel_apply` do in Fiji.

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
projections (`temporal_standard_deviation`), three-frame overlays
(`temporal_color_overlay`), line profiles, kymographs
(`registration_kymograph`) and signal-to-background ratios.

## Reproducible numbers

NanoPyx sums in parallel, so drift estimates can differ by about 0.001 pixel
between runs. Set `OMP_NUM_THREADS=1` before importing `fast4dreg` to get the
same numbers every time. `workers` never changes the result.
