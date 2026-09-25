# Reference datasets

The data associated with Fast4DReg are archived on Zenodo.

## Records

- Requested archival record (v1.0): <https://zenodo.org/records/6534570>,
  DOI <https://doi.org/10.5281/zenodo.6534570>, title **Fast4DRegistration**.
- Zenodo links it to the expanded v2.0 record:
  <https://zenodo.org/records/7514913>, DOI
  <https://doi.org/10.5281/zenodo.7514913>. All fixtures and the full-movie
  validation use this record.

The archive (CC BY 4.0) contains synthetic-drift data, HUVEC data,
channel-alignment data, expected Fiji outputs and the original software. It is
tens of gigabytes and is not vendored here.

## The synthetic large-drift movie

Archive `2-Synthetic-drift-dataset.zip` (MD5
`27e3623f58d23d7c50674edc9432fe1b`):

| Member | Content |
| --- | --- |
| `2.1-Synthetic-drift-files/2.1.2-LargeDrift_original.tif` | raw movie, `TZYX` 25 x 69 x 416 x 416, uint16, Z spacing 0.5 in the ImageJ metadata |
| `2.2-Synthetic-drift-expected-results/2.2.1-LargeDrift_F4DReg.tif` | archived Fiji Fast4DReg output, `TZYX` 25 x 69 x 275 x 352, uint16 |

`validation/full_movie/validate_large_drift.py` re-reads and records the exact
shapes, axes, dtypes and calibration of both files on every run
(`run_info.json`).

### Ground-truth convention

`scripts/Drift_generator.ijm` duplicates the original volume as frame 0 and
then translates frames `t = 1..T-1` by the drift it generated (quadratic trend
plus Gaussian noise). **Frame 0 is never translated.** The table reported in
Fig. S1A (and Pylvänäinen's thesis, Table 7) also lists a value for frame 0,
which is the noise drawn for `t = 0` and was never applied.

The translation Fast4DRegPy (and Fiji) should apply to frame `t` is therefore

```
(dz, dy, dx) = (-z[t], -y[t], -x[t])  for t >= 1,   (0, 0, 0) for t = 0
```

This was verified directly: fitting a translated copy of raw frame 0 to raw
frame 6 gives an added displacement of (z, y, x) = (-2.4792, -2.0125, 4.8259),
matching the published frame-6 value (-2.4789, -2.012, 4.83). Earlier versions
of the tests subtracted the frame-0 value, which is wrong by up to 0.84 px.

Only five published values (frames 0, 6, 12, 18, 24) are available in
machine-readable form in this repository. The full-movie validation recovers
the added displacement of all 25 frames by the same forward fit and checks it
against those five values.

### How the archived Fiji output was produced

Established from the data and the macro source:

- **32-bit arithmetic ("Save RAM" off).** Applying ImageJ's two-pass bicubic
  translation to raw frame 6 in float, then rounding once to uint16,
  reproduces 99.99% of the archived voxels exactly (maximum difference 1 grey
  level). The "Save RAM" model (16-bit rounding after each pass) does not fit
  (maximum difference 282). The archive is the 32-bit result converted once to
  uint16.
- **Bicubic ImageJ translation, zero fill**, XY pass before the Z pass.
- **Cropped output.** Frame 0 of the archived output is an exact crop of raw
  frame 0 at (y, x) = (138, 0) with size 275 x 352 and the full 69 slices, so
  "Extend stack to fit" was off.

Settings that are inferred rather than recorded are listed, with their
evidence, in `docs/full_movie_validation.md`. No settings CSV or drift table
for this result has been found in the archive.

## Committed fixtures

| Fixture | Size | Content | Provenance |
| --- | --- | --- | --- |
| `tests/data/zenodo_synthetic/large_drift_xy_max.npz` | 1.2 MB | full-field max-Z projections of raw frames 0, 6, 12, 18, 24 | Zenodo raw movie; `manifest.json` |
| `tests/data/zenodo_xyzt/large_drift_xyzt_fiji_reference.npz` | 28 MB | raw frames 0 and 6 (all Z, full X, 192 central Y rows) and the matching archived Fiji region | Zenodo raw + Fiji output; `manifest.json`; in Git only, not in the sdist |
| `tests/data/fiji_macro/fiji_macro_reference.npz` | 2.1 MB | synthetic 12 x 12 x 36 x 44 movie, Fiji drift tables for 8 macro settings, Fiji-corrected stacks for 3 | real Fiji macro run headless, `validation/fiji/make_macro_fixtures.py` |
| `tests/data/imagej_interpolation/reference.npz` | 40 kB | ImageJ `translate` and `resize` outputs | real ImageJ 1.53t, `validation/fiji/make_imagej_interpolation_fixture.py` |

The XYZT fixture is cropped in Y, so it cannot reproduce Fiji's full-field XY
estimate; its tests take XY from the full-field XY fixture. Fiji's actual
frame-6 translation, recovered from the archived output to better than
0.005 px, is recorded in its manifest.

Do not replace these fixtures with regenerated synthetic images: their purpose
is to exercise Fast4DRegPy on pixels from the published dataset and on output
written by the original Fiji implementation.
