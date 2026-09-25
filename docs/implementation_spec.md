# Implementation specification (0.5.0)

## Aim

Provide the Python implementation of Fast4DReg's projection-based rigid
translation workflow, using NanoPyx for 2D cross-correlation in the same role
that NanoJ serves in the Fiji implementation. The parity target is the Fiji
macro `time_estimate+apply.ijm` v2.1 (Fast4DReg commit `0483ace`) running in
ImageJ 1.x with the Fast4DReg/NanoJ Java plugin.

## Authoritative references

- Fast4DReg repository: <https://github.com/CellMigrationLab/Fast4DReg>
  (`Fast4DReg/macros/*.ijm`, `Fast4DReg/jar-files/src/main/java/`)
- Fast4DReg paper: <https://doi.org/10.1242/jcs.260728>
- Fast4DReg dataset: <https://zenodo.org/records/6534570> (v1),
  <https://zenodo.org/records/7514913> (v2)
- NanoPyx 2.1.4: `nanopyx.core.analysis._le_drift_calculator.DriftEstimator`,
  `nanopyx.core.analysis.ccm`, `nanopyx.core.analysis.estimate_shift`
- ImageJ 1.53t: `ImageProcessor.translate`, `getBicubicInterpolatedPixel`,
  `FloatProcessor.resize`, `resizeLinearly`, `plugin.Scaler`

## Conventions

- Translations are stored as `(dz, dy, dx)` **translations to apply**, the
  same quantity as the Fiji/NanoJ drift table (`ImageProcessor.translate` is
  called with the table values). Positive values move content towards larger
  indices.
- The synthetic generator adds `published[t]` (x, y, z) to frame `t >= 1` and
  leaves frame 0 unchanged, so its ground-truth translation to apply is
  `-published[t]` with frame 0 at zero.

## Algorithm mapping

| Step | Fiji Fast4DReg | Fast4DRegPy |
| --- | --- | --- |
| Axes | ImageJ hyperstack dimensions | explicit `axes`, normalised to `CTZYX` |
| XY projection | `Z Project` Max/Average over Z per frame | `np.max` / `np.mean` over Z of the reference channel |
| Even square | `NJ_FHT.makeEvenSquare`: centre crop to the largest even square | same crop |
| Correlation map | NanoJ DHT CCM, normalised to Pearson range, `(N-1)^2` | NanoPyx `calculate_ccm` (FFT), same normalisation; zero shift at index `N/2-1` in both |
| Search window (`r>0`) | centred `2r+1` crop of the CCM | same centred window (not NanoPyx's `2r` slice) |
| Subpixel peak | ImageJ `Minimizer` on bicubic CCM; NaN within 1 px of the border | NanoPyx `GetMaxOptimizer` (Nelder-Mead on Catmull-Rom); **error** when the integer peak is within 1 px of a bounded window's edge |
| Reference | first: raw frame 1 vs every block; previous: block `n-1` vs block `n` | same |
| Time averaging | blocks of `k` frames, trailing partial block kept; block drift minus block 0; `resizeLinearly` to frames (block `b` at frame `b(N-1)/(B-1)`) | same (not NanoPyx's averaged-block reference, dropped block and cubic knots) |
| XY apply | per Z plane, `ImageProcessor.translate` BICUBIC (Catmull-Rom `a=0.5`, bilinear edge rule, 0 outside) on 32-bit data | `interpolation="imagej"` (default): exact NumPy port; `"scipy"`: `ndimage.shift` spline |
| Crop output | after XY apply, crop to `(ceil(max dx), ceil(max dy))` with size `W - ceil(max dx) + ceil(min dx)` etc. (extrema include 0) | `crop_output=True`, `fiji_crop_bounds()`; the crop precedes Z estimation as in Fiji |
| Z projection | `Reslice` Top (planes X x Z per Y) or Left (Y x Z per X), `avoid` interpolation, then Max/Average over the resliced stack | `np.max`/`np.mean` over Y (`axial_projection_axis="Y"`) or X (`"X"`) of the XY-corrected float32 stack |
| Axial stretch | `round(width/height)` from **pixel geometry** (calibration is not used); `Scale... y=s interpolation=Bicubic` | same factor; exact port of `FloatProcessor.resize` (centre-mapped, displacement scale exactly `s`) |
| Z estimation | Estimate Drift on the stretched movie; Y column divided by `s` | same; `max_expected_drift` is therefore in stretched axial pixels for Z |
| Z apply | per axial plane, `translate(0, dz)` BICUBIC; optional `Canvas Size` padding `2*max(-floor(min dz), ceil(max dz))`, centred | same two-pass order; `extend_z=True`, `fiji_z_padding()` |
| Output | 32-bit (Save RAM off) or input depth with per-pass rounding (Save RAM on) | float32 by default; `output_dtype="input"` rounds half-up and clips once |
| Channels | channels reordered into time; always channel 1 as reference | `register_channels` with selectable `reference_channel` |

## Deliberate differences from Fiji

- **Settings are shared between XY and Z** (projection, reference, time
  averaging, maximum drift). Fiji exposes them separately.
- **Bounded windows refuse instead of failing silently.** Fiji writes NaN or a
  value clamped to +/-(r-1) when the correlation peak is within one pixel of
  the window border; Fast4DRegPy raises `ValueError`.
- **Time averaging with fewer than two blocks is rejected.** Fiji reports zero
  drift for every frame.
- **Save RAM (16-bit) arithmetic is not reproduced.** Integer output is rounded
  once, not after each pass.
- The NanoPyx and NanoJ subpixel optimisers differ; measured agreement on real
  Fiji output is at most 0.004 px (see `tests/test_fiji_macro_parity.py`).

## Explicit failure behaviour

- Axis order, image values, indices, enums, booleans, integer ranges, shifts,
  interpolation options and output paths are validated before work begins.
- Settings that Fiji or NanoPyx would ignore or change silently are rejected
  (search windows too large for the image, fewer than two averaging blocks,
  peaks at the window edge, `interpolation_order` or a non-zero `cval` with
  ImageJ interpolation, `crop_output` without XY correction).
- The selected NanoPyx backend is never changed after failure. `backend` only
  selects the DriftEstimator implementation for unbounded, unaveraged
  estimation; both NanoPyx 2.1.4 backends share the same CCM code.
- Files are never overwritten without `overwrite=True`.
- Z correction is never inferred from shape; callers must enable it.

## Concurrency and reproducibility

- `workers` is an explicit positive integer; independent volume transforms run
  in a thread pool and write into disjoint output views. Transform results are
  bit-identical for any worker count.
- NanoPyx 2.1.4 uses OpenMP reductions; with more than one OpenMP thread,
  estimates can differ by ~0.001 px between runs. Use `OMP_NUM_THREADS=1` for
  bit-reproducible estimates.

## Exclusions

No true 3D FFT, rotation correction, lazy loading, Zarr, GPU-specific code,
local elastic channel warping, or automatic dimension inference.
