# Codex implementation backlog

Work top-to-bottom within each priority. Keep changes small and add tests for
every acceptance criterion. Read `docs/parity_audit.md` first.

## P0 — establish scientific parity

Completed in version 0.3: sequential XY correction before Z estimation,
explicit NanoPyx backend execution without fallback, strict input validation,
float32 transform output by default, and paper-compatible validation helpers.

Completed in version 0.4: explicit bounded parallel volume transformations,
parallel XY preparation for Z estimation, direct writes into preallocated
output views, serial/parallel equality tests, and a reproducible transform
benchmark. Lazy storage and automatic ROI selection remain deferred because
they change the execution or estimation model before Fiji parity is established.

### 1. Extend Fiji reference fixtures

Two published-data fixtures are now committed from Zenodo record 7514913
(archival record 6534570):

- an XY max-Z fixture spanning five timepoints;
- an XYZT fixture using frames 0 and 6 together with the archived
  `2.2.1-LargeDrift_F4DReg.tif` output.

The XYZT regression checks the published relative XYZ displacement within
0.75 pixels and corrected-pixel agreement with Fiji at Pearson >0.98.

Remaining fixture work:

- add a second XYZT case with different voxel geometry/calibration;
- record the original Fiji settings/drift tables directly if available;
- add edge cases for crop/extend-Z and bounded drift windows.

### 2. Broaden axial parity coverage

The current geometry-derived axial stretch / shift-rescaling path now passes
one direct published Fiji XYZT comparison. Broaden this validation rather than
treating one dataset as universal proof.

Acceptance criteria:

- API can represent explicit voxel spacing where geometry alone is insufficient;
- isotropic and anisotropic synthetic tests recover known subpixel Z shifts;
- at least one additional Fiji reference with different Z:XY sampling meets a
  documented tolerance.

### 3. Match bounded drift-window semantics

For `max_expected_drift=r>0`, Fiji crops the CCM to `2r+1` pixels while
NanoPyx 2.1.4's low-level estimator currently slices `2r`. Implement a
Fiji-compatible bounded window using NanoPyx correlation primitives, or keep
the nonzero mode explicitly documented as NanoPyx-specific.

Acceptance criteria:

- `max_expected_drift=0` remains unchanged.
- Odd-width `2r+1` search windows match Fiji on synthetic translations.
- Edge cases at the positive and negative search limit are tested.

### 4. Verify transform application parity

Determine Fiji's exact interpolation, boundary, rounding, crop, bit-depth, and
NaN behaviour and reproduce it as an explicit compatibility mode.

Acceptance criteria:

- Integer and subpixel XYZ fixture outputs match Fiji within documented error.
- Default dtype behaviour is documented and tested for uint8, uint16, and
  float32.

## P1 — complete the original workflow

### 5. Separate XY and Z estimation settings

Support independent projection, reference, time averaging, and maximum drift
parameters without breaking the concise defaults.

### 6. Add crop-to-overlap and extend-Z options

Implement Fiji-equivalent crop bounds and symmetric Z padding from shift
extrema. Test positive, negative, fractional, and zero shifts.

### 7. Add a portable run manifest and saved drift plots

Use a path-independent JSON or CSV manifest containing axes, parameters,
versions, input metadata, and drift-table filename. Keep the existing simple
CSV shift table. Add a documented Fiji-settings importer only after fixtures
from P0 Task 1 exist.

### 8. Port the synthetic drift/noise generator

Implement deterministic quadratic XYZ drift with an RNG seed, optional drift
noise, Gaussian or Poisson image noise, and known ground-truth tables. Do not
hard-code the acquisition-specific 0.101/0.400 µm voxel sizes from the Fiji
macro.

## P2 — usability and larger files

### 9. Preserve OME-TIFF metadata

Round-trip axes, voxel sizes, time spacing, channel names, and units. Do not
claim general Bio-Formats support from TIFF-only tests.

### 10. Add a small batch runner

Provide one direct function or CLI that applies one configuration to multiple
files and creates predictable result folders. Avoid a plugin architecture.

### 11. Add optional lazy arrays

Add Dask/Zarr only after the in-memory P0 parity suite passes. The same core
registration and validation tests must run against NumPy and lazy inputs.

## Deferred by current project scope

- True 3D correlation.
- Rotation, scaling, shear, or non-rigid transforms.
- Napari or desktop GUI.
- GPU-selection framework.

These may be proposed later, but must not be mixed into parity work for the
Fast4DRegPy parity work.
