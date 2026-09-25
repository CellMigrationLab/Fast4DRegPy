"""Validate Fast4DRegPy on the complete published large-drift movie."""

from __future__ import annotations

import os
import sys

if "--omp-threads" in sys.argv:
    index = sys.argv.index("--omp-threads")
    if index + 1 >= len(sys.argv):
        raise ValueError("--omp-threads requires a value")
    os.environ["OMP_NUM_THREADS"] = sys.argv[index + 1]
else:
    os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import platform
from pathlib import Path

import numpy as np
import tifffile
from analysis import (
    axis_summaries,
    crop_formula_report,
    expected_translations,
    find_archived_crop,
    git_commit,
    published_subset_difference,
    recover_reference_translations,
    run_fast4dregpy,
    run_worker_comparison,
    settings_sweep,
)
from data import REPOSITORY, Movie, load, self_test_movie
from report import (
    GATES,
    compare_images,
    gate_results,
    write_results,
    z_error_correlates,
)

import fast4dreg


def _software_info(movie: Movie) -> dict:
    import nanopyx
    import scipy

    return {
        "fast4dregpy_version": fast4dreg.__version__,
        "fast4dregpy_commit": git_commit(REPOSITORY),
        "python": sys.version,
        "platform": platform.platform(),
        "omp_num_threads": os.environ["OMP_NUM_THREADS"],
        "dataset": movie.metadata,
        "versions": {
            "nanopyx": nanopyx.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "tifffile": tifffile.__version__,
        },
    }


def _validate_shapes(movie: Movie) -> None:
    raw, fiji = movie.raw, movie.fiji
    if raw.ndim != 4 or fiji.ndim != 4:
        raise RuntimeError(
            f"expected TZYX movies, got raw={raw.shape}, fiji={fiji.shape}"
        )
    if raw.shape[:2] != fiji.shape[:2]:
        raise RuntimeError(
            "raw and Fiji movies must have matching T and Z dimensions; "
            f"got raw={raw.shape}, fiji={fiji.shape}"
        )


def _run_registration(movie: Movie, workers: int) -> tuple[dict, np.ndarray, dict]:
    principal, comparison = run_worker_comparison(movie.raw, workers)
    cropped = run_fast4dregpy(movie.raw, crop_output=True, workers=workers)
    cropped_shifts = cropped["shifts"]
    del cropped["corrected"]

    info = {
        "settings": principal["settings"],
        **comparison,
        "crop_before_z_hypothesis_shifts": cropped_shifts.tolist(),
    }
    return principal, cropped_shifts, info


def _reference_data(
    movie: Movie,
    shifts: np.ndarray,
    args: argparse.Namespace,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int], dict]:
    crop = find_archived_crop(movie.raw, movie.fiji)
    y0, x0, height, width = crop
    recovered, fiji_translation, fit_quality = recover_reference_translations(
        movie.raw,
        movie.fiji,
        shifts,
        crop_origin=(y0, x0),
    )
    expected, source = expected_translations(
        recovered,
        ground_truth_csv=args.ground_truth_csv,
    )
    details = {
        "fiji_crop": {"y0": y0, "x0": x0, "height": height, "width": width},
        "ground_truth_source": source,
        "published_subset_minus_recovered_px": published_subset_difference(
            expected,
            self_test=args.self_test,
        ),
        "settings_sweep_vs_fiji": settings_sweep(
            movie.raw,
            fiji_translation,
            workers=args.workers,
        ),
        "fiji_crop_formula_from_fiji_translations": crop_formula_report(
            fiji_translation,
            movie.raw.shape,
            crop,
        ),
        "forward_fit_quality": fit_quality,
    }
    return expected, fiji_translation, crop, details


def _summary(
    movie: Movie,
    principal: dict,
    cropped_shifts: np.ndarray,
    expected: np.ndarray,
    fiji_translation: np.ndarray,
    crop: tuple[int, int, int, int],
    info: dict,
    gate: str,
) -> tuple[dict, list[dict]]:
    shifts = principal["shifts"]
    summary = axis_summaries(shifts, expected, fiji_translation, cropped_shifts)
    metric_rows, distributions = compare_images(
        movie.raw,
        principal["corrected"],
        movie.fiji,
        crop=crop,
    )
    summary["fiji_image_metrics"] = distributions
    summary["abs_z_error_spearman"] = z_error_correlates(
        shifts,
        expected,
        movie.raw.shape,
    )
    summary["gate"] = gate_results(
        summary,
        metric_rows,
        preset=gate,
        serial_parallel_identical=info["serial_parallel_identical"],
    )
    return summary, metric_rows


def _plots(
    output: Path,
    movie: Movie,
    principal: dict,
    shifts: np.ndarray,
    expected: np.ndarray,
    fiji_translation: np.ndarray,
    metric_rows: list[dict],
    crop: tuple[int, int, int, int],
) -> None:
    from plots import make_plots

    make_plots(
        output,
        movie.raw,
        movie.fiji,
        principal["corrected"],
        shifts,
        expected,
        fiji_translation,
        metric_rows,
        crop[:2],
    )


def validate(movie: Movie, args: argparse.Namespace, output: Path) -> bool:
    _validate_shapes(movie)
    info = _software_info(movie)
    principal, cropped_shifts, registration_info = _run_registration(
        movie,
        args.workers,
    )
    info.update(registration_info)
    shifts = principal["shifts"]

    expected, fiji_translation, crop, reference_info = _reference_data(
        movie,
        shifts,
        args,
    )
    info.update(reference_info)
    summary, metric_rows = _summary(
        movie,
        principal,
        cropped_shifts,
        expected,
        fiji_translation,
        crop,
        info,
        args.gate,
    )

    write_results(
        output,
        info=info,
        summary=summary,
        shift_table=(shifts, expected, fiji_translation, cropped_shifts),
        metric_rows=metric_rows,
    )
    if not args.no_plots:
        _plots(
            output,
            movie,
            principal,
            shifts,
            expected,
            fiji_translation,
            metric_rows,
            crop,
        )

    checks = summary["gate"]["checks"]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    return all(checks.values())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPOSITORY / ".validation-data",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY / "validation-results" / "large-drift-full-movie",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="download the pinned archive from Zenodo if absent",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--gate", choices=sorted(GATES), default="strict")
    parser.add_argument(
        "--ground-truth-csv",
        type=Path,
        help="published drift table with columns frame,x,y,z",
    )
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument(
        "--omp-threads",
        default=os.environ["OMP_NUM_THREADS"],
        help="OpenMP threads for NanoPyx; default 1 for reproducible estimates",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the pipeline on the committed small Fiji fixture",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.self_test:
        args.output_dir = args.output_dir.with_name(args.output_dir.name + "-SELF-TEST")

    if (
        args.output_dir.exists()
        and any(args.output_dir.iterdir())
        and not args.overwrite
    ):
        raise FileExistsError(f"{args.output_dir} is not empty; pass --overwrite")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.self_test:
        movie = self_test_movie()
    else:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        movie = load(args.data_dir, download=args.download)

    print(
        f"raw {movie.raw.shape} {movie.raw.dtype}; "
        f"fiji {movie.fiji.shape} {movie.fiji.dtype}"
    )
    return 0 if validate(movie, args, args.output_dir) else 1


if __name__ == "__main__":
    raise SystemExit(main())
