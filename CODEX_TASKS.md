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

### 1. Add Fiji reference fixtures

Source archive: Zenodo record 6534570 (currently linked to expanded version
7514913). Select one small redistribution-safe XYT dataset and one small XYZT
dataset from that archive, then run the current Fiji Fast4DReg on both using
documented settings.

Acceptance criteria:

- Store or reproducibly download the raw input, Fiji XY/Z drift tables,
  settings CSV, and corrected outputs.
- Record checksums, Fast4DReg commit/version, Fiji version, and all parameters.
- Tests compare shift sign, axis order, frame count, and corrected pixels.

### 2. Reproduce Fiji axial reslice scaling

Replace or augment even-square padding with a documented physical-pixel-size
aware axial-resampling path equivalent to the Fiji macros' bicubic scaling and
Z-drift rescaling.

Acceptance criteria:

- API accepts voxel spacing explicitly; it never guesses calibration.
- Isotropic and anisotropic synthetic tests recover known subpixel Z shifts.
- Fiji axial reference tables meet the Task 1 tolerance.

### 3. Verify transform application parity

Determine Fiji's exact interpolation, boundary, rounding, crop, bit-depth, and
NaN behaviour and reproduce it as an explicit compatibility mode.

Acceptance criteria:

- Integer and subpixel XYZ fixture outputs match Fiji within documented error.
- Default dtype behaviour is documented and tested for uint8, uint16, and
  float32.

## P1 — complete the original workflow

### 4. Separate XY and Z estimation settings

Support independent projection, reference, time averaging, and maximum drift
parameters without breaking the concise defaults.

### 5. Add crop-to-overlap and extend-Z options

Implement Fiji-equivalent crop bounds and symmetric Z padding from shift
extrema. Test positive, negative, fractional, and zero shifts.

### 6. Add a portable run manifest and saved drift plots

Use a path-independent JSON or CSV manifest containing axes, parameters,
versions, input metadata, and drift-table filename. Keep the existing simple
CSV shift table. Add a documented Fiji-settings importer only after fixtures
from P0 Task 1 exist.

### 7. Port the synthetic drift/noise generator

Implement deterministic quadratic XYZ drift with an RNG seed, optional drift
noise, Gaussian or Poisson image noise, and known ground-truth tables. Do not
hard-code the acquisition-specific 0.101/0.400 µm voxel sizes from the Fiji
macro.

## P2 — usability and larger files

### 8. Preserve OME-TIFF metadata

Round-trip axes, voxel sizes, time spacing, channel names, and units. Do not
claim general Bio-Formats support from TIFF-only tests.

### 9. Add a small batch runner

Provide one direct function or CLI that applies one configuration to multiple
files and creates predictable result folders. Avoid a plugin architecture.

### 10. Add optional lazy arrays

Add Dask/Zarr only after the in-memory P0 parity suite passes. The same core
registration and validation tests must run against NumPy and lazy inputs.

## Deferred by current project scope

- True 3D correlation.
- Rotation, scaling, shear, or non-rigid transforms.
- Napari or desktop GUI.
- GPU-selection framework.

These may be proposed later, but must not be mixed into parity work for the
Fast4DRegPy parity work.
