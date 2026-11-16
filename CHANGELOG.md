# Changelog

## Unreleased

- Fast4DRegPy is also a LabConstrictor app: each release builds installers
  for Windows, macOS and Linux that open the notebook
  (`notebooks/Fast4DRegApp/Fast4DRegApp.ipynb`) and add the tools
  **Correct drift (time-lapse)** and **Align channels** to napari and Fiji
  (`src/fast4dreg_lc_tools/`, tested in `lc_tests/` and
  `tests/test_lc_tools.py`). Releases can also publish `fast4dregpy` on PyPI.
- `fast4dreg.__version__` is read from the installed package metadata.
- The notebook offers every Fast4DReg setting (time averaging, maximum
  expected drift, crop output, extend Z, reslice, output type) and its install
  cell works in Google Colab.
- New documentation in `docs/`: installation, step-by-step workflow with every
  setting, napari and Fiji, Python guide, troubleshooting, development and
  releases; timings against the Fiji macro in `docs/validation.md`.
- Split drift estimation, translation helpers and full-movie validation into
  smaller modules without changing the default registration algorithm.
- `backend="unthreaded"` now raises an explicit error when used with
  `time_averaging > 1` or `max_expected_drift > 0`. Those Fiji-compatible
  modes use NanoPyx's compiled correlation primitives directly; the backend
  setting was previously accepted but ignored.
- Full-movie validation now fails if reference fitting, commit identification,
  Fiji timing extraction or output-shape comparison is incomplete.
- `validation/fiji/compare_with_fiji.py` replaces `time_full_movie.py`. It
  runs Fiji and Fast4DRegPy on any registered Zenodo dataset
  (`synthetic-large-drift` or `huvec`) and is available as the manual
  **fiji comparison** workflow.

## 0.5.0

Validated against Fiji Fast4DReg on the complete published test movie; see
[docs/validation.md](docs/validation.md).

### Changed

- Translations now use ImageJ's bicubic interpolation by default, applied in
  XY and then in Z as Fiji does. The corrected images closely match Fiji's.
  The previous SciPy spline interpolation is available with
  `interpolation="scipy"`. `interpolation_order` and a non-zero `cval` are
  only accepted with `interpolation="scipy"`.
- `time_averaging` now works like Fiji: an incomplete last block is kept, each
  block is compared with the first frame, and drift is interpolated linearly
  between blocks. It must leave at least two blocks.
- `max_expected_drift` now searches the same window as Fiji. If the drift
  reaches the edge of the window, an error is raised instead of returning a
  wrong value.

### Added

- `crop_output` and `extend_z` options, equivalent to Fiji's "Crop output"
  and "Extend stack to fit", and the helpers `fiji_crop_bounds` and
  `fiji_z_padding`.
- Faster image correction, which scales with `workers`.
- Validation tools and results in `validation/`.

### Fixed

- Z drift was overestimated by about 1–4 % (more for stacks with fewer slices)
  because the axial projection was stretched differently from Fiji.
- Z drift was measured on an XY-corrected stack that used different
  interpolation from Fiji.
- The source package included a test whose data file was left out.
