# Performance (0.5.0)

Measured in a 4-logical-CPU Linux container (Python 3.11, NumPy 2.4,
NanoPyx 2.1.4, no OpenCL/CUDA). Numbers are illustrative; run
`benchmarks/benchmark_transforms.py` on the target machine.

## Transform benchmark

`python benchmarks/benchmark_transforms.py --workers 1 2 4 --interpolation <mode>`
(float32 `20 x 16 x 256 x 256`, median of three warmed repetitions):

| Workers | `imagej` (default) | `scipy` (order 3) |
| ---: | ---: | ---: |
| 1 | 1.52 s | 5.49 s |
| 2 | 0.67 s | 3.00 s |
| 4 | 0.45 s | 1.67 s |

The ImageJ path translates whole stacks at once (every plane shares the
Catmull-Rom weights), so it is faster than a SciPy spline shift and scales with
`workers`.

## Full-size registration

`register_time(..., axes="TZYX", correct_z=True)` on a synthetic uint16 movie
with the published geometry (25 x 69 x 416 x 416, 597 MB), including both
NanoPyx estimations, the XY-corrected preparation for Z and the final
transform, `OMP_NUM_THREADS=1`:

| Workers | Wall time | Peak RSS |
| ---: | ---: | ---: |
| 1 | 64.3 s | 4.4 GB |
| 4 | 22.5 s | 6.2 GB |

Shifts and corrected volumes were bit-identical for `workers=1` and `4`.
The full-movie validation records the same measurements on the published movie
(`run_info.json`; see `full_movie_validation.md`).

## Reproducibility

Transform results never depend on `workers`. NanoPyx's own OpenMP reductions
do depend on the OpenMP thread count: with `OMP_NUM_THREADS>1`, drift estimates
can differ by ~0.001 px between otherwise identical runs. Set
`OMP_NUM_THREADS=1` when bit-reproducible estimates are required.

Memory: the API is in-memory. Expect roughly 8-10x the uint16 input size at
peak (float32 copies for Z preparation and output, plus per-worker scratch).
