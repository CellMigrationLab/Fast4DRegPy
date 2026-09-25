"""Reproducible CPU benchmark for independent volume transformations."""

from __future__ import annotations

import argparse
import statistics
import time

import numpy as np

from fast4dreg import apply_drift


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timepoints", type=int, default=20)
    parser.add_argument("--z", type=int, default=16)
    parser.add_argument("--y", type=int, default=256)
    parser.add_argument("--x", type=int, default=256)
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--repeats", type=int, default=3)
    return parser.parse_args()


def _positive(values: list[int], *, name: str) -> None:
    if any(value < 1 for value in values):
        raise ValueError(f"every {name} value must be at least 1")


def main() -> None:
    args = _parse_args()
    dimensions = [args.timepoints, args.z, args.y, args.x]
    _positive(dimensions, name="dimension")
    _positive(args.workers, name="workers")
    _positive([args.repeats], name="repeats")

    rng = np.random.default_rng(1)
    image = rng.normal(size=dimensions).astype(np.float32)
    index = np.arange(args.timepoints, dtype=np.float32)
    shifts = np.column_stack(
        (index * 0.13 % 3, index * 0.27 % 5, -(index * 0.31 % 7))
    )

    print(f"shape={image.shape}, dtype={image.dtype}, repeats={args.repeats}")
    baseline = None
    for workers in args.workers:
        apply_drift(image, shifts, axes="TZYX", workers=workers)
        durations = []
        for _ in range(args.repeats):
            start = time.perf_counter()
            apply_drift(image, shifts, axes="TZYX", workers=workers)
            durations.append(time.perf_counter() - start)
        median = statistics.median(durations)
        if baseline is None:
            baseline = median
        print(
            f"workers={workers:>2}: {median:.4f} s "
            f"({baseline / median:.2f}x versus first result)"
        )


if __name__ == "__main__":
    main()
