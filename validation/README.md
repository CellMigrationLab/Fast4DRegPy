# Validation tools

Tools used to compare Fast4DRegPy with Fiji Fast4DReg. Results are summarised
in [`docs/validation.md`](../docs/validation.md).

## Full-movie comparison

```bash
python -m pip install -e ".[validation]"
python validation/full_movie/validate_large_drift.py --download --workers 4
```

The script:

- downloads `2-Synthetic-drift-dataset.zip` from Zenodo record 7514913 into
  `.validation-data/` and checks its MD5 (`27e3623f58d23d7c50674edc9432fe1b`);
- registers the full movie with Fast4DRegPy, once with one worker and once
  with `--workers`, and checks that both give the same result;
- determines the drift added to each frame, and the translation Fiji applied,
  by fitting translated copies of the raw frames;
- compares drift and corrected volumes with the ground truth and the archived
  Fiji result;
- writes `shifts_per_frame.csv`, `fiji_comparison_metrics.csv`,
  `summary.json`, `run_info.json` and figures to
  `validation-results/large-drift-full-movie/`.

It exits with an error if a threshold is exceeded (`--gate strict`, the
default: 0.01 px from Fiji, 0.15 px from the ground truth, correlation with
Fiji above 0.99999; `--gate baseline`: 0.75 px and 0.98). `--self-test` runs
the same steps on the small stack in `tests/data/fiji_macro/`.
`OMP_NUM_THREADS` is set to 1 so that results are reproducible.

The same run is available as the **full-movie validation** workflow in the
repository's Actions tab. Its first results are in
`results/large-drift-full-movie/`.

## Running the Fiji macro

`validation/fiji/` runs the original `time_estimate+apply.ijm` from the
Fast4DReg repository in ImageJ without a screen. It needs Java 11 or later and
`xvfb-run`.

```bash
git clone https://github.com/CellMigrationLab/Fast4DReg
validation/fiji/setup_imagej.sh ImageJ Fast4DReg   # ImageJ 1.53t + Fast4DReg plugin
```

`patch_macro.py` changes only what is needed to run without a user:

- the dialog settings become fixed values;
- the Bio-Formats file opener is replaced by ImageJ's `open()`;
- `run("Collect Garbage")`, which hangs without a screen, is replaced by a
  direct garbage-collection call;
- the log is saved to a file at the end.

The registration steps themselves are not changed. `run_fiji_macro.sh` runs
the patched macro on a virtual display.

Scripts:

- `compare_with_fiji.py --dataset NAME` runs Fiji and Fast4DRegPy with the
  same settings on a dataset from the Zenodo archive (`synthetic-large-drift`
  or `huvec`) and compares their drift tables, outputs, the archived Fiji
  result and run times. It is also available as the **fiji comparison**
  workflow. Earlier timing results are in `results/fiji-full-movie-timing/`.
- `make_macro_fixtures.py` regenerates `tests/data/fiji_macro/`, and
  `make_imagej_interpolation_fixture.py` regenerates
  `tests/data/imagej_interpolation/`:

```bash
python validation/fiji/make_macro_fixtures.py ImageJ \
  Fast4DReg/Fast4DReg/macros/time_estimate+apply.ijm \
  tests/data/fiji_macro/fiji_macro_reference.npz
python validation/fiji/make_imagej_interpolation_fixture.py ImageJ/ij.jar \
  tests/data/imagej_interpolation/reference.npz
```
