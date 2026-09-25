# Full-movie comparison results

Output of `validation/full_movie/validate_large_drift.py` on the published
synthetic large-drift movie. The run on `main` after the 0.5.0 merge gave the
same values.

| File | Content |
| --- | --- |
| `shifts_per_frame.csv` | per frame: known drift, Fast4DRegPy estimate and error, the translation Fiji applied, and the estimate with cropping before Z |
| `fiji_comparison_metrics.csv` | per frame: Pearson, RMSE, NRMSE, MAE and SSIM against the Fiji result (whole volume and projections), and correlation with the first frame before and after registration |
| `summary.json` | per-axis error statistics, worst frames and pass/fail checks |
| `run_info.json` | software versions, settings, run times, file checksums and TIFF metadata |
| `*.png` | drift plot, metric plot and difference images for frames 0, 1, 12 and 24 |

Summary: [`docs/validation.md`](../../../docs/validation.md).
