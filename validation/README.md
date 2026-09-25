# Validation tooling

Two independent kinds of evidence back Fast4DRegPy's Fiji parity claims:

1. **The original Fiji macro, run headless** (`validation/fiji/`). The fixtures
   in `tests/data/fiji_macro/` and `tests/data/imagej_interpolation/` were
   produced by real ImageJ 1.53t and the Fast4DReg/NanoJ Java plugin, so normal
   CI checks Fast4DRegPy against Fiji without needing Java.
2. **The published full movie** (`validation/full_movie/`). The complete
   25-frame, 69-plane synthetic large-drift movie from Zenodo is registered and
   compared with the archived Fiji result and with the drift that was actually
   added to every frame.

Neither is part of the fast PR test suite.

## Full-movie validation

```bash
python -m pip install -e ".[validation]"
python validation/full_movie/validate_large_drift.py --download --workers 4
```

- Downloads `2-Synthetic-drift-dataset.zip` from Zenodo record **7514913**
  (the v2.0 version of archival record 6534570) into `.validation-data/`,
  unless it is already there. The archive must have MD5
  `27e3623f58d23d7c50674edc9432fe1b`; Zenodo's reported checksum is checked
  before downloading and the file is checked again afterwards. Another record,
  version or file is never used.
- Extracts only `2.1.2-LargeDrift_original.tif` and
  `2.2.1-LargeDrift_F4DReg.tif`, records their SHA-256, TIFF axes, dtype and
  ImageJ calibration, and lists every CSV/NJT/TXT member of the archive that
  could hold Fiji settings or drift tables.
- Registers all 25 timepoints and 69 Z planes (`max` projections, first-frame
  reference, no time averaging, automatic search, Top reslice, no crop),
  once with `workers=1` and once with `--workers`, and checks that the results
  are bit-identical. `OMP_NUM_THREADS` is pinned to 1 (see below).
- Recovers the **ground truth** for every frame by fitting ImageJ's two-pass
  bicubic translation of raw frame 0 to raw frame `t`. This is a forward model
  of `scripts/Drift_generator.ijm`, which leaves frame 0 untouched. The
  recovered values are compared with the five published Fig. S1A values
  committed in the test manifests. A complete published table can be supplied
  with `--ground-truth-csv frame,x,y,z`.
- Locates the archived Fiji crop by exact matching of frame 0 (Fiji never moves
  frame 0) and recovers **Fiji's applied translation for every frame** by
  fitting the same model to the archived frames. Fiji's crop rectangle is then
  recomputed from those translations with the macro's own formula.
- Also estimates the drift with `crop_output=True` to test whether Fiji
  estimated Z from the cropped stack (the v1 macro always cropped before Z).
- Writes to `validation-results/large-drift-full-movie/`:
  `shifts_per_frame.csv`, `fiji_comparison_metrics.csv`, `summary.json`,
  `run_info.json` and PNG diagnostics (`drift_trajectory.png`,
  `fiji_comparison_metrics.png`, `difference_frameNN.png`).
- Exits non-zero if a gate fails. `--gate baseline` uses the thresholds that
  predate this validation (0.75 px, Pearson > 0.98); `--gate strict` uses the
  levels measured on the compact frame-6 fixture (0.1 px vs truth, 0.02 px vs
  Fiji, Pearson > 0.9999).

`--self-test` runs the same pipeline on the committed small synthetic movie
and its real Fiji output. It checks that the tooling works and says nothing
about the published movie; results go to a separate `-SELF-TEST` folder.

The same run is available as the manually dispatched GitHub workflow
**full-movie validation** (`.github/workflows/full-movie-validation.yml`),
which caches the verified archive and uploads the results folder.

### Reproducibility note

NanoPyx 2.1.4 normalises correlation maps with OpenMP reductions whose
summation order depends on the thread count. With more than one OpenMP thread,
repeated runs can differ by 0.001 px (the DriftEstimator rounds to 3 decimals).
Set `OMP_NUM_THREADS=1` for bit-reproducible estimates. Fast4DRegPy's `workers`
parameter does not affect this.

## Running the original Fiji macro headless

`validation/fiji/` runs the unmodified `time_estimate+apply.ijm` from the
Fast4DReg repository. `patch_macro.py` only replaces the SciJava `#@` dialog
parameters with fixed values, replaces the Bio-Formats opener with `open()`,
and replaces `run("Collect Garbage")` (which blocks in headless ImageJ) with a
direct `System.gc()` call. Every projection, reslice, scale, crop, estimation
and correction command is the original.

Setup (Java 11+ and `xvfb-run`):

```bash
# ImageJ 1.53t and the NanoJ dependencies from Maven Central
M=https://repo1.maven.org/maven2
mkdir -p ImageJ/plugins lib
curl -o ImageJ/ij.jar $M/net/imagej/ij/1.53t/ij-1.53t.jar
for p in com/github/wendykierp/JTransforms/3.1/JTransforms-3.1.jar \
         pl/edu/icm/JLargeArrays/1.5/JLargeArrays-1.5.jar \
         org/apache/commons/commons-math3/3.5/commons-math3-3.5.jar \
         org/apache/commons/commons-compress/1.21/commons-compress-1.21.jar; do
  curl -o ImageJ/plugins/$(basename $p) $M/$p
done
# Compile the Fast4DReg Java plugin from the Fiji repository
git clone https://github.com/CellMigrationLab/Fast4DReg
SRC=Fast4DReg/Fast4DReg/jar-files/src/main
mkdir classes && javac -nowarn -d classes -cp "ImageJ/ij.jar:ImageJ/plugins/*" \
  $(find $SRC/java -name '*.java')
cp $SRC/resources/plugins.config classes/ && jar cf ImageJ/plugins/Fast4DReg_.jar -C classes .
```

Regenerate the committed fixtures:

```bash
python validation/fiji/make_macro_fixtures.py ImageJ \
  Fast4DReg/Fast4DReg/macros/time_estimate+apply.ijm \
  tests/data/fiji_macro/fiji_macro_reference.npz
python validation/fiji/make_imagej_interpolation_fixture.py ImageJ/ij.jar \
  tests/data/imagej_interpolation/reference.npz
```

The fixtures were generated with Fast4DReg commit `0483ace` (macro v2.1) and
ImageJ 1.53t (`ij.jar` SHA-256 recorded in each fixture).
