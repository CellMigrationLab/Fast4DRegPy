"""Run Fast4DRegPy and recover full-movie reference translations."""

from __future__ import annotations

import csv
import subprocess
import time
from pathlib import Path

import numpy as np

from fast4dreg import apply_drift, estimate_time_drift, fiji_crop_bounds

from metrics import axis_statistics
from reference import central_block, fit_translation, locate_fiji_crop

PUBLISHED_SUBSET = {
    0: (-0.1846, -0.842, 0.7736),
    6: (4.83, -2.012, -2.4789),
    12: (15.5335, -25.244, -7.4236),
    18: (34.7591, -71.216, -10.8287),
    24: (62.7437, -137.609, -14.8706),
}


def git_commit(repository: Path) -> str:
    """Return HEAD or fail; validation results must have a concrete commit."""
    return subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def load_ground_truth_csv(path: Path, frames: int) -> np.ndarray:
    """Read published drift columns ``frame,x,y,z``."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if [int(row["frame"]) for row in rows] != list(range(frames)):
        raise ValueError("ground-truth CSV must list frames 0..T-1 in order")
    return np.asarray(
        [[float(row["x"]), float(row["y"]), float(row["z"])] for row in rows]
    )


def run_fast4dregpy(
    raw: np.ndarray,
    *,
    crop_output: bool,
    workers: int,
) -> dict:
    settings = {
        "axes": "TZYX",
        "projection": "max",
        "reference": "first",
        "correct_xy": True,
        "correct_z": True,
        "axial_projection_axis": "Y",
        "time_averaging": 1,
        "max_expected_drift": 0,
        "crop_output": crop_output,
        "workers": workers,
    }
    start = time.perf_counter()
    shifts = estimate_time_drift(raw, **settings)
    estimated = time.perf_counter()
    corrected = apply_drift(raw, shifts, axes="TZYX", workers=workers)
    finished = time.perf_counter()
    return {
        "settings": {**settings, "interpolation": "imagej", "output_dtype": "float32"},
        "shifts": shifts,
        "corrected": corrected,
        "estimate_seconds": estimated - start,
        "apply_seconds": finished - estimated,
    }


def run_worker_comparison(raw: np.ndarray, workers: int) -> tuple[dict, dict]:
    runs = {
        count: run_fast4dregpy(raw, crop_output=False, workers=count)
        for count in sorted({1, workers})
    }
    for count, run in runs.items():
        print(
            f"workers={count}: estimate {run['estimate_seconds']:.1f} s, "
            f"apply {run['apply_seconds']:.1f} s"
        )

    principal = runs[1]
    comparison = {
        "timing_seconds": {
            str(count): {
                "estimate": run["estimate_seconds"],
                "apply": run["apply_seconds"],
            }
            for count, run in runs.items()
        },
        "serial_parallel_identical": {
            "shifts": bool(
                all(
                    np.array_equal(run["shifts"], principal["shifts"])
                    for run in runs.values()
                )
            ),
            "corrected": bool(
                all(
                    np.array_equal(run["corrected"], principal["corrected"])
                    for run in runs.values()
                )
            ),
        },
    }
    return principal, comparison


def _fit_reference_frame(
    raw: np.ndarray,
    fiji: np.ndarray,
    shifts: np.ndarray,
    *,
    frame: int,
    block: tuple[int, int, int],
    crop_origin: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, dict]:
    y0, x0 = crop_origin
    guess = -shifts[frame].astype(np.float64)
    center = np.array(raw.shape[1:]) // 2
    offset = center - np.array(block) // 2
    offset[1:] = np.clip(
        offset[1:] + np.rint(guess[1:]).astype(int) // 2,
        8,
        np.array(raw.shape[2:]) - np.array(block[1:]) - 8,
    )
    raw_slices = tuple(
        slice(start, start + size)
        for start, size in zip(offset, block, strict=True)
    )
    added, truth_rmse, _ = fit_translation(
        raw[0],
        raw[frame][raw_slices],
        guess,
        target_offset=tuple(offset),
        round_uint16=False,
    )

    fz, fy, fx = central_block(fiji.shape[1:], block)
    applied, fiji_rmse, exact = fit_translation(
        raw[frame],
        fiji[frame][fz, fy, fx],
        shifts[frame].astype(np.float64),
        target_offset=(fz.start, fy.start + y0, fx.start + x0),
        round_uint16=True,
    )
    quality = {
        "frame": frame,
        "truth_fit_rmse": truth_rmse,
        "fiji_fit_rmse": fiji_rmse,
        "fiji_fit_identical_voxel_fraction": exact,
    }
    return added, applied, quality


def recover_reference_translations(
    raw: np.ndarray,
    fiji: np.ndarray,
    shifts: np.ndarray,
    *,
    crop_origin: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Recover generator and Fiji translations with the ImageJ forward model."""
    frames = raw.shape[0]
    block = (
        max(4, min(20, raw.shape[1] // 3)),
        min(80, fiji.shape[2] // 2),
        min(80, fiji.shape[3] // 2),
    )
    truth_added = np.zeros((frames, 3))
    fiji_translation = np.zeros((frames, 3))
    fit_quality: list[dict] = []

    for frame in range(1, frames):
        added, applied, quality = _fit_reference_frame(
            raw,
            fiji,
            shifts,
            frame=frame,
            block=block,
            crop_origin=crop_origin,
        )
        truth_added[frame] = added
        fiji_translation[frame] = applied
        fit_quality.append(quality)
        print(
            f"frame {frame}: truth {-added.round(3)} "
            f"fiji {applied.round(3)} ours {shifts[frame].round(3)}"
        )

    return -truth_added, fiji_translation, fit_quality


def expected_translations(
    recovered: np.ndarray,
    *,
    ground_truth_csv: Path | None,
) -> tuple[np.ndarray, str]:
    if ground_truth_csv is None:
        return recovered, "recovered by forward fitting raw frame 0 to raw frame t"

    published = load_ground_truth_csv(ground_truth_csv, recovered.shape[0])
    expected = -published[:, ::-1]
    expected[0] = 0
    return expected, f"published table {ground_truth_csv}"


def published_subset_difference(
    expected: np.ndarray,
    *,
    self_test: bool,
) -> dict[str, list[float]]:
    if self_test:
        return {}
    published = {
        frame: (-np.asarray(values[::-1]) if frame else np.zeros(3))
        for frame, values in PUBLISHED_SUBSET.items()
        if frame < expected.shape[0]
    }
    return {
        str(frame): (translation - expected[frame]).tolist()
        for frame, translation in published.items()
    }


def settings_sweep(
    raw: np.ndarray,
    fiji_translation: np.ndarray,
    *,
    workers: int,
) -> dict:
    """Compare deliberate setting changes with the recovered Fiji shifts."""
    variants = {
        "principal (max, first, Top, no averaging, auto search)": {},
        "average projection": {"projection": "mean"},
        "previous-frame reference": {"reference": "previous"},
        "Left reslice (axial projection over X)": {"axial_projection_axis": "X"},
        "crop before Z estimation": {"crop_output": True},
        "time averaging 2": {"time_averaging": 2},
    }
    sweep = {}
    for label, change in variants.items():
        options = {
            "axes": "TZYX",
            "projection": "max",
            "reference": "first",
            "correct_z": True,
            "axial_projection_axis": "Y",
            "workers": workers,
            **change,
        }
        try:
            estimate = estimate_time_drift(raw, **options)
        except ValueError as error:
            # A rejected Fiji failure mode is itself a result of this sweep.
            sweep[label] = {"rejected": str(error)}
            continue
        difference = np.abs(estimate - fiji_translation)
        sweep[label] = {
            "max_abs_vs_fiji_dzdydx": difference.max(axis=0).tolist(),
            "mean_abs_vs_fiji_dzdydx": difference.mean(axis=0).tolist(),
        }
    return sweep


def crop_formula_report(
    fiji_translation: np.ndarray,
    raw_shape: tuple[int, ...],
    archived_crop: tuple[int, int, int, int],
) -> dict:
    y0, y1, x0, x1 = fiji_crop_bounds(
        fiji_translation,
        raw_shape[2],
        raw_shape[3],
    )
    expected = (y0, x0, y1 - y0, x1 - x0)
    return {
        "y0": y0,
        "x0": x0,
        "height": y1 - y0,
        "width": x1 - x0,
        "matches_archive": expected == archived_crop,
    }


def axis_summaries(
    shifts: np.ndarray,
    expected: np.ndarray,
    fiji_translation: np.ndarray,
    cropped_shifts: np.ndarray,
) -> dict:
    names = ("dz", "dy", "dx")
    summary = {
        "per_axis_vs_truth": {},
        "per_axis_vs_fiji": {},
        "fiji_vs_truth": {},
        "crop_before_z_vs_fiji": {},
    }
    for axis, name in enumerate(names):
        summary["per_axis_vs_truth"][name] = axis_statistics(
            shifts[:, axis] - expected[:, axis]
        )
        summary["per_axis_vs_fiji"][name] = axis_statistics(
            shifts[:, axis] - fiji_translation[:, axis]
        )
        summary["fiji_vs_truth"][name] = axis_statistics(
            fiji_translation[:, axis] - expected[:, axis]
        )
        summary["crop_before_z_vs_fiji"][name] = axis_statistics(
            cropped_shifts[:, axis] - fiji_translation[:, axis]
        )
    return summary


def find_archived_crop(raw: np.ndarray, fiji: np.ndarray) -> tuple[int, int, int, int]:
    y0, x0 = locate_fiji_crop(raw[0], fiji[0])
    height, width = fiji.shape[-2:]
    return y0, x0, height, width
