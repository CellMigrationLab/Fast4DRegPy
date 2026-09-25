# Version 0.4 performance verification

> **Superseded:** see [`performance.md`](performance.md) for 0.5.0, where the
> default transform is the ImageJ-compatible path.

## Scope

Version 0.4 parallelizes independent SciPy volume translations without changing
the projection algorithm, NanoPyx backend, interpolation settings, boundary
conditions, output dtype, or shift convention. The public `workers` parameter
defaults to `1` and must be set explicitly.

The implementation writes each task directly into a disjoint preallocated
output view. It therefore avoids keeping one completed output volume per future
while preserving worker exception propagation.

## Correctness checks

- Serial and parallel time registration application are bit-for-bit identical.
- Serial and parallel channel registration application are bit-for-bit
  identical.
- The XY-corrected axial projection is bit-for-bit identical with one or
  several workers.
- Real NanoPyx integration tests recover known XYZ time and channel shifts while
  using two transform workers.

## Benchmark method

Measurements used a CPU-only environment with 9 logical CPUs. Inputs were
float32 arrays shaped `20 x 16 x 256 x 256` in `TZYX` order. Results are warmed
medians; no OpenCL, CUDA, Dask, or Zarr backend was available.

The reproducible transform benchmark used five timed repetitions:

| Workers | Transform time | Speedup |
| ---: | ---: | ---: |
| 1 | 0.5922 s | 1.00x |
| 2 | 0.4515 s | 1.31x |
| 4 | 0.2264 s | 2.62x |
| 8 | 0.1370 s | 4.32x |

Warmed full XYZ registration, including both NanoPyx estimations and transform
application, used three timed repetitions:

| Workers | Median XYZ registration |
| ---: | ---: |
| 1 | 1.6028 s |
| 4 | 0.5137 s |
| 8 | 0.3920 s |

## Interpretation

Four workers are a conservative starting point for a workstation. Eight were
faster on this machine, but scaling depends on CPU count and memory bandwidth.
Users should run:

```bash
python benchmarks/benchmark_transforms.py --workers 1 2 4 8
```

The current package remains in-memory. Very large datasets may therefore
require external chunking or another out-of-core workflow. Optional lazy
storage remains deferred until the Fiji parity fixtures recorded in
`CODEX_TASKS.md` are established.
