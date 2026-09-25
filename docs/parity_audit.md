# Fast4DReg parity audit

Audit date: 2026-09-25 (supersedes 2026-08-08). Full findings:
[`audit_2026-09-25.md`](audit_2026-09-25.md). Full-movie results:
[`full_movie_validation.md`](full_movie_validation.md).

## Sources checked

- Fast4DReg repository at commit `0483ace`: macros `time_estimate+apply.ijm`
  (v2.1) and its v1 predecessor (commit `f1571de`, June 2022), the Java
  plugin (`DriftEstimation_`, `CrossCorrelationMap`, `NJ_FHT`,
  `EstimateShiftAndTilt`, `ApplyDriftCorrection`), `Drift_generator.ijm`.
- ImageJ 1.53t (`ImageProcessor.translate`, `getBicubicInterpolatedPixel`,
  `FloatProcessor.resize`, `resizeLinearly`, `Scaler`).
- NanoPyx 2.1.4 (`_le_drift_calculator.pyx`, `ccm.pyx`,
  `ccm_helper_functions.pyx`, `estimate_shift.py`), recovered from the
  published sdist.
- The original Fiji macro **executed** headless on synthetic data
  (`validation/fiji/`), and the archived Fiji output of the published movie.

## Levels of evidence

| Level | Meaning |
| --- | --- |
| **Fiji-run** | matches output written by the original Fiji macro/ImageJ in this repository's fixtures |
| **Archive** | matches the archived Fiji output of the published movie |
| **Truth** | matches the drift actually added by the published generator |
| **Synthetic** | matches known mathematical shifts only |
| **Untested** | no evidence |

## Functional comparison

| Capability | Status | Evidence |
| --- | --- | --- |
| XY estimation, max/average projection, first/previous reference | Implemented | Fiji-run: <=0.004 px on all macro cases; Archive/Truth: see full-movie report |
| Z estimation, Top (Y) and Left (X) reslice | Implemented | Fiji-run: <=0.004 px; ImageJ-exact axial stretch |
| Axial stretch factor | `round(width/height)` from pixel geometry, as Fiji | Fiji-run; Fiji does not use voxel calibration |
| Time averaging, including a trailing partial block | Implemented with NanoJ semantics | Fiji-run: <=0.0015 px (blocks of 3 and 5 of 12 frames) |
| Bounded search (`max_expected_drift`) | Fiji's centred `2r+1` window; refuses when the peak reaches the window edge | Fiji-run: identical to automatic search inside the bound; Fiji writes NaN/clamps at the edge |
| Z search bound | In stretched axial pixels (Fiji semantics) | Fiji-run |
| Final transform | ImageJ bicubic (Catmull-Rom) two-pass, zero fill (default); SciPy spline optional | Fiji-run and Archive: 99.99% of voxels identical given Fiji's translation |
| Crop output | `crop_output=True`, Fiji rectangle, applied before Z estimation | Fiji-run (crop + extend case) |
| Extend stack to fit | `extend_z=True` | Fiji-run |
| Output dtype | float32 default (Fiji "Save RAM" off); `output_dtype="input"` rounds once | Archive (32-bit then one uint16 conversion) |
| Save RAM (16-bit per-pass rounding) | Not implemented | — |
| Independent XY/Z settings | Missing (shared) | — |
| Channel registration | Implemented; selectable reference channel (Fiji: channel 1) | Synthetic only |
| Multichannel time series | Reference channel estimated, applied to all channels | Synthetic only |
| NanoJ `.njt` drift-table I/O | Missing (format documented in `validation/fiji/`) | — |
| Settings manifest, drift plots, batch runner | Missing | — |
| Bio-Formats / OME metadata | Missing; TIFF only | — |
| Validation metrics (mSSIM, PSNR, PCC, paper NRMSE) | Implemented | archived notebook formulae |

## Known differences

- NanoPyx's Nelder-Mead and NanoJ's ImageJ Minimizer find the subpixel CCM
  peak with different optimisers; measured differences are <=0.004 px.
- NanoPyx 2.1.4 OpenMP reductions are not bit-reproducible across runs with
  more than one OpenMP thread (~0.001 px). Use `OMP_NUM_THREADS=1` when
  bit-reproducibility matters.
- Fast4DRegPy refuses a bounded search whose peak reaches the window edge and
  averaging with fewer than two blocks; Fiji returns NaN/clamped or zero drift.
- XY and Z settings are shared.

## Scientific interpretation

Where a setting is implemented, Fast4DRegPy reproduces the Fiji algorithm,
not just its outcome: drift tables agree with real Fiji runs to a few
thousandths of a pixel, and given the same translation the corrected voxels
are bit-identical after Fiji's uint16 conversion. The published-movie
comparison is reported separately in `full_movie_validation.md`; channel
registration and voxel geometries other than the published movie and the
synthetic fixtures remain untested against Fiji.
