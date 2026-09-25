# Version 0.4.1 implementation specification

## Aim

Provide the Python implementation of Fast4DReg's projection-based rigid
translation workflow, using NanoPyx for 2D drift estimation in the same role
that NanoJ serves in the Fiji implementation.

## Authoritative references

- Fast4DReg repository: <https://github.com/CellMigrationLab/Fast4DReg>
- Fast4DReg paper: <https://doi.org/10.1242/jcs.260728>
- Fast4DReg dataset: <https://zenodo.org/records/6534570>
- Latest Zenodo dataset version: <https://zenodo.org/records/7514913>
- NanoPyx repository: <https://github.com/HenriquesLab/NanoPyx>
- NanoPyx 2.1.4 low-level drift estimator:
  `nanopyx.core.analysis._le_drift_calculator.DriftEstimator`

## Algorithm mapping

1. Normalize the explicitly labelled input array to internal `CTZYX` order.
2. Select a reference channel for time-drift estimation.
3. Project each `ZYX` volume over Z to create a `TYX` movie.
4. Call the explicitly selected NanoPyx `threaded` or `unthreaded` backend to
   estimate lateral translations. Do not use LiquidEngine dispatch because it
   can catch a backend failure and retry another backend.
5. Apply the estimated XY translation to a float32 copy of each reference
   volume. Independent volumes may be processed by an explicit fixed-size
   worker pool; the default remains one worker.
6. Project each XY-corrected volume over Y or X to create a `TZX` or `TZY`
   movie.
7. Centre-crop rectangular projections to the closest even square before
   NanoPyx estimation, matching both Fiji Fast4DReg and NanoPyx 2.1.4.
8. Use the Z component of the NanoPyx projection result as axial translation.
9. Combine the estimates in `(dz,dy,dx)` order.
10. Apply the same rigid translation to every channel at a given timepoint.

Channel registration uses the same operations with channel as the sequence
dimension. All channels are compared with the selected reference channel and
the estimated channel translation is applied to the complete volume.

## Required validation before scientific use

- Confirm translation signs and X/Y column ordering against Fiji Fast4DReg.
- Compare maximum and average projections on representative confocal data.
- Compare first-frame and previous-frame modes.
- Confirm subpixel interpolation behaviour and dtype conversion.
- Confirm axial results for anisotropic voxel spacing.
- Add at least one small raw dataset, Fast4DReg drift table, and corrected image
  as regression fixtures or downloadable test data.

## Paper validation implementation

`fast4dreg.validation` is based on the paper's archived
`scripts/registration_assesment_notebook.ipynb` and the methods described in
the publication. It provides:

- affine pair normalization matching the archived notebook;
- mSSIM, PSNR, Pearson correlation, and the historical notebook NRMSE value;
- a separately named conventional Euclidean NRMSE;
- first-to-subsequent and adjacent-frame comparison modes;
- selected-Z, maximum-projection, and average-projection analysis;
- ImageJ-compatible temporal standard-deviation projections (`ddof=1`);
- temporal color overlays, line profiles, kymographs, and signal/background
  ratios.

The historical notebook's NRMSE expression is not conventional NRMSE. It is
preserved as `paper_nrmse` only for reproduction of published analyses.

## Known algorithm differences

Fiji rescales the shallow axial reslice bicubically before estimation and then
rescales the measured Z translation. Version 0.4.1 now matches Fiji/NanoPyx
centre-cropping for rectangular correlation inputs, but it still does not
reproduce Fiji's physical axial rescaling. Z parity is therefore not yet
numerically proven.

## Explicit failure behaviour

- Axis order, image values, indices, enums, booleans, integer ranges, shifts,
  interpolation order, and output paths are validated before work begins.
- NanoPyx settings that NanoPyx 2.1.4 would clamp or ignore are rejected.
- The selected backend is never changed after failure.
- Files are never overwritten without `overwrite=True`.
- Z correction is never inferred from shape; callers must enable it.

## Version 0.4.1 performance behaviour

- `workers` is validated as a positive integer and is never inferred from the
  machine.
- Independent channel/timepoint transforms write directly into disjoint output
  views. Worker failures propagate to the caller.
- Serial and parallel outputs are required to be bit-for-bit identical by the
  regression suite.
- NanoPyx backend selection remains independent and explicit. Transform worker
  parallelism never changes or retries the estimation backend.

## Version 0.4.1 exclusions

There is no true 3D FFT, rotation correction, lazy loading, Zarr, GPU-specific
code, local elastic channel warping, or automatic dimension inference.
