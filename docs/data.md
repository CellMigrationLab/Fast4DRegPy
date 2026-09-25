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
large-drift functions reported in the Fast4DReg paper and verifies that
registration improves frame-to-reference alignment. The published large-drift
parameters are `x1=0.2`, `x2=0.1`, `y1=1.5`, `y2=-0.03`,
`z1=-0.6`, `z2=0`, with drift-noise amplitude `A=0.1`.

This XY projection fixture does **not** establish axial parity. A separate
XYZT fixture is still needed to validate Fiji's calibrated axial reslice and
Z-drift rescaling.
