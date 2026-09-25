# Zenodo XYZT Fiji parity fixture

This directory contains a compact derivative of the published Fast4DReg
large-drift synthetic dataset together with pixels from the corresponding
archived Fiji Fast4DReg-corrected output.

## Sources

- Zenodo record: https://zenodo.org/records/7514913
- Requested archival record: https://zenodo.org/records/6534570
- Archive: `2-Synthetic-drift-dataset.zip`
- Raw member:
  `2.1-Synthetic-drift-files/2.1.2-LargeDrift_original.tif`
- Fiji reference member:
  `2.2-Synthetic-drift-expected-results/2.2.1-LargeDrift_F4DReg.tif`

## Fixture design

The fixture keeps frames 0 and 6 and the complete Z dimension. To preserve the
geometry used by the original Fiji Z-estimation workflow, the raw fixture keeps
the **full 416-pixel X dimension** and crops only Y. The archived Fiji reference
keeps its complete X extent and the matching central Y region.

This matters because Fast4DReg derives the axial projection stretch factor from
the resliced projection geometry before cross-correlation. Cropping the lateral
axis would change that factor and therefore would not test the same algorithm.

The raw and Fiji regions are linked by template matching frame 0 after maximum-Z
projection. Exact coordinates, checksums, source dimensions, selected timepoints
and published drift values are recorded in `manifest.json`.

No intensity normalization, denoising or synthetic regeneration is applied.

## Purpose

The fixture is used to test:

1. recovery of the published X, Y and Z drift between frames 0 and 6;
2. end-to-end agreement of corrected pixels with the archived Fiji Fast4DReg
   output;
3. the axial rescaling / shift-rescaling path in Fast4DRegPy.

It is intentionally small enough for normal GitHub CI while retaining the
spatial geometry needed for the Z algorithm.
