# Fast4DReg parity audit

Audit date: 2026-08-08

## Sources checked

- [Fast4DReg paper](https://doi.org/10.1242/jcs.260728), especially the
  Algorithms, Metrics, synthetic-drift, noise, and acquired-data sections.
- [Original repository at commit 0483ace](https://github.com/CellMigrationLab/Fast4DReg/tree/0483ace1ac5b8ee0e3938d00c303104109897803).
- Fiji macros `time_estimate+apply.ijm`, `time_apply.ijm`,
  `channel_estimate+apply.ijm`, and `channel_apply.ijm`.
- Archived `scripts/registration_assesment_notebook.ipynb` and
  `scripts/Drift_generator.ijm`.
- ImageJ `ZProjector.StandardDeviation`, which uses sample standard deviation
  (`n - 1`).

## Functional comparison

| Capability | Python 0.4 status | Important difference or evidence |
| --- | --- | --- |
| XYT/XYZT time registration | Implemented | Explicit axes are required instead of inferred ImageJ dimensions. |
| XYC/XYZC channel registration | Implemented | Channels are compared to a selectable reference channel. |
| Maximum and average projections | Implemented | One shared projection setting is currently used for XY and Z. |
| First-frame and previous-frame references | Implemented | One shared reference setting is currently used for XY and Z. |
| Time averaging | Implemented with strict bounds | Values NanoPyx would silently clamp, or that cannot support its cubic interpolation, are rejected. Fiji equivalence is not yet proven. |
| Maximum expected drift | **Partial** | `0 = auto` is supported and is the parity-safe default. For nonzero radius `r`, Fiji uses a `2r+1` CCM crop while NanoPyx 2.1.4 currently slices `2r`; bounded-window parity is not yet exact. |
| NanoPyx backend | Explicit CPU backend | `threaded` or `unthreaded` is called directly; LiquidEngine fallback dispatch is bypassed. |
| Subpixel translation | Implemented | NanoPyx estimation plus SciPy cubic interpolation by default; Fiji uses ImageJ bicubic, so exact pixel parity remains untested. |
| Sequential XY correction then Z estimation | Implemented | A regression test verifies that the axial projection is generated from the XY-corrected volume. Fiji fixture parity is still required. |
| Axial reslice scaling | **Validated on one published XYZT case** | The current geometry-derived axial stretch and post-estimation Z rescaling recover the published XYZ displacement within 0.75 pixels and produce corrected pixels with Pearson >0.98 against the archived Fiji Fast4DReg output for frames 0 and 6 of the large-drift dataset. Broader calibration/interpolation parity remains to be tested. |
| Independent XY/Z settings | Missing | Fiji exposes projection, averaging, reference, and maximum drift separately for XY and Z. |
| Crop black borders | Missing | Fiji crops using extrema from the XY drift table. |
| Extend Z stack to fit | Missing | Fiji pads Z using extrema from the Z drift table. |
| RAM-saving/virtual-stack mode | Missing | Current API materializes NumPy arrays in memory; this remains deferred until parity fixtures pass. |
| Fiji settings CSV | Missing | Python saves a portable drift CSV but no complete run manifest. |
| NanoJ NJT drift-table compatibility | Missing | Signs, column names, and round-trip compatibility require Fiji fixtures. |
| Drift plots | Partial | Notebook displays a plot but the API does not save publication-ready plots. |
| Batch file processing | Missing | The array API can be called in a loop; no batch runner or result-folder convention exists. |
| Bio-Formats input and metadata | Missing | TIFF is supported; OME metadata and arbitrary microscopy formats are not preserved. |
| Headless use | Implemented | The Python API is directly callable without the notebook. |
| mSSIM, PSNR, PCC | Implemented | Pair normalization and metric parameters match the archived notebook. |
| Historical paper NRMSE | Implemented as `paper_nrmse` | The archived code uses `sqrt(mean(abs(error)))`, not conventional NRMSE. |
| Conventional NRMSE | Implemented as `standard_nrmse` | Added to avoid perpetuating the historical label. |
| Temporal standard-deviation projection | Implemented | Uses `ddof=1`, matching ImageJ. |
| Three-frame color overlay | Implemented | Blue, green, then red, as described in the paper. |
| Line profiles and kymographs | Implemented | Available as array-returning validation helpers. |
| Paper SNR definition | Implemented | Mean signal divided by mean background using supplied masks. |
| Synthetic drift/noise generator | Missing | Original uses quadratic XYZ drift, optional drift noise, background homogenization, and Poisson noise. |
| Reference regression dataset | **XY + XYZT Fiji fixtures implemented** | The 1.18 MB XY fixture checks the published lateral drift trend. A second ~28.1 MB XYZT fixture uses frames 0 and 6 from the same raw dataset plus the archived `2.2.1-LargeDrift_F4DReg.tif` output to test XYZ shifts and corrected-pixel agreement directly. |
| True 3D correlation, rotation, shear, scaling | Deliberately deferred | The paper describes translation-only projection registration; current project scope remains projection-only. |

## Scientific interpretation

Fast4DRegPy is the Python implementation of Fast4DReg. Sequential XY-then-Z
estimation, the paper's validation measurements, and one direct published XYZT
comparison against archived Fiji Fast4DReg output are now covered by regression
tests. The current axial path is therefore supported by direct parity evidence
for that case, but bounded drift-window semantics, broader voxel-calibration
coverage, interpolation-edge behaviour, cropping/extension, and full drift-table
compatibility remain open parity tasks.
