# Codex implementation backlog

Work top-to-bottom within each priority. Keep changes small and add tests for
every acceptance criterion. Read `docs/parity_audit.md` first.

## Completed

- 0.3: sequential XY correction before Z estimation, explicit NanoPyx backend
  execution without fallback, strict input validation, float32 output,
  paper-compatible validation helpers.
- 0.4: explicit bounded parallel transforms, serial/parallel equality tests,
  transform benchmark.
- 0.5 (audit 2026-09-25, `docs/audit_2026-09-25.md`):
  - headless harness running the original Fiji macro (`validation/fiji/`)
    and committed real-Fiji fixtures for default, previous/average, bounded
    windows, time averaging with a partial block, Left reslice, crop + extend;
  - ImageJ-exact axial stretch (fixes a Z scale bias), ImageJ bicubic
    two-pass transform as the default, Fiji-centred `2r+1` search windows,
    NanoJ time-averaging semantics, `crop_output` / `extend_z`;
  - corrected published ground-truth convention (frame 0 is not drifted);
  - full-movie validation script and manual workflow
    (`validation/full_movie/`, `docs/full_movie_validation.md`);
  - archived Fiji settings confirmed by re-running the macro on the full
    movie, with Fiji and Fast4DRegPy timed on the same runner.

## P0 — remaining parity work

### 1. Keep the full-movie validation green

Run the **full-movie validation** workflow (default `strict` gate: 0.01 px vs
Fiji, Pearson > 0.99999, 0.15 px vs ground truth) after any change to
estimation, transforms or the NanoPyx pin.

### 2. Second XYZT reference with different geometry

The Fiji comparisons cover one published dataset (69 slices, 416 px) and the
synthetic macro fixtures. Add a published or Fiji-generated XYZT case with a
different Z:XY aspect (different axial stretch factor), ideally from the
HUVEC data in the Zenodo archive, using `validation/fiji/`.

## P1 — complete the original workflow

### 3. Separate XY and Z estimation settings

Fiji exposes projection, reference, time averaging and maximum drift
separately for XY and Z; Fast4DRegPy shares them. In particular the Z search
radius is in stretched axial pixels. Add separate Z parameters without breaking
the concise defaults, with macro fixtures for mixed settings.

### 4. Save RAM (16-bit) compatibility mode

Fiji's "Save RAM" rounds to the input bit depth after the XY pass and after the
Z pass. Add an explicit mode only if a use case needs bit-exact 16-bit parity.

### 5. Portable run manifest and saved drift plots

Path-independent JSON/CSV manifest with axes, parameters, versions, input
metadata and drift-table filename. NanoJ `.njt` import/export (the format is a
zip containing a tab-separated `data.txt`; see `validation/fiji/`).

### 6. Port the synthetic drift/noise generator

Deterministic quadratic XYZ drift with an RNG seed, optional drift noise and
Gaussian/Poisson image noise. Note that `Drift_generator.ijm` never drifts
frame 0.

## P2 — usability and larger files

### 7. Preserve OME-TIFF / ImageJ metadata

`save_tiff` writes a tifffile-shaped TIFF; it does not write an ImageJ
hyperstack or voxel sizes. Round-trip axes, voxel sizes, time spacing and
channel names.

### 8. Batch runner and optional lazy arrays

A single direct function or CLI for many files; Dask/Zarr only after the
in-memory parity suite passes on the same tests.

## Deferred by current project scope

- True 3D correlation.
- Rotation, scaling, shear, or non-rigid transforms.
- Napari or desktop GUI.
- GPU-selection framework.
