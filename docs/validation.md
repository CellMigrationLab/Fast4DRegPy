# Validation

Fast4DRegPy has been checked against the original Fiji Fast4DReg in two ways:
on the published synthetic test movie, and on small synthetic stacks
processed by the Fiji macro itself.

## Published test movie

Data: the synthetic large-drift movie from the Fast4DReg dataset
([Zenodo 7514913](https://zenodo.org/records/7514913),
`2-Synthetic-drift-dataset.zip`): 25 timepoints × 69 slices × 416 × 416
pixels, 16-bit, with known drift of up to 138 pixels in XY and 15 slices in
Z. The archive also contains the result of Fiji Fast4DReg
(`2.2.1-LargeDrift_F4DReg.tif`).

Settings: maximum projection, first-frame reference, no time averaging,
automatic search, Top reslice.

### Drift

Error of the estimated drift against the drift actually added to each frame,
over all 25 frames (pixels):

| | Z | Y | X |
| --- | ---: | ---: | ---: |
| Fast4DRegPy, mean error | 0.030 | 0.044 | 0.046 |
| Fast4DRegPy, largest error | 0.110 | 0.081 | 0.072 |
| Fiji, mean error | 0.030 | 0.043 | 0.046 |
| Fiji, largest error | 0.110 | 0.076 | 0.072 |
| Largest difference between Fast4DRegPy and Fiji | 0.002 | 0.005 | 0.004 |

Both implementations have the same accuracy. The largest errors occur in the
last frames, where the Z drift exceeds 13 slices and little of the volume
overlaps with the first frame.

![Drift trajectories](../validation/results/large-drift-full-movie/drift_trajectory.png)

### Corrected images

Compared with the Fiji result, frame by frame, over the region Fiji kept:

| Measure (worst frame) | Value |
| --- | ---: |
| Pearson correlation, whole volume | 0.9999993 |
| SSIM, whole volume | 0.9999997 |
| Mean absolute difference | 1.25 grey levels (of 65,280) |

Registration improved every frame. The correlation of each frame with the
first frame rose from between 0.97 and −0.02 before correction to between
0.994 and 0.999 after, the same as with Fiji.

Per-frame values, difference images and figures are in
[`validation/results/large-drift-full-movie/`](../validation/results/large-drift-full-movie/).

### Speed

Both programs ran on the same 2-CPU machine with the same settings:

| | Time |
| --- | ---: |
| Fiji Fast4DReg (ImageJ 1.53t) | 41 s |
| Fast4DRegPy, 1 worker | 19.5 s |
| Fast4DRegPy, 4 workers | 14.9 s |

### About the archived Fiji result

Running the Fiji macro again with the settings above and "Crop output" gives
exactly the archived voxels. Its output is 277 × 354 pixels, the size
Fast4DRegPy produces with `crop_output=True`. The archived file is 2 pixels
smaller in each direction because its right and bottom edges were trimmed
further after processing.

## Fiji macro on synthetic stacks

The Fiji macro was run on a small synthetic stack with eight settings. For
six of them (the default, average projection with previous-frame reference,
Left reslice, time averaging with 3 and 5 frames, and crop with Z extension),
Fast4DRegPy agrees with Fiji's drift tables within 0.004 pixels. Its corrected
stacks for the default, Left and crop cases have the same size as Fiji's and a
correlation above 0.9999.

The other two used a limited search radius. Where the drift stays inside the
radius, the results are the same as with automatic search. Where it reaches
the limit, Fiji returns NaN or a clipped value and Fast4DRegPy stops with an
error.

These results are part of the automated tests.

## Automated tests

The test suite (`python -m pytest`) runs on Python 3.10–3.13 and includes:

- the Fiji macro outputs above (`tests/data/fiji_macro/`);
- ImageJ interpolation and scaling outputs (`tests/data/imagej_interpolation/`);
- frames 0, 6, 12, 18 and 24 of the published movie, with the known drift
  (`tests/data/zenodo_synthetic/`);
- frames 0 and 6 of the published movie in 3D together with the Fiji result
  (`tests/data/zenodo_xyzt/`, not included in the source package because of
  its size).

## Not yet validated against Fiji

Channel registration, the Save RAM setting, and data with a different ratio
of lateral size to number of slices than the published movie.

## Re-running the validation

The full-movie comparison downloads the dataset (1.5 GB), checks its
checksum and writes CSV, JSON and PNG results:

```bash
python -m pip install -e ".[validation]"
python validation/full_movie/validate_large_drift.py --download
```

It fails if Fast4DRegPy differs from Fiji by more than 0.01 pixels, from the
known drift by more than 0.15 pixels, or if the correlation with the Fiji
result drops below 0.99999. Both comparisons can also be started from the
repository's Actions tab ("full-movie validation" and "fiji full-movie
timing"). See [`validation/README.md`](../validation/README.md) for running
the Fiji macro yourself.

## Data licence

The Fast4DReg dataset is published under CC BY 4.0 by Pylvänäinen et al.
The files in `tests/data/` are small extracts from it.
