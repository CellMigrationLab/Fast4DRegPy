# Changelog

## Unreleased

- Split drift estimation, translation helpers and full-movie validation into
  smaller modules without changing the default registration algorithm.
- `backend="unthreaded"` now raises an explicit error when used with
  `time_averaging > 1` or `max_expected_drift > 0`. Those Fiji-compatible
  modes use NanoPyx's compiled correlation primitives directly; the backend
  setting was previously accepted but ignored.
- Full-movie validation now fails if reference fitting, commit identification,
  Fiji timing extraction or output-shape comparison is incomplete.

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
