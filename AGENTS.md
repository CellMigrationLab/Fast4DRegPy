# Working on Fast4DRegPy

Fast4DRegPy reimplements the Fiji plugin
[Fast4DReg](https://github.com/CellMigrationLab/Fast4DReg) in Python, with
NanoPyx doing the cross-correlation that NanoJ does in Fiji. **Fiji is the
reference:** a change is correct when it matches what the original Fiji macro
does, not when it looks more elegant. User documentation:
`README.md`, `docs/fiji_compatibility.md`, `docs/validation.md`.

## Setup and checks

```bash
python -m pip install -e ".[dev]"
python -m ruff check src tests benchmarks validation
python -m pytest -q          # ~10 s; must pass on Python 3.10–3.13
```

Run both before finishing any change. NanoPyx (pinned to 2.1.4) is a real
dependency: never mock it, vendor it or skip tests when it is missing.

After changing estimation, transforms or the NanoPyx pin, also run the
full-movie comparison (about 20 minutes). Either dispatch the **full-movie
validation** workflow in GitHub Actions, or run
`python validation/full_movie/validate_large_drift.py --download` (needs
access to zenodo.org). It must pass the default `strict` gate: at most
0.01 px from Fiji, at most 0.15 px from the known drift, correlation with
Fiji above 0.99999.

## Where things are

| Path | Contents |
| --- | --- |
| `src/fast4dreg/core.py` | `register_time`, `register_channels` (estimate, then apply) |
| `src/fast4dreg/estimation.py` | XY/Z projection and estimation orchestration |
| `src/fast4dreg/_drift.py` | NanoPyx calls, Fiji time averaging and bounded-search semantics |
| `src/fast4dreg/transform.py` | public transform application, Fiji crop and Z padding |
| `src/fast4dreg/_translation.py` | transform validation and low-level application helpers |
| `src/fast4dreg/_imagej.py` | NumPy ports of ImageJ `translate` (bicubic) and `resize` |
| `src/fast4dreg/axes.py` | axis strings, conversion to and from internal `CTZYX` |
| `src/fast4dreg/io.py` | TIFF and drift-CSV input/output |
| `src/fast4dreg/validation.py`, `visualization.py` | quality metrics and figures from the paper |
| `tests/test_fiji_macro_parity.py` | comparisons with output written by the real Fiji macro |
| `tests/test_imagej_parity.py` | comparisons with real ImageJ interpolation output |
| `tests/test_zenodo_*.py` | extracts of the published movie and its Fiji result |
| `validation/full_movie/` | full-movie data loading, reference fitting, metrics, reporting and CLI |
| `validation/fiji/` | Fiji runner and fixture-generation tools |
| `src/fast4dreg_lc_tools/` | the napari / Fiji tools of the app: only call the public API |
| `lc_tests/`, `tests/test_lc_tools.py` | the tool cases (also used by LabConstrictor's napari and Fiji checks) and their accuracy test |
| `notebooks/Fast4DRegApp/` | the app's notebook and the pinned environment of the app (`requirements.yaml`) |
| `app/`, `.tools/`, `.template_sync/`, `construct.yaml`, `environment.yaml`, `setup.py`, `requirements*.txt` | LabConstrictor template files that build the installers; changed by the template-sync pull requests, not by hand (`setup.py` is the exception: see its docstring) |

## Conventions that must not change

- Shifts are stored as `(dz, dy, dx)` and are the **translation applied** to
  each frame, the same quantity as Fiji's drift table (`X-Drift` = `dx`,
  `Y-Drift` = `dy`, Z table `Y-Drift` = `dz`).
- Axes are always given explicitly; never infer them from the array shape.
- XY is estimated and applied before the projection used for Z is made.
- The same translation is applied to every channel of a timepoint.
- The default interpolation is ImageJ bicubic, applied per Z plane and then
  per axial plane, with 0 outside the image. Keep `_imagej.py` bit-compatible
  with ImageJ; its tests use real ImageJ output.

## Things that have caused bugs

- **Ground truth of the published movie.** `Drift_generator.ijm` never moves
  frame 0, so the translation that corrects frame `t` is `-published[t]`,
  not `-(published[t] - published[0])`.
- **Axial stretch.** Fiji stretches the axial projection by
  `round(lateral / slices)` using ImageJ's `resize`, which scales
  displacements by exactly that factor. `scipy.ndimage.zoom` does not, and
  biased Z by 1–4 %. The factor comes from pixel counts, not voxel sizes.
- **NanoPyx differs from NanoJ.** Its bounded search window is off-centre
  and its time averaging uses different reference, blocks and
  interpolation. Fast4DRegPy therefore builds these from NanoPyx's
  correlation primitives (`_fiji_drift` in `_drift.py`). Do not route
  these cases back through `DriftEstimator`.
- **Fiji's own failure modes.** Fiji writes NaN or clipped values when the
  drift reaches the search limit, and zero drift when averaging leaves one
  block. Fast4DRegPy raises an error in both cases; keep it that way.
- **Cropping changes Z.** Fiji crops before measuring Z, so `crop_output`
  affects estimation, not only the output.
- **Reproducibility.** NanoPyx uses OpenMP reductions, so estimates vary by
  ~0.001 px between runs unless `OMP_NUM_THREADS=1`. `workers` never changes
  results; tests compare serial and parallel output exactly.
- **Test data that looks convenient but is not equivalent.** The XYZT
  extract is cropped in Y, so XY drift must come from the full-field extract.
  Do not replace published or Fiji-generated fixtures with regenerated data.

## Releases

`version` in `pyproject.toml` must equal the release tag before a release is
published (the PyPI step stops otherwise). Keep `requires-python` and the
dependencies in `pyproject.toml`; `setup.py` deliberately has neither (they
would override `pyproject.toml` on PyPI). The app's pinned environment is
`notebooks/Fast4DRegApp/requirements.yaml`; the tools' tables need `pandas`
there.

## Rules

- Reject invalid input or unsupported settings with a clear error. Never
  silently change a setting, switch or retry a NanoPyx backend, overwrite a
  file, or skip a requested correction.
- Every bug fix gets a test that fails without the fix. Use asymmetric test
  images so axis swaps and sign errors show up.
- Never loosen a tolerance just to make a test pass; find out why it fails.
- Keep `workers` explicit (default 1); never pick a worker count
  automatically.
- Keep `paper_nrmse` (the paper's formula) separate from `standard_nrmse`.
- Keep the API plain: explicit keyword arguments, NumPy arrays, no `**kwargs`,
  configuration objects or plugin systems. Registration code belongs in
  `src/fast4dreg`; the notebook only calls the public API.
- Update `CHANGELOG.md` for user-visible changes.

## Regenerating Fiji fixtures

The fixtures in `tests/data/fiji_macro/` and
`tests/data/imagej_interpolation/` come from the real Fiji macro and ImageJ.
Regenerate them with the scripts in `validation/fiji/`. This needs Java 11+
and `xvfb-run`; `setup_imagej.sh` builds ImageJ 1.53t with the Fast4DReg
plugin from Maven Central and the Fast4DReg repository. Keep the macro patch
limited to what is needed to run without a screen (`patch_macro.py`).

## Open work, in priority order

1. **Second 3D reference.** Validate on data with a different ratio of
   lateral size to number of slices (a different axial stretch factor), for
   example the HUVEC data in the Zenodo archive, using `validation/fiji/`.
2. **Separate XY and Z settings.** Fiji allows projection, reference, time
   averaging and search radius to differ between XY and Z. Add separate Z
   parameters without changing the defaults, with Fiji fixtures for mixed
   settings.
3. **Fiji "Save RAM" mode**, rounding after the XY step and the Z step, only
   if bit-exact 16-bit output is needed.
4. **Drift-table I/O and run records.** Read and write NanoJ `.njt` files (a
   zip containing a tab-separated `data.txt`; see
   `validation/fiji/make_macro_fixtures.py`) and save the settings used.
5. **Synthetic drift generator** with a seed, matching `Drift_generator.ijm`
   (which never moves frame 0).
6. **TIFF metadata.** Write ImageJ hyperstacks with voxel sizes and
   channel names.
7. **Batch processing** of folders; lazy (Dask/Zarr) arrays only once the same
   tests pass for them.

Out of scope unless agreed first: true 3D correlation; rotation, scaling or
non-rigid registration; a GUI beyond the notebook and the napari / Fiji tools;
GPU selection.
