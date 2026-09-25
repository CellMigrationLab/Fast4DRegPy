"""Compare Fast4DRegPy with a fresh run of the Fiji macro on a Zenodo dataset.

For the chosen dataset, the script downloads and checks the Zenodo archive,
runs the original ``time_estimate+apply.ijm`` in ImageJ (see
``patch_macro.py``), runs Fast4DRegPy with the same settings on the same
machine, and compares:

- the drift tables, frame by frame;
- the corrected stacks;
- the fresh Fiji output with the Fiji result stored in the archive;
- run time and peak memory.

Usage::

    python validation/fiji/compare_with_fiji.py IMAGEJ_DIR MACRO \\
        --dataset huvec --download --output-dir validation-results/huvec
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import csv
import hashlib
import json
import resource
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import tifffile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from make_macro_fixtures import FIRST, PREVIOUS, read_njt  # noqa: E402
from process_metrics import PeakRss  # noqa: E402

from fast4dreg import apply_drift, estimate_time_drift  # noqa: E402

ZENODO_RECORD = "7514913"
BASE_SETTINGS = {
    "exp_nro": 1,
    "XY_registration": True,
    "projection_type_xy": "Max Intensity",
    "time_xy": 1,
    "max_xy": 0,
    "reference_xy": FIRST,
    "crop_output": False,
    "z_registration": True,
    "projection_type_z": "Max Intensity",
    "reslice_mode": "Top",
    "time_z": 1,
    "max_z": 0,
    "reference_z": FIRST,
    "extend_stack_to_fit": False,
    "ram_conservative_mode": False,
}
DATASETS = {
    "synthetic-large-drift": {
        "archive": "2-Synthetic-drift-dataset.zip",
        "md5": "27e3623f58d23d7c50674edc9432fe1b",
        "raw": "2-Synthetic-drift-dataset/2.1-Synthetic-drift-files/"
        "2.1.2-LargeDrift_original.tif",
        "archived_fiji": "2-Synthetic-drift-dataset/"
        "2.2-Synthetic-drift-expected-results/2.2.1-LargeDrift_F4DReg.tif",
        "axes": "TZYX",
        "settings": {**BASE_SETTINGS, "crop_output": True},
    },
    "huvec": {
        "archive": "4-HUVEC-monolayer-dataset.zip",
        "md5": "8fa5f595ed267d1c66b3f6b1b1237ef5",
        "raw": "4-HUVEC-monolayer-dataset/4.1-Image11_original.tif",
        "archived_fiji": "4-HUVEC-monolayer-dataset/4.2-Image11_Fast4D.tif",
        "axes": "TZYX",
        "settings": dict(BASE_SETTINGS),
    },
}
PROJECTIONS = {"Max Intensity": "max", "Average Intensity": "mean"}


# ------------------------------------------------------------------ data
def md5sum(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(dataset: dict, data_dir: Path, *, download: bool) -> tuple[Path, Path]:
    """Return verified paths to the raw and archived-Fiji TIFFs."""
    data_dir.mkdir(parents=True, exist_ok=True)
    archive = data_dir / dataset["archive"]
    if not archive.exists():
        if not download:
            raise FileNotFoundError(f"{archive} not found; pass --download")
        url = (
            f"https://zenodo.org/api/records/{ZENODO_RECORD}/files/"
            f"{dataset['archive']}/content"
        )
        partial = archive.with_suffix(".partial")
        urllib.request.urlretrieve(url, partial)
        partial.rename(archive)
    if md5sum(archive) != dataset["md5"]:
        raise RuntimeError(f"{archive} does not have MD5 {dataset['md5']}")
    with zipfile.ZipFile(archive) as bundle:
        for member in (dataset["raw"], dataset["archived_fiji"]):
            target = data_dir / member
            if (
                not target.exists()
                or target.stat().st_size != bundle.getinfo(member).file_size
            ):
                bundle.extract(member, data_dir)
    return data_dir / dataset["raw"], data_dir / dataset["archived_fiji"]


def python_options(settings: dict, axes: str) -> dict:
    """Translate Fiji macro settings into Fast4DRegPy keyword arguments."""
    for xy, z in (
        ("projection_type_xy", "projection_type_z"),
        ("reference_xy", "reference_z"),
        ("time_xy", "time_z"),
        ("max_xy", "max_z"),
    ):
        if settings[xy] != settings[z]:
            raise ValueError(f"Fast4DRegPy uses one value for {xy} and {z}")
    if settings["ram_conservative_mode"]:
        raise ValueError("Fiji 'Save RAM' is not reproduced by Fast4DRegPy")
    return {
        "axes": axes,
        "projection": PROJECTIONS[settings["projection_type_xy"]],
        "reference": {FIRST: "first", PREVIOUS: "previous"}[settings["reference_xy"]],
        "correct_xy": settings["XY_registration"],
        "correct_z": settings["z_registration"],
        "axial_projection_axis": {"Top": "Y", "Left": "X"}[settings["reslice_mode"]],
        "time_averaging": settings["time_xy"],
        "max_expected_drift": settings["max_xy"],
    }


# ------------------------------------------------------------------- Fiji
def _one_match(directory: Path, pattern: str) -> Path:
    matches = list(directory.glob(pattern))
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one {pattern!r} in {directory}, found {len(matches)}"
        )
    return matches[0]


def _macro_seconds(log: str) -> float:
    values = [
        float(line.split("Time taken:")[1].split("s")[0])
        for line in log.splitlines()
        if "Time taken:" in line
    ]
    if len(values) != 1:
        raise RuntimeError(
            f"expected one Fiji 'Time taken:' entry, found {len(values)}"
        )
    return values[0]


def run_fiji(
    imagej: Path, macro: Path, raw_path: Path, settings: dict, work: Path
) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    (work / "settings.json").write_text(
        json.dumps({**settings, "files": str(raw_path)}), encoding="utf-8"
    )
    # The macro writes to <stem>_<date>-<exp>; remove a stale folder first.
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
                "14400",
            ],
            capture_output=True,
            text=True,
        )
    seconds = time.perf_counter() - start
    if completed.returncode != 0:
        raise RuntimeError(f"Fiji failed:\n{completed.stdout}\n{completed.stderr}")
    new = [p for p in raw_path.parent.iterdir() if p.is_dir() and p not in before]
    if len(new) != 1:
        raise RuntimeError(f"Fiji should create one results directory, found {new}")
    results = new[0]
    log = (work / "run" / "fiji_log.txt").read_text()
    macro_seconds = _macro_seconds(log)
    xy = read_njt(_one_match(results, "*_xy_DriftTable.njt"))
    z = read_njt(_one_match(results, "*_z_DriftTable.njt"))
    shifts = np.column_stack(
        [z["Y-Drift (pixels)"], xy["Y-Drift (pixels)"], xy["X-Drift (pixels)"]]
    )
    return {
        "wall_seconds_including_jvm_start": seconds,
        "macro_reported_seconds": macro_seconds,
        "peak_java_rss_gb": rss.peak / 1e9,
        "shifts": shifts,
        "output_path": _one_match(results, "*_xyzCorrected.tif"),
        "log": log,
    }


# ---------------------------------------------------------------- Python
def run_python(raw: np.ndarray, options: dict, settings: dict, workers: int) -> dict:
    start = time.perf_counter()
    shifts = estimate_time_drift(
        raw, crop_output=settings["crop_output"], workers=workers, **options
    )
    estimated = time.perf_counter()
    corrected = apply_drift(
        raw,
        shifts,
        axes=options["axes"],
        axial_projection_axis=options["axial_projection_axis"],
        crop_output=settings["crop_output"],
        extend_z=settings["extend_stack_to_fit"],
        workers=workers,
    )
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


def rounded(volume: np.ndarray, dtype: np.dtype) -> np.ndarray:
    info = np.iinfo(dtype)
    return np.clip(np.floor(np.asarray(volume, np.float64) + 0.5), info.min, info.max)


def open_stack(path: Path) -> np.ndarray:
    """Memory-map an uncompressed TIFF when possible, else read it."""
    try:
        return tifffile.memmap(path, mode="r")
    except ValueError:
        return tifffile.imread(path)


# ------------------------------------------------------------------ main
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("imagej_dir", type=Path)
    parser.add_argument("macro", type=Path, help="original time_estimate+apply.ijm")
    parser.add_argument("--dataset", choices=sorted(DATASETS), required=True)
    parser.add_argument("--data-dir", type=Path, default=Path(".validation-data"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    dataset = DATASETS[args.dataset]
    settings = dataset["settings"]
    options = python_options(settings, dataset["axes"])
    raw_path, archived_path = fetch(dataset, args.data_dir, download=args.download)

    fiji = run_fiji(
        args.imagej_dir, args.macro, raw_path, settings, args.output_dir / "fiji-work"
    )
    print(
        f"Fiji: {fiji['macro_reported_seconds']:.1f} s, "
        f"peak {fiji['peak_java_rss_gb']:.1f} GB"
    )

    raw = tifffile.imread(raw_path)
    ours = run_python(raw, options, settings, workers=1)
    print(f"Fast4DRegPy workers=1: {ours['total_seconds']:.1f} s")
    parallel = run_python(raw, options, settings, workers=args.workers)
    print(f"Fast4DRegPy workers={args.workers}: {parallel['total_seconds']:.1f} s")
    identical = bool(
        np.array_equal(parallel["shifts"], ours["shifts"])
        and np.array_equal(parallel["corrected"], ours["corrected"])
    )
    timing_parallel = {
        k: parallel[k] for k in ("estimate_seconds", "apply_seconds", "total_seconds")
    }
    del parallel
    python_peak_gb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6

    fresh = open_stack(fiji["output_path"])
    archived = open_stack(archived_path)
    if ours["corrected"].shape != fresh.shape:
        raise RuntimeError(
            "Fast4DRegPy and fresh Fiji output shapes differ: "
            f"{ours['corrected'].shape} vs {fresh.shape}"
        )
    frames = raw.shape[0]
    rows = []
    for t in range(frames):
        row = {"frame": t}
        for axis, name in enumerate(("dz", "dy", "dx")):
            row[f"fiji_{name}"] = float(fiji["shifts"][t, axis])
            row[f"fast4dregpy_{name}"] = float(ours["shifts"][t, axis])
            row[f"difference_{name}"] = float(
                ours["shifts"][t, axis] - fiji["shifts"][t, axis]
            )
        row["pearson_vs_fresh_fiji"] = pearson(ours["corrected"][t], fresh[t])
        row["identical_voxels_vs_fresh_fiji"] = float(
            np.mean(
                rounded(ours["corrected"][t], raw.dtype) == rounded(fresh[t], raw.dtype)
            )
        )
        if archived.shape == fresh.shape:
            row["fresh_fiji_identical_to_archive"] = float(
                np.mean(rounded(fresh[t], archived.dtype) == archived[t])
            )
            row["pearson_fresh_fiji_vs_archive"] = pearson(fresh[t], archived[t])
            row["pearson_vs_archive"] = (
                pearson(ours["corrected"][t], archived[t])
                if ours["corrected"].shape == archived.shape
                else None
            )
        rows.append(row)
    with (args.output_dir / "per_frame.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    difference = np.abs(ours["shifts"] - fiji["shifts"])

    def minimum(key: str):
        values = [r[key] for r in rows if r.get(key) is not None]
        return min(values) if values else None

    result = {
        "dataset": {k: v for k, v in dataset.items() if k != "settings"},
        "raw_shape": list(raw.shape),
        "raw_dtype": str(raw.dtype),
        "fiji_settings": settings,
        "fast4dregpy_options": {
            **options,
            "crop_output": settings["crop_output"],
            "extend_z": settings["extend_stack_to_fit"],
        },
        "machine": {
            "cpus": os.cpu_count(),
            "omp_num_threads": os.environ["OMP_NUM_THREADS"],
        },
        "fiji": {
            k: v for k, v in fiji.items() if k not in ("shifts", "output_path", "log")
        },
        "fast4dregpy": {
            "1": {
                k: ours[k]
                for k in ("estimate_seconds", "apply_seconds", "total_seconds")
            },
            str(args.workers): timing_parallel,
            "peak_rss_gb": python_peak_gb,
        },
        "serial_equals_parallel": identical,
        "fresh_fiji_shape": list(fresh.shape),
        "fast4dregpy_shape": list(ours["corrected"].shape),
        "archived_shape": list(archived.shape),
        "max_abs_difference_dzdydx": difference.max(axis=0).tolist(),
        "mean_abs_difference_dzdydx": difference.mean(axis=0).tolist(),
        "max_abs_fiji_drift_dzdydx": np.abs(fiji["shifts"]).max(axis=0).tolist(),
        "min_pearson_vs_fresh_fiji": minimum("pearson_vs_fresh_fiji"),
        "min_identical_voxels_vs_fresh_fiji": minimum("identical_voxels_vs_fresh_fiji"),
        "min_fresh_fiji_identical_to_archive": minimum(
            "fresh_fiji_identical_to_archive"
        ),
        "min_pearson_fresh_fiji_vs_archive": minimum("pearson_fresh_fiji_vs_archive"),
        "min_pearson_vs_archive": minimum("pearson_vs_archive"),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    (args.output_dir / "fiji_log.txt").write_text(fiji["log"], encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
