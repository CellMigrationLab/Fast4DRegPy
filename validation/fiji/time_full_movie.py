"""Time the original Fiji macro and Fast4DRegPy on the full published movie.

Runs the unmodified ``time_estimate+apply.ijm`` (patched only for headless
parameters, see ``patch_macro.py``) in ImageJ under Xvfb on the complete
25 x 69 x 416 x 416 synthetic large-drift movie, then runs Fast4DRegPy with
the same settings on the same machine. Records wall time and peak memory for
both, and compares Fiji's drift tables and corrected stack with Fast4DRegPy
and with the archived Fiji result.

Usage::

    python validation/fiji/time_full_movie.py IMAGEJ_DIR FAST4DREG_MACRO \\
        --data-dir .validation-data --output-dir validation-results/fiji-timing
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import json
import resource
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import tifffile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "full_movie"))
sys.path.insert(0, str(HERE))

import validate_large_drift as full  # noqa: E402
from make_macro_fixtures import FIRST, read_njt  # noqa: E402

from fast4dreg import apply_drift, estimate_time_drift  # noqa: E402

# Settings inferred for the archived result (docs/full_movie_validation.md).
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


class PeakRss:
    """Sample the summed RSS of all java processes once per second."""

    def __init__(self) -> None:
        self.peak = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _rss(self) -> int:
        total = 0
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                if Path(f"/proc/{pid}/comm").read_text().strip() != "java":
                    continue
                for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        total += int(line.split()[1]) * 1024
            except OSError:
                continue
        return total

    def _run(self) -> None:
        while not self._stop.is_set():
            self.peak = max(self.peak, self._rss())
            self._stop.wait(1.0)

    def __enter__(self) -> PeakRss:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join()


def run_fiji(imagej: Path, macro: Path, raw_path: Path, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    settings = {**SETTINGS, "files": str(raw_path)}
    (work / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    # The macro names its results folder <stem>_<date>-<exp>; remove a stale
    # one so this run's output is unambiguous.
    for stale in raw_path.parent.glob(raw_path.stem + "_*"):
        if stale.is_dir():
            shutil.rmtree(stale)
    before = {p for p in raw_path.parent.iterdir() if p.is_dir()}
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
    seconds = time.perf_counter() - start
    if completed.returncode != 0:
        raise RuntimeError(f"Fiji failed:\n{completed.stdout}\n{completed.stderr}")
    (results,) = [
        p for p in raw_path.parent.iterdir() if p.is_dir() and p not in before
    ]
    log = (work / "run" / "fiji_log.txt").read_text()
    macro_seconds = None
    for line in log.splitlines():
        if "Time taken:" in line:
            macro_seconds = float(line.split("Time taken:")[1].split("s")[0])
    return {
        "wall_seconds_including_jvm_start": seconds,
        "macro_reported_seconds": macro_seconds,
        "peak_java_rss_gb": rss.peak / 1e9,
        "results_dir": results,
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
    corrected = apply_drift(raw, shifts, axes="TZYX", crop_output=True, workers=workers)
    done = time.perf_counter()
    return {
        "shifts": shifts,
        "corrected": corrected,
        "estimate_seconds": estimated - start,
        "apply_seconds": done - estimated,
        "total_seconds": done - start,
    }


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(np.ravel(a), np.ravel(b))[0, 1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("imagej_dir", type=Path)
    parser.add_argument("macro", type=Path, help="original time_estimate+apply.ijm")
    parser.add_argument("--data-dir", type=Path, default=Path(".validation-data"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("validation-results/fiji-timing")
    )
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    archive = full.fetch_archive(args.data_dir, download=args.download)
    raw_path, fiji_path, _ = full.extract(archive, args.data_dir)

    fiji = run_fiji(
        args.imagej_dir, args.macro, raw_path, args.output_dir / "fiji-work"
    )
    print(
        f"Fiji: {fiji['wall_seconds_including_jvm_start']:.1f} s wall, "
        f"{fiji['macro_reported_seconds']} s reported, "
        f"peak {fiji['peak_java_rss_gb']:.2f} GB"
    )
    xy = read_njt(next(fiji["results_dir"].glob("*_xy_DriftTable.njt")))
    z = read_njt(next(fiji["results_dir"].glob("*_z_DriftTable.njt")))
    fiji_shifts = np.column_stack(
        [z["Y-Drift (pixels)"], xy["Y-Drift (pixels)"], xy["X-Drift (pixels)"]]
    )
    fiji_output = tifffile.imread(next(fiji["results_dir"].glob("*_xyzCorrected.tif")))

    raw = tifffile.imread(raw_path)
    archived = tifffile.imread(fiji_path)
    python = {}
    for workers in sorted({1, args.workers}):
        python[workers] = run_python(raw, workers)
        print(
            f"Fast4DRegPy workers={workers}: {python[workers]['total_seconds']:.1f} s"
        )
    ours = python[1]

    # Fresh Fiji output vs archived Fiji output: same origin (frame 0 is
    # never moved), compare the common region.
    height = min(fiji_output.shape[2], archived.shape[2])
    width = min(fiji_output.shape[3], archived.shape[3])
    fresh_vs_archive = [
        pearson(fiji_output[t, :, :height, :width], archived[t, :, :height, :width])
        for t in range(raw.shape[0])
    ]
    fresh_rounded = np.clip(
        np.floor(fiji_output[:, :, :height, :width] + 0.5), 0, 65535
    )
    identical_to_archive = float(
        np.mean(fresh_rounded == archived[:, :, :height, :width])
    )
    ours_vs_fresh = (
        [pearson(ours["corrected"][t], fiji_output[t]) for t in range(raw.shape[0])]
        if ours["corrected"].shape == fiji_output.shape
        else None
    )
    difference = np.abs(ours["shifts"] - fiji_shifts)

    result = {
        "machine": {
            "cpus": os.cpu_count(),
            "omp_num_threads": os.environ["OMP_NUM_THREADS"],
        },
        "settings": SETTINGS,
        "fiji": {k: v for k, v in fiji.items() if k not in ("results_dir", "log")},
        "fast4dregpy": {
            str(w): {
                k: r[k] for k in ("estimate_seconds", "apply_seconds", "total_seconds")
            }
            for w, r in python.items()
        },
        "fast4dregpy_process_peak_rss_gb": resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss
        / 1e6,
        "serial_equals_parallel": bool(
            all(np.array_equal(r["shifts"], ours["shifts"]) for r in python.values())
            and all(
                np.array_equal(r["corrected"], ours["corrected"])
                for r in python.values()
            )
        ),
        "fiji_output_shape": list(fiji_output.shape),
        "fiji_output_dtype": str(fiji_output.dtype),
        "fast4dregpy_output_shape": list(ours["corrected"].shape),
        "archived_shape": list(archived.shape),
        "max_abs_fast4dregpy_minus_fiji_dzdydx": difference.max(axis=0).tolist(),
        "mean_abs_fast4dregpy_minus_fiji_dzdydx": difference.mean(axis=0).tolist(),
        "fresh_fiji_vs_archive_pearson_min": min(fresh_vs_archive),
        "fresh_fiji_vs_archive_identical_voxels_after_uint16": identical_to_archive,
        "fast4dregpy_vs_fresh_fiji_pearson_min": min(ours_vs_fresh)
        if ours_vs_fresh
        else None,
        "fiji_drift_table_dzdydx": fiji_shifts.tolist(),
        "fast4dregpy_dzdydx": ours["shifts"].tolist(),
    }
    (args.output_dir / "timing_and_parity.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (args.output_dir / "fiji_log.txt").write_text(fiji["log"], encoding="utf-8")
    print(
        json.dumps(
            {k: v for k, v in result.items() if not k.endswith("dzdydx")}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
