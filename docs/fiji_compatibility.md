# Fiji compatibility

Fast4DRegPy follows the Fiji macro `time_estimate+apply.ijm` (Fast4DReg v2.1)
step by step, and uses the same interpolation as ImageJ. With the same
settings it gives the same drift table and the same corrected images, up to
small subpixel differences (below 0.005 pixels on the published test data).

## Settings

| Fiji dialog | Fast4DRegPy | Notes |
| --- | --- | --- |
| xy-drift correction | `correct_xy=True` | |
| z-drift correction | `correct_z=True` | needs a Z axis with at least two slices |
| Projection type: Max / Average Intensity | `projection="max"` / `"mean"` | one value for XY and Z |
| Reference frame: first / previous | `reference="first"` / `"previous"` | one value for XY and Z |
| Time averaging | `time_averaging` | 1 disables; must leave at least two blocks |
| Maximum expected drift | `max_expected_drift` | 0 = whole image; for Z the value is in stretched axial pixels, as in Fiji |
| Reslice mode: Top / Left | `axial_projection_axis="Y"` / `"X"` | |
| Crop output | `crop_output=True` | |
| Extend stack to fit | `extend_z=True` | |
| Save RAM | `output_dtype="input"` | see differences below |

The drift table columns map as follows: Fiji `X-Drift` is `dx`, `Y-Drift` is
`dy`, and the Y-Drift of the Z table is `dz`. Both store the translation that
is applied to each frame.

## How the registration works

1. Each frame is projected over Z, and the XY drift is measured by
   cross-correlation. Frames that are not square are centre-cropped to the
   largest even square for this step.
2. The XY correction is applied to every Z plane.
3. With "Crop output", the stack is cropped to the area covered by every frame.
4. The XY-corrected stack is projected over Y (Top) or X (Left), giving an
   image with Z as one axis. That axis is stretched by `round(lateral size /
   number of slices)`, the Z drift is measured, and the result is divided by
   the same factor. Like Fiji, this uses pixel counts, not voxel sizes.
5. The Z correction is applied, optionally in a padded stack.

Translations use ImageJ's bicubic interpolation, and pixels moved in from
outside the image are set to 0. To use SciPy spline interpolation instead,
pass `interpolation="scipy"` (with `interpolation_order` and `cval`); this does
not match Fiji pixel for pixel.

## Differences

- **Separate XY and Z settings.** Fiji lets projection, reference, time
  averaging and maximum drift differ between XY and Z. Fast4DRegPy uses the
  same value for both.
- **Drift at the search limit.** When the drift reaches the edge of the
  `max_expected_drift` window, Fiji writes NaN or a clipped value to the drift
  table. Fast4DRegPy raises an error; increase `max_expected_drift` or use 0.
- **Time averaging that leaves one block.** Fiji reports zero drift for every
  frame; Fast4DRegPy raises an error.
- **Save RAM.** Fiji rounds to the input bit depth after the XY step and again
  after the Z step. `output_dtype="input"` rounds once at the end, which can
  differ by one grey level.
- **Channel registration.** Fiji always uses the first channel as reference;
  `register_channels` lets you choose it with `reference_channel`.

## Not supported

Bio-Formats files (only TIFF is read and written), the NanoJ `.njt` drift-table
format, batch processing of folders, and the RAM-saving virtual-stack mode.
Voxel sizes are not written to the output TIFF.
