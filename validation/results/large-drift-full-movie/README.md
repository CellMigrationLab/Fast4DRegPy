# Full-movie validation results

Output of `validation/full_movie/validate_large_drift.py` on the published
synthetic large-drift movie (Zenodo 7514913, `2-Synthetic-drift-dataset.zip`,
MD5 `27e3623f58d23d7c50674edc9432fe1b`), GitHub Actions run 36151270321 at
commit `57f6766` (`--gate baseline`; every value also passes the current
`strict` gate, confirmed by run 36152160907 at `79bc6f5`). The figures were transferred through the job log and are
rendered at reduced resolution.

- `shifts_per_frame.csv`: per frame, expected/estimated/error for dz, dy, dx
  (expected = negated displacement recovered from the raw movie), Fiji's
  recovered applied translation, and the crop-before-Z estimate.
- `fiji_comparison_metrics.csv`: per-frame Pearson, RMSE, NRMSE, MAE and SSIM
  vs the archived Fiji output (3D, max-Z, max-Y), representative slices,
  identical-voxel fraction, and correlation with frame 0 (raw, ours, Fiji).
- `summary.json`: aggregate statistics, worst frames, error correlates, gates.
- `run_info.json`: versions, settings, timings, checksums, TIFF metadata,
  Fiji crop analysis, forward-fit quality and the settings sweep.

Interpretation: [`docs/full_movie_validation.md`](../../../docs/full_movie_validation.md).
