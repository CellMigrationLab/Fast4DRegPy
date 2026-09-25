# Published movie: frames 0 and 6 with the Fiji result

Extract from the Fast4DReg synthetic large-drift dataset
([Zenodo 7514913](https://zenodo.org/records/7514913),
`2-Synthetic-drift-dataset.zip`):

- `image`: raw frames 0 and 6 of `2.1.2-LargeDrift_original.tif`, all 69
  slices, full 416-pixel width, 192 central rows;
- `fiji_corrected`: the matching region of the Fiji result
  `2.2.1-LargeDrift_F4DReg.tif`.

The full width is kept because the Z estimation depends on it. Because the
rows are cropped, XY drift is taken from the `zenodo_synthetic` extract in the
tests. `manifest.json` records coordinates, checksums, the published drift and
the translation Fiji applied to frame 6. The pixels are unmodified.
