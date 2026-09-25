# Reference datasets

The data associated with Fast4DReg are archived on Zenodo.

## Requested archival record

- Zenodo: <https://zenodo.org/records/6534570>
- DOI: <https://doi.org/10.5281/zenodo.6534570>
- Title: **Fast4DRegistration**
- Version: 1.0

This is the dataset location requested for the Fast4DRegPy repository and
should remain documented even if newer versions are published.

Zenodo currently marks this record as having a newer version. The linked
version 2.0 record is:

- Zenodo: <https://zenodo.org/records/7514913>
- DOI: <https://doi.org/10.5281/zenodo.7514913>

## Contents relevant to this implementation

The archive provides the material needed to validate the Python implementation
against the published Fast4DReg workflow, including synthetic drift data,
biological time-series data, channel-alignment examples, reference/expected
outputs, videos, and the original software archive. Version 2.0 also contains
additional noisy-image and biological datasets.

The complete archive is large (the current expanded record is tens of
gigabytes), so it should not be committed to this repository. Automated parity
tests should instead use a documented, redistribution-safe subset or a small
fixture derived from the archive, with checksums and provenance recorded.

## Intended use in the test suite

The parity fixture should record:

1. the exact Zenodo record and source filename;
2. the checksum of every extracted input fixture;
3. the Fiji/Fast4DReg version or commit used to generate reference results;
4. all XY and Z registration settings;
5. the reference drift tables and corrected outputs;
6. numerical tolerances used for the Python comparison.

This is particularly important for Z registration because the Fiji workflow
rescales the axial reslice before drift estimation and rescales the measured
Z drift afterward. That behavior is not yet reproduced exactly by version
0.4.0 of the Python implementation.


## Committed regression fixture

The repository contains a compact fixture derived directly from the published
large-drift synthetic dataset:

- source archive: `2-Synthetic-drift-dataset.zip`
- source member: `2.1.2-LargeDrift_original.tif`
- source series: `TZYX`, shape `25 x 69 x 416 x 416`, `uint16`
- selected frames: `0, 6, 12, 18, 24`
- derivation: full-field maximum-intensity projection over Z only
- fixture: `tests/data/zenodo_synthetic/large_drift_xy_max.npz`
- fixture SHA-256:
  `c81c373b52d094d2da5cbe5df723b91b3eca180848d48dd02dfb2de7ec42e5ff`

No spatial crop, intensity normalization, denoising, or synthetic regeneration
is used. The fixture therefore exercises Fast4DRegPy on image pixels derived
from the published dataset while keeping normal Git/CI use practical.

The regression test compares the estimated lateral translations with the
published per-frame drift values for the selected frames and verifies that
registration improves frame-to-reference alignment. These values are stored
explicitly in the fixture manifest rather than regenerated from nominal
polynomial coefficients.

## XYZT Fiji parity fixture

A second fixture now tests the axial path directly against the archived Fiji
Fast4DReg output:

- source raw member: `2.1.2-LargeDrift_original.tif`
- Fiji reference member: `2.2.1-LargeDrift_F4DReg.tif`
- selected frames: 0 and 6
- complete Z dimension retained
- raw X dimension retained at the full 416 pixels so the Fiji axial-geometry
  scale factor remains 6
- compact fixture: `tests/data/zenodo_xyzt/large_drift_xyzt_fiji_reference.npz`
- fixture size: approximately 28.1 MB

The fixture stores the corresponding raw and archived Fiji-corrected volumes,
with ROI mapping derived from frame-0 maximum-Z template matching. The regression
test requires all three estimated translation components to match the published
relative XYZ drift within 0.75 pixels and requires the registered frame to agree
with the archived Fiji output at Pearson correlation >0.98.

This establishes direct parity evidence for the current axial workflow on one
published XYZT case. It does not prove universal equivalence for all voxel
calibrations, interpolation edge cases, time-averaging settings, or bounded
drift windows.
