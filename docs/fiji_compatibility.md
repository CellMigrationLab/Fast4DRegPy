# Fiji compatibility

Fast4DRegPy follows the registration sequence in the Fiji Fast4DReg
`time_estimate+apply.ijm` macro and uses ImageJ-compatible interpolation for
the default transform path.

On the complete published large-drift movie, the largest difference between
the Fast4DRegPy and fresh Fiji drift tables was 0.0047 pixels. The lowest
whole-volume Pearson correlation between their corrected outputs was
0.9999993. See [validation.md](validation.md) for the measurements and the
exact test conditions.

## Settings

| Fiji dialog | Fast4DRegPy | Notes |
| --- | --- | --- |
| xy-drift correction | `correct_xy=True` | |
| z-drift correction | `correct_z=True` | requires at least two Z slices |
| Projection type: Max / Average Intensity | `projection="max"` / `"mean"` | one shared value for XY and Z |
| Reference frame: first / previous | `reference="first"` / `"previous"` | one shared value for XY and Z |
| Time averaging | `time_averaging` | 1 disables averaging |
| Maximum expected drift | `max_expected_drift` | 0 uses the full correlation map |
| Reslice mode: Top / Left | `axial_projection_axis="Y"` / `"X"` | |
| Crop output | `crop_output=True` | |
| Extend stack to fit | `extend_z=True` | |
| Save RAM | `output_dtype="input"` | similar intent, but not bit-equivalent; see below |

Fiji's drift-table columns correspond to Fast4DRegPy as follows:
`X-Drift = dx`, `Y-Drift = dy`, and the Z-table `Y-Drift = dz`. Both
represent the translation applied to the image.

## Registration sequence

For time-lapse data Fast4DRegPy follows the same order as Fiji:

1. Project each volume over Z and estimate XY drift.
2. Apply XY correction with ImageJ-compatible bicubic interpolation.
3. If requested, crop to the common XY overlap.
4. Build an axial projection from the XY-corrected stack.
5. Stretch the axial dimension by `round(lateral size / number of Z slices)`,
   estimate Z drift, then divide the measured axial displacement by that factor.
6. Apply the Z correction, with optional symmetric Z padding.

Rectangular correlation inputs are centre-cropped to the same even-square
geometry used by Fiji/NanoPyx. Pixels brought in from outside the image are
zero-filled.

The axial stretch factor is based on image dimensions, as in the Fiji macro.
It is not calculated from physical voxel spacing.

## Deliberate differences

**One set of XY/Z estimation settings.** Fiji can use different projection,
reference, averaging and search settings for XY and Z. Fast4DRegPy currently
uses one value for both.

**Search-window failures.** Fiji can return NaN or a clipped value when a
correlation peak reaches the edge of `max_expected_drift`. Fast4DRegPy raises
an error instead, because returning a plausible but unreliable shift would be
harder to detect.

**Degenerate time averaging.** If averaging leaves fewer than two blocks, Fiji
reports zero drift. Fast4DRegPy raises an error.

**Backend selection.** `backend="threaded"` and `"unthreaded"` select the
NanoPyx DriftEstimator implementation when `time_averaging=1` and
`max_expected_drift=0`. Fiji-compatible averaging and bounded-search modes
use NanoPyx's compiled correlation primitives directly. In those modes,
`backend="unthreaded"` is rejected rather than silently ignored.

**Save RAM.** Fiji's RAM-saving path converts back to the input bit depth after
the XY step and again after the Z step. `output_dtype="input"` converts once
at the end, so individual grey values can differ.

**Channel reference.** Fiji channel registration uses the first channel.
Fast4DRegPy lets the caller choose `reference_channel`.

## Not yet covered

The current Fiji parity tests do not cover channel registration, Fiji's
RAM-saving mode, or a second 3D dataset with a substantially different
lateral-to-Z geometry. Bio-Formats input, NanoJ `.njt` drift-table I/O,
folder-level batch processing and virtual-stack processing are also not
implemented.

For SciPy interpolation instead of ImageJ-compatible interpolation, use
`interpolation="scipy"`. That is an explicit alternative and is not expected
to match Fiji pixel for pixel.
