"""Time Fiji Fast4DReg and Fast4DRegPy on the published full movie."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import json
import resource
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import tifffile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "full_movie"))
sys.path.insert(0, str(HERE))

from data import extract, fetch_archive  # noqa: E402
from make_macro_fixtures import FIRST, read_njt  # noqa: E402
from metrics import pearson  # noqa: E402
from process_metrics import PeakRss  # noqa: E402

from fast4dreg import apply_drift, estimate_time_drift  # noqa: E402

SETTINGS = {
    "exp_nro": 1,
    "XY_registration": True,
    "projection_type_xy": "Max Intensity",
    "time_xy": 1,
    "max_xy": 0,
    "reference_xy": FIRST,
    "crop_output": True,
    "z_registration": True,
    "projection_type_z": "Max Intensity",
    "reslice_mode": "Top",
    "time_z": 1,
    "max_z": 0,
    "reference_z": FIRST,
    "extend_stack_to_fit": False,
    "ram_conservative_mode": False,
}


def _one_match(directory: Path, pattern: str) -> Path:
    matches = list(directory.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {pattern!r} in {directory}, found {len(matches)}"
        )
    return matches[0]


def _macro_seconds(log: str) -> float:
    values = []
    for line in log.splitlines():
        if "Time taken:" in line:
            values.append(float(line.split("Time taken:")[1].split("s")[0]))
    if len(values) != 1:
        raise RuntimeError(
            f"expected one Fiji 'Time taken:' entry, found {len(values)}"
        )
    return values[0]


def run_fiji(imagej: Path, macro: Path, raw_path: Path, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    settings = {**SETTINGS, "files": str(raw_path)}
    (work / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    for stale in raw_path.parent.glob(raw_path.stem + "_*"):
        if stale.is_dir():
            shutil.rmtree(stale)
    before = {path for path in raw_path.parent.iterdir() if path.is_dir()}

    start = time.perf_counter()
    with PeakRss() as rss:
        completed = subprocess.run(
            [
                HERE / "run_fiji_macro.sh",
                imagej,
                macro,
                work / "settings.json",
                work / "run",
                "10800",
            ],
            capture_output=True,
            text=True,
        )
    wall_seconds = time.perf_counter() - start
    if completed.returncode != 0:
        raise RuntimeError(f"Fiji failed:\n{completed.stdout}\n{completed.stderr}")

    new_directories = [
        path
        for path in raw_path.parent.iterdir()
        if path.is_dir() and path not in before
    ]
    if len(new_directories) != 1:
        raise RuntimeError(
            "Fiji should create exactly one results directory; "
            f"found {new_directories}"
        )

    log = (work / "run" / "fiji_log.txt").read_text(encoding="utf-8")
    return {
        "wall_seconds_including_jvm_start": wall_seconds,
        "macro_reported_seconds": _macro_seconds(log),
        "peak_java_rss_gb": rss.peak / 1e9,
        "results_dir": new_directories[0],
        "log": log,
    }


def run_python(raw: np.ndarray, workers: int) -> dict:
    options = {
        "axes": "TZYX",
        "projection": "max",
        "reference": "first",
        "correct_xy": True,
        "correct_z": True,
        "axial_projection_axis": "Y",
        "time_averaging": 1,
        "max_expected_drift": 0,
        "crop_output": True,
        "workers": workers,
    }
    start = time.perf_counter()
    shifts = estimate_time_drift(raw, **options)
    estimated = time.perf_counter()
    corrected = apply_drift(
        raw,
        shifts,
        axes="TZYX",
        crop_output=True,
        workers=workers,
    )
    finished = time.perf_counter()
    return {
        "shifts": shifts,
        "corrected": corrected,
        "estimate_seconds": estimated - start,
        "apply_seconds": finished - estimated,
        "total_seconds": finished - start,
    }


def _read_fiji_outputs(results_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    xy = read_njt(_one_match(results_dir, "*_xy_DriftTable.njt"))
    z = read_njt(_one_match(results_dir, "*_z_DriftTable.njt"))
    shifts = np.column_stack(
        [z["Y-Drift (pixels)"], xy["Y-Drift (pixels)"], xy["X-Drift (pixels)"]]
    )
    corrected = tifffile.imread(_one_match(results_dir, "*_xyzCorrected.tif"))
    return shifts, corrected


def _run_python_variants(raw: np.ndarray, workers: int) -> dict[int, dict]:
    runs = {
        count: run_python(raw, count)
        for count in sorted({1, workers})
    }
    for count, run in runs.items():
        print(f"Fast4DRegPy workers={count}: {run['total_seconds']:.1f} s")
    return runs


def _compare_outputs(
    *,
    raw: np.ndarray,
    archived: np.ndarray,
    fiji_output: np.ndarray,
    fiji_shifts: np.ndarray,
    python: dict[int, dict],
) -> dict:
    ours = python[1]
    if ours["corrected"].shape != fiji_output.shape:
        raise RuntimeError(
            "Fast4DRegPy and fresh Fiji output shapes differ: "
            f"{ours['corrected'].shape} vs {fiji_output.shape}"
        )

    height = min(fiji_output.shape[2], archived.shape[2])
    width = min(fiji_output.shape[3], archived.shape[3])
    fresh_vs_archive = [
        pearson(
            fiji_output[frame, :, :height, :width],
            archived[frame, :, :height, :width],
        )
        for frame in range(raw.shape[0])
    ]
    fresh_rounded = np.clip(
        np.floor(fiji_output[:, :, :height, :width] + 0.5),
        0,
        65535,
    )
    identical_to_archive = float(
        np.mean(fresh_rounded == archived[:, :, :height, :width])
    )
    ours_vs_fresh = [
        pearson(ours["corrected"][frame], fiji_output[frame])
        for frame in range(raw.shape[0])
    ]
    difference = np.abs(ours["shifts"] - fiji_shifts)

    return {
        "fiji_output_shape": list(fiji_output.shape),
        "fiji_output_dtype": str(fiji_output.dtype),
        "fast4dregpy_output_shape": list(ours["corrected"].shape),
        "archived_shape": list(archived.shape),
        "max_abs_fast4dregpy_minus_fiji_dzdydx": difference.max(axis=0).tolist(),
        "mean_abs_fast4dregpy_minus_fiji_dzdydx": difference.mean(axis=0).tolist(),
        "fresh_fiji_vs_archive_pearson_min": min(fresh_vs_archive),
        "fresh_fiji_vs_archive_identical_voxels_after_uint16": identical_to_archive,
        "fast4dregpy_vs_fresh_fiji_pearson_min": min(ours_vs_fresh),
    }


def _result(
    *,
    fiji: dict,
    python: dict[int, dict],
    parity: dict,
    fiji_shifts: np.ndarray,
) -> dict:
    ours = python[1]
    return {
        "machine": {
            "cpus": os.cpu_count(),
            "omp_num_threads": os.environ["OMP_NUM_THREADS"],
        },
        "settings": SETTINGS,
        "fiji": {
            key: value
            for key, value in fiji.items()
            if key not in ("results_dir", "log")
        },
        "fast4dregpy": {
            str(workers): {
                key: run[key]
                for key in ("estimate_seconds", "apply_seconds", "total_seconds")
            }
            for workers, run in python.items()
        },
        "fast4dregpy_process_peak_rss_gb": resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss
        / 1e6,
        "serial_equals_parallel": bool(
            all(
                np.array_equal(run["shifts"], ours["shifts"])
                for run in python.values()
            )
            and all(
                np.array_equal(run["corrected"], ours["corrected"])
                for run in python.values()
            )
        ),
        **parity,
        "fiji_drift_table_dzdydx": fiji_shifts.tolist(),
        "fast4dregpy_dzdydx": ours["shifts"].tolist(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("imagej_dir", type=Path)
    parser.add_argument("macro", type=Path, help="original time_estimate+apply.ijm")
    parser.add_argument("--data-dir", type=Path, default=Path(".validation-data"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("validation-results/fiji-timing"),
    )
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    return parser


def main() -> int:
    args = _parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    archive = fetch_archive(args.data_dir, download=args.download)
    raw_path, fiji_path, _ = extract(archive, args.data_dir)
    raw = tifffile.imread(raw_path)
    archived = tifffile.imread(fiji_path)

    fiji = run_fiji(
        args.imagej_dir,
        args.macro,
        raw_path,
        args.output_dir / "fiji-work",
    )
    print(
        f"Fiji: {fiji['wall_seconds_including_jvm_start']:.1f} s wall, "
        f"{fiji['macro_reported_seconds']:.1f} s reported, "
        f"peak {fiji['peak_java_rss_gb']:.2f} GB"
    )
    fiji_shifts, fiji_output = _read_fiji_outputs(fiji["results_dir"])
    python = _run_python_variants(raw, args.workers)
    parity = _compare_outputs(
        raw=raw,
        archived=archived,
        fiji_output=fiji_output,
        fiji_shifts=fiji_shifts,
        python=python,
    )
    result = _result(
        fiji=fiji,
        python=python,
        parity=parity,
        fiji_shifts=fiji_shifts,
    )

    (args.output_dir / "timing_and_parity.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "fiji_log.txt").write_text(
        fiji["log"],
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if not key.endswith("dzdydx")
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
