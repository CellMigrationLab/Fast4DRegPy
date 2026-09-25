# Zenodo synthetic XY fixture

This directory contains a compact derivative of the published Fast4DReg large-drift synthetic dataset. The source is Zenodo record 7514913 (archival record requested for this repository: 6534570), member `2.1.2-LargeDrift_original.tif` from `2-Synthetic-drift-dataset.zip`.

The fixture stores full-field maximum-Z projections at five timepoints spanning the movie. No spatial cropping, intensity normalization, denoising, or resampling is applied. If the source contains a channel axis, channel 0 is used. Exact provenance, source shape/axes, selected timepoints, published drift parameters, and the fixture SHA-256 are recorded in `manifest.json`.

Do not replace this fixture with regenerated synthetic images: its purpose is to exercise Fast4DRegPy on pixels derived from the published Fast4DReg dataset.

The source dataset is distributed under **CC BY 4.0**. The selected ground-truth
drift values stored in `manifest.json` are the actual values reported for the
corresponding frames in Fast4DReg Fig. S1A (also reproduced in Pylvänäinen's
doctoral thesis, Table 7), not values regenerated from nominal polynomial
coefficients.
