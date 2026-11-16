# Tests of the napari and Fiji tools

The tools are declared in `src/fast4dreg_lc_tools/` and run in the app's own
environment through the LabConstrictor tools worker. They need
`labconstrictor-tools` (the app installer installs it) and `pandas` for their
tables.

```bash
cd lc_tests
python make_fixtures.py fixtures
labconstrictor-tools check --module fast4dreg_lc_tools
labconstrictor-tools test  --module fast4dreg_lc_tools --cases cases.json
```

`make_fixtures.py` writes four small images cut out of one random scene at
known whole-pixel offsets (Y and X sizes differ, so an axis swap shows):
a 2D and a 3D time-lapse, and a 2D and a 3D multichannel image. The 3D
images have 20 slices: with about 10, Fast4DRegPy does not measure the Z drift.

`cases.json` runs each tool on them and checks what the hosts rely on: the
shape and type of the corrected image, the columns and rows of the drift
table, and the clear refusals (axes that do not fit the image, Z correction
without a Z axis, a reference channel the image does not have). The napari
and Fiji UI checks of LabConstrictor use the same cases.

`tests/test_lc_tools.py` checks, on the same images, that the tools find the
known drift within 0.4 px, so that a sign or axis error cannot pass.
