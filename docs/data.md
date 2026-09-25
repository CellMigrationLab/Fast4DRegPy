# Reference datasets

The data associated with Fast4DReg are archived on Zenodo.

## Requested archival record

- Zenodo: <https://zenodo.org/records/6534570>
- DOI: <https://doi.org/10.5281/zenodo.6534570>
- Title: **Fast4DRegistration**
- Version: 1.0

This is the dataset location requested for the Fast4DReg Python repository and
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
