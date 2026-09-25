"""Full-movie validation of Fast4DRegPy against the published Fast4DReg data.

Runs Fast4DRegPy on every timepoint and Z plane of the published synthetic
large-drift movie (Zenodo record 7514913, ``2-Synthetic-drift-dataset.zip``)
and compares it with

1. the synthetic drift actually added to every frame (ground truth),
2. the archived Fiji Fast4DReg output ``2.2.1-LargeDrift_F4DReg.tif``,
3. the unregistered movie.

The archive and its members are verified against pinned checksums; another
record, version or file is never substituted. Results (CSV, JSON, PNG) are
written to ``--output-dir`` and the script exits non-zero if any parity gate
fails. See ``validation/README.md``.

Ground truth. ``Drift_generator.ijm`` leaves frame 0 untouched and translates
frame ``t`` by the drift in the published table (Fig. S1A). Only five of those
values are available in machine-readable form (tests/data manifests), so the
added displacement of every frame is *recovered* by fitting the ImageJ
two-pass bicubic translation of raw frame 0 to raw frame ``t`` (a forward
model of the generator). Recovered values are cross-checked against the five
published values, and a complete published table can be supplied with
``--ground-truth-csv``.

Fiji reference. The archived Fiji output is 32-bit Fiji output converted once
to uint16 and cropped. The crop offset is located by exact matching of frame 0
(which Fiji never moves), and Fiji's applied translation for every frame is
recovered by fitting the same forward model to the archived frame. This yields
Fiji's per-frame drift table, which is not archived.
"""

from __future__ import annotations

import os
import sys

# NanoPyx 2.1.4 uses OpenMP reductions whose summation order depends on the
# thread count, which changes drift estimates by up to ~0.001 px between runs.
# Pin the OpenMP thread count before NanoPyx is imported (recorded in results).
if "--omp-threads" in sys.argv:
    os.environ["OMP_NUM_THREADS"] = sys.argv[sys.argv.index("--omp-threads") + 1]
else:
    os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import csv
import hashlib
import json
import platform
import resource
import subprocess
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
from scipy.optimize import minimize
from scipy.stats import spearmanr
from skimage.metrics import structural_similarity

import fast4dreg
from fast4dreg import apply_drift, estimate_time_drift, fiji_crop_bounds
from fast4dreg._imagej import translate_volume

REPOSITORY = Path(__file__).resolve().parents[2]
ZENODO_RECORD = "7514913"
ARCHIVE = "2-Synthetic-drift-dataset.zip"
ARCHIVE_MD5 = "27e3623f58d23d7c50674edc9432fe1b"
RAW_MEMBER = (
    "2-Synthetic-drift-dataset/2.1-Synthetic-drift-files/2.1.2-LargeDrift_original.tif"
)
FIJI_MEMBER = (
    "2-Synthetic-drift-dataset/2.2-Synthetic-drift-expected-results/"
    "2.2.1-LargeDrift_F4DReg.tif"
)
# Published Fig. S1A drift (x, y, z pixels) available in machine-readable form.
PUBLISHED_SUBSET = {
    0: (-0.1846, -0.842, 0.7736),
    6: (4.83, -2.012, -2.4789),
    12: (15.5335, -25.244, -7.4236),
    18: (34.7591, -71.216, -10.8287),
    24: (62.7437, -137.609, -14.8706),
}
# Gates. "baseline" repeats the compact-fixture thresholds that predate this
# validation; "strict" is the level measured on the compact frame-6 fixture
# (see docs/full_movie_validation.md) and must be confirmed on the full run.
GATES = {
    "baseline": {"truth_px": 0.75, "fiji_px": 0.75, "pearson": 0.98},
    "strict": {"truth_px": 0.1, "fiji_px": 0.02, "pearson": 0.9999},
}
REPRESENTATIVE_Z = (17, 34, 51)


@dataclass
class Movie:
    raw: np.ndarray
    fiji: np.ndarray
    metadata: dict


# --------------------------------------------------------------------- data
def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_archive(data_dir: Path, *, download: bool) -> Path:
    """Return the verified archive, downloading it only when requested."""
    archive = data_dir / ARCHIVE
    if not archive.exists():
        if not download:
            raise FileNotFoundError(
                f"{archive} not found. Pass --download to fetch it from Zenodo "
                f"record {ZENODO_RECORD}, or place the verified archive there."
            )
        with urllib.request.urlopen(
            f"https://zenodo.org/api/records/{ZENODO_RECORD}", timeout=60
        ) as response:
            record = json.load(response)
        entries = [f for f in record["files"] if f["key"] == ARCHIVE]
        if len(entries) != 1:
            raise RuntimeError(f"{ARCHIVE} is not in Zenodo record {ZENODO_RECORD}")
        if entries[0]["checksum"] != f"md5:{ARCHIVE_MD5}":
            raise RuntimeError(
                f"Zenodo reports checksum {entries[0]['checksum']} for {ARCHIVE}; "
                f"expected md5:{ARCHIVE_MD5}. Refusing a different dataset version."
            )
        partial = archive.with_suffix(".partial")
        print(f"downloading {entries[0]['links']['self']} ({entries[0]['size']} B)")
        urllib.request.urlretrieve(entries[0]["links"]["self"], partial)
        partial.rename(archive)
    checksum = _md5(archive)
    if checksum != ARCHIVE_MD5:
        raise RuntimeError(
            f"{archive} has MD5 {checksum}, expected {ARCHIVE_MD5}; delete it and "
            "download again. No other dataset version is accepted."
        )
    return archive


def extract(archive: Path, data_dir: Path) -> tuple[Path, Path, list[str]]:
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        for member in (RAW_MEMBER, FIJI_MEMBER):
            if member not in names:
                raise RuntimeError(f"{member} missing from {archive}")
            target = data_dir / member
            if (
                not target.exists()
                or target.stat().st_size != bundle.getinfo(member).file_size
            ):
                target.parent.mkdir(parents=True, exist_ok=True)
                bundle.extract(member, data_dir)
    return data_dir / RAW_MEMBER, data_dir / FIJI_MEMBER, names


def tiff_metadata(path: Path) -> dict:
    with tifffile.TiffFile(path) as tif:
        series = tif.series[0]
        page = tif.pages[0]
        info = {
            "shape": list(series.shape),
            "axes": series.axes,
            "dtype": str(series.dtype),
            "imagej_metadata": {
                k: v for k, v in (tif.imagej_metadata or {}).items() if k != "Info"
            },
        }
        resolution = page.tags.get("XResolution")
        if resolution is not None:
            num, den = resolution.value
            info["x_pixels_per_unit"] = num / den
        resolution = page.tags.get("YResolution")
        if resolution is not None:
            num, den = resolution.value
            info["y_pixels_per_unit"] = num / den
        return info


def load(data_dir: Path, *, download: bool) -> tuple[Movie, dict]:
    archive = fetch_archive(data_dir, download=download)
    raw_path, fiji_path, names = extract(archive, data_dir)
    provenance = {
        "zenodo_record": ZENODO_RECORD,
        "archive": ARCHIVE,
        "archive_md5": ARCHIVE_MD5,
        "raw_member": RAW_MEMBER,
        "raw_sha256": _sha256(raw_path),
        "fiji_member": FIJI_MEMBER,
        "fiji_sha256": _sha256(fiji_path),
        "raw_metadata": tiff_metadata(raw_path),
        "fiji_metadata": tiff_metadata(fiji_path),
        # Any settings file or drift table in the archive is evidence for the
        # Fiji settings; list everything next to the Fiji result.
        "expected_results_members": [
            n for n in names if "2.2-Synthetic-drift-expected-results" in n
        ],
        "possible_settings_or_tables": [
            n for n in names if n.lower().endswith((".csv", ".njt", ".txt", ".xlsx"))
        ],
    }
    raw = tifffile.imread(raw_path)
    fiji = tifffile.imread(fiji_path)
    return Movie(raw=raw, fiji=fiji, metadata=provenance), provenance


# ---------------------------------------------------------- forward models
def _fit_translation(
    source: np.ndarray,
    target: np.ndarray,
    initial: np.ndarray,
    *,
    target_offset: tuple[int, int, int],
    round_uint16: bool,
    margin: int = 6,
) -> tuple[np.ndarray, float, float]:
    """Fit ``target ~ T(source, d)`` (ImageJ two-pass bicubic), return ``d``.

    ``target`` is a sub-block of the translated source at ``target_offset``
    (z, y, x). Only the region of ``source`` that can reach the target block
    is translated, so full-size volumes stay affordable.
    """
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    tz, ty, tx = target_offset
    shape = target.shape
    whole = np.rint(initial).astype(int)

    def block(d: np.ndarray) -> np.ndarray:
        # Source window covering target - round(d), padded for interpolation.
        start = np.array([tz, ty, tx]) - whole - margin
        stop = start + np.array(shape) + 2 * margin
        clipped_start = np.maximum(start, 0)
        clipped_stop = np.minimum(stop, source.shape)
        window = np.zeros(tuple(stop - start))
        inner = tuple(
            slice(a - s, b - s)
            for a, b, s in zip(clipped_start, clipped_stop, start, strict=True)
        )
        window[inner] = source[
            tuple(slice(a, b) for a, b in zip(clipped_start, clipped_stop, strict=True))
        ]
        moved = translate_volume(window, d - whole, axial_projection_axis="Y")
        # Translating the window instead of the whole volume changes ImageJ's
        # edge rule only within `margin` of the window, which is discarded.
        moved = moved[margin:-margin, margin:-margin, margin:-margin]
        return np.clip(np.floor(moved + 0.5), 0, 65535) if round_uint16 else moved

    def cost(d: np.ndarray) -> float:
        return float(np.mean((block(d) - target) ** 2))

    result = minimize(
        cost,
        np.asarray(initial, dtype=np.float64),
        method="Nelder-Mead",
        options={"xatol": 1e-4, "fatol": 1e-9, "maxiter": 600},
    )
    best = block(result.x)
    exact = float(np.mean(best == target)) if round_uint16 else float("nan")
    return result.x, float(np.sqrt(result.fun)), exact


def locate_fiji_crop(raw0: np.ndarray, fiji0: np.ndarray) -> tuple[int, int]:
    """Find the (y0, x0) at which Fiji's frame 0 is an exact crop of raw frame 0."""
    height, width = fiji0.shape[-2:]
    reference = fiji0[fiji0.shape[0] // 2]
    plane = raw0[raw0.shape[0] // 2]
    matches = [
        (y, x)
        for y in range(plane.shape[0] - height + 1)
        for x in range(plane.shape[1] - width + 1)
        if plane[y, x] == reference[0, 0]
        and np.array_equal(plane[y : y + height, x : x + width], reference)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one exact frame-0 crop match, found {matches}")
    y0, x0 = matches[0]
    if not np.array_equal(raw0[:, y0 : y0 + height, x0 : x0 + width], fiji0):
        raise RuntimeError("Fiji frame 0 is not an exact crop of raw frame 0")
    return y0, x0


def central_block(
    shape: tuple[int, ...], size: tuple[int, int, int]
) -> tuple[slice, ...]:
    return tuple(
        slice((n - s) // 2, (n - s) // 2 + s) for n, s in zip(shape, size, strict=True)
    )


# ---------------------------------------------------------------- metrics
def pearson(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(np.ravel(a), np.ravel(b))[0, 1])


def image_metrics(ours: np.ndarray, reference: np.ndarray, prefix: str) -> dict:
    a = np.asarray(ours, dtype=np.float64)
    b = np.asarray(reference, dtype=np.float64)
    span = float(b.max() - b.min())
    return {
        f"{prefix}_pearson": pearson(a, b),
        f"{prefix}_rmse": float(np.sqrt(np.mean((a - b) ** 2))),
        f"{prefix}_nrmse_range": float(np.sqrt(np.mean((a - b) ** 2)) / span),
        f"{prefix}_mae": float(np.mean(np.abs(a - b))),
        f"{prefix}_ssim": float(structural_similarity(a, b, data_range=span)),
    }


def axis_statistics(errors: np.ndarray) -> dict:
    absolute = np.abs(errors)
    return {
        "mean_abs": float(absolute.mean()),
        "median_abs": float(np.median(absolute)),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "max_abs": float(absolute.max()),
        "max_abs_frame": int(np.argmax(absolute)),
        "bias": float(errors.mean()),
    }


# --------------------------------------------------------------- running
def run_fast4dregpy(raw: np.ndarray, *, crop_output: bool, workers: int) -> dict:
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
    estimate_seconds = time.perf_counter() - start
    start = time.perf_counter()
    corrected = apply_drift(raw, shifts, axes="TZYX", workers=workers)
    apply_seconds = time.perf_counter() - start
    return {
        "settings": {**settings, "interpolation": "imagej", "output_dtype": "float32"},
        "shifts": shifts,
        "corrected": corrected,
        "estimate_seconds": estimate_seconds,
        "apply_seconds": apply_seconds,
    }


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPOSITORY), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_ground_truth_csv(path: Path, frames: int) -> np.ndarray:
    """Published per-frame drift as columns frame,x,y,z (displacement added)."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    table = np.asarray([[float(r["x"]), float(r["y"]), float(r["z"])] for r in rows])
    if [int(r["frame"]) for r in rows] != list(range(frames)):
        raise ValueError("ground-truth CSV must list frames 0..T-1 in order")
    return table


def validate(movie: Movie, args: argparse.Namespace, output: Path) -> bool:
    raw, fiji = movie.raw, movie.fiji
    if raw.ndim != 4 or fiji.ndim != 4 or raw.shape[:2] != fiji.shape[:2]:
        raise RuntimeError(f"unexpected shapes raw={raw.shape} fiji={fiji.shape}")
    frames = raw.shape[0]
    info: dict = {
        "fast4dregpy_version": fast4dreg.__version__,
        "fast4dregpy_commit": git_commit(),
        "python": sys.version,
        "platform": platform.platform(),
        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
        "dataset": movie.metadata,
    }
    import nanopyx
    import scipy

    info["versions"] = {
        "nanopyx": nanopyx.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "tifffile": tifffile.__version__,
    }

    # 1. Fast4DRegPy on the complete movie (principal run: no crop).
    runs = {}
    for workers in sorted({1, args.workers}):
        runs[workers] = run_fast4dregpy(raw, crop_output=False, workers=workers)
        print(
            f"workers={workers}: estimate {runs[workers]['estimate_seconds']:.1f} s, "
            f"apply {runs[workers]['apply_seconds']:.1f} s"
        )
    principal = runs[1]
    shifts = principal["shifts"]
    info["settings"] = principal["settings"]
    info["timing_seconds"] = {
        str(w): {"estimate": r["estimate_seconds"], "apply": r["apply_seconds"]}
        for w, r in runs.items()
    }
    info["serial_parallel_identical"] = {
        "shifts": bool(all(np.array_equal(r["shifts"], shifts) for r in runs.values())),
        "corrected": bool(
            all(
                np.array_equal(r["corrected"], principal["corrected"])
                for r in runs.values()
            )
        ),
    }
    for workers in list(runs):
        if workers != 1:
            del runs[workers]
    cropped_run = run_fast4dregpy(raw, crop_output=True, workers=args.workers)
    info["crop_before_z_hypothesis_shifts"] = cropped_run["shifts"].tolist()
    del cropped_run["corrected"]

    # 2. Map the archived Fiji output into raw coordinates.
    y0, x0 = locate_fiji_crop(raw[0], fiji[0])
    height, width = fiji.shape[-2:]
    info["fiji_crop"] = {"y0": y0, "x0": x0, "height": height, "width": width}

    # 3. Ground truth and Fiji translations recovered by forward fitting.
    # Blocks small enough that the fitted source window never reaches the
    # real volume boundary (where ImageJ's edge rule would differ).
    block = (
        max(4, min(20, raw.shape[1] // 3)),
        min(80, fiji.shape[2] // 2),
        min(80, fiji.shape[3] // 2),
    )
    truth_added = np.zeros((frames, 3))  # (dz, dy, dx) displacement added
    fiji_translation = np.zeros((frames, 3))
    fit_quality = []
    for t in range(1, frames):
        guess = -shifts[t].astype(np.float64)
        # Ground truth: raw[t] = generator(raw[0], d). Compare a central block
        # of raw[t] that stays inside raw[0] after the displacement.
        center = np.array(raw.shape[1:]) // 2
        offset = center - np.array(block) // 2
        # Target centred at c + d/2 so the source (c - d/2) is also inside.
        offset[1:] = np.clip(
            offset[1:] + np.rint(guess[1:]).astype(int) // 2,
            8,
            np.array(raw.shape[2:]) - np.array(block[1:]) - 8,
        )
        target = raw[t][
            tuple(slice(o, o + s) for o, s in zip(offset, block, strict=True))
        ]
        added, truth_rmse, _ = _fit_translation(
            raw[0], target, guess, target_offset=tuple(offset), round_uint16=False
        )
        truth_added[t] = added
        # Fiji: fiji[t] = round(T(raw[t], f)) cropped at (y0, x0).
        fz, fy, fx = central_block(fiji.shape[1:], block)
        target = fiji[t][fz, fy, fx]
        applied, fiji_rmse, exact = _fit_translation(
            raw[t],
            target,
            shifts[t].astype(np.float64),
            target_offset=(fz.start, fy.start + y0, fx.start + x0),
            round_uint16=True,
        )
        fiji_translation[t] = applied
        fit_quality.append(
            {
                "frame": t,
                "truth_fit_rmse": truth_rmse,
                "fiji_fit_rmse": fiji_rmse,
                "fiji_fit_identical_voxel_fraction": exact,
            }
        )
        print(
            f"frame {t}: truth {-added.round(3)} fiji {applied.round(3)} "
            f"ours {shifts[t].round(3)}"
        )
    expected = -truth_added
    info["ground_truth_source"] = (
        "recovered by forward fitting raw frame 0 to raw frame t"
    )
    published_check = {
        t: (-np.asarray(v[::-1]) if t else np.zeros(3))
        for t, v in PUBLISHED_SUBSET.items()
        if t < frames and not args.self_test
    }
    info["published_subset_minus_recovered_px"] = {
        str(t): (published_check[t] - expected[t]).tolist() for t in published_check
    }
    if args.ground_truth_csv:
        published = load_ground_truth_csv(args.ground_truth_csv, frames)
        expected = -published[:, ::-1]
        expected[0] = 0
        info["ground_truth_source"] = f"published table {args.ground_truth_csv}"

    # 4. Fiji crop semantics from Fiji's own translations.
    fy0, fy1, fx0, fx1 = fiji_crop_bounds(fiji_translation, raw.shape[2], raw.shape[3])
    info["fiji_crop_formula_from_fiji_translations"] = {
        "y0": fy0,
        "x0": fx0,
        "height": fy1 - fy0,
        "width": fx1 - fx0,
        "matches_archive": (fy0, fx0, fy1 - fy0, fx1 - fx0) == (y0, x0, height, width),
    }
    info["forward_fit_quality"] = fit_quality

    # 5. Per-frame tables.
    names = ("dz", "dy", "dx")
    rows = []
    for t in range(frames):
        row = {"frame": t}
        for axis, name in enumerate(names):
            row[f"expected_{name}"] = float(expected[t, axis])
            row[f"estimated_{name}"] = float(shifts[t, axis])
            row[f"error_{name}"] = float(shifts[t, axis] - expected[t, axis])
        for axis, name in enumerate(names):
            row[f"fiji_{name}"] = float(fiji_translation[t, axis])
            row[f"fiji_minus_estimated_{name}"] = float(
                fiji_translation[t, axis] - shifts[t, axis]
            )
            row[f"fiji_error_{name}"] = float(
                fiji_translation[t, axis] - expected[t, axis]
            )
        for axis, name in enumerate(names):
            row[f"crop_before_z_{name}"] = float(cropped_run["shifts"][t, axis])
        rows.append(row)
    write_csv(output / "shifts_per_frame.csv", rows)

    summary: dict = {
        "per_axis_vs_truth": {},
        "per_axis_vs_fiji": {},
        "fiji_vs_truth": {},
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
        summary.setdefault("crop_before_z_vs_fiji", {})[name] = axis_statistics(
            cropped_run["shifts"][:, axis] - fiji_translation[:, axis]
        )

    # 6. Image comparisons in Fiji's region.
    ours = principal["corrected"][:, :, y0 : y0 + height, x0 : x0 + width]
    raw_region = raw[:, :, y0 : y0 + height, x0 : x0 + width].astype(np.float32)
    fiji_f = fiji.astype(np.float32)
    ours_u16 = np.clip(np.floor(ours + 0.5), 0, 65535)
    metric_rows = []
    for t in range(frames):
        row = {"frame": t}
        row.update(image_metrics(ours[t], fiji_f[t], "volume"))
        row.update(image_metrics(ours[t].max(axis=0), fiji_f[t].max(axis=0), "maxz"))
        row.update(image_metrics(ours[t].max(axis=1), fiji_f[t].max(axis=1), "maxy_xz"))
        for z in REPRESENTATIVE_Z:
            if z < ours.shape[1]:
                row[f"slice{z}_pearson"] = pearson(ours[t, z], fiji_f[t, z])
        row["identical_voxel_fraction_uint16"] = float(
            np.mean(ours_u16[t] == fiji_f[t])
        )
        row["max_abs_difference"] = float(np.abs(ours[t] - fiji_f[t]).max())
        # Improvement relative to the unregistered movie, independent of Fiji.
        row["raw_vs_frame0_pearson"] = pearson(raw_region[t], raw_region[0])
        row["ours_vs_frame0_pearson"] = pearson(ours[t], ours[0])
        row["fiji_vs_frame0_pearson"] = pearson(fiji_f[t], fiji_f[0])
        row["registration_improves"] = bool(
            t == 0 or row["ours_vs_frame0_pearson"] > row["raw_vs_frame0_pearson"]
        )
        metric_rows.append(row)
    write_csv(output / "fiji_comparison_metrics.csv", metric_rows)

    metric_names = [
        k
        for k in metric_rows[0]
        if k != "frame" and not isinstance(metric_rows[0][k], bool)
    ]
    distributions = {}
    for name in metric_names:
        values = np.asarray([r[name] for r in metric_rows], dtype=np.float64)
        higher_is_better = any(s in name for s in ("pearson", "ssim", "identical"))
        worst = int(
            np.argmin(values[1:]) + 1 if higher_is_better else np.argmax(values[1:]) + 1
        )
        distributions[name] = {
            "min": float(values.min()),
            "median": float(np.median(values)),
            "mean": float(values.mean()),
            "max": float(values.max()),
            "worst_frame_excluding_0": worst,
        }
    summary["fiji_image_metrics"] = distributions
    summary["frames_where_registration_worsens"] = [
        r["frame"] for r in metric_rows if not r["registration_improves"]
    ]

    # 7. Error correlates (Z stress test).
    z_error = np.abs(shifts[:, 0] - expected[:, 0])
    overlap = [
        float(np.prod([1 - abs(expected[t, a]) / raw.shape[a + 1] for a in range(3)]))
        for t in range(frames)
    ]
    correlates = {
        "abs_dz": np.abs(expected[:, 0]),
        "abs_dy": np.abs(expected[:, 1]),
        "abs_dx": np.abs(expected[:, 2]),
        "frame": np.arange(frames),
        "overlap_fraction": np.asarray(overlap),
    }
    summary["abs_z_error_spearman"] = {
        name: float(spearmanr(values[1:], z_error[1:]).statistic)
        for name, values in correlates.items()
    }

    # 8. Gates.
    gate = GATES[args.gate]
    worst_truth = max(summary["per_axis_vs_truth"][n]["max_abs"] for n in names)
    worst_fiji = max(summary["per_axis_vs_fiji"][n]["max_abs"] for n in names)
    worst_pearson = distributions["volume_pearson"]["min"]
    checks = {
        "shift_vs_truth": worst_truth <= gate["truth_px"],
        "shift_vs_fiji": worst_fiji <= gate["fiji_px"],
        "volume_pearson_vs_fiji": worst_pearson > gate["pearson"],
        "registration_never_worsens": not summary["frames_where_registration_worsens"],
        "serial_equals_parallel": all(info["serial_parallel_identical"].values()),
    }
    summary["gate"] = {"preset": args.gate, **gate, "checks": checks}
    info["peak_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6

    (output / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (output / "run_info.json").write_text(
        json.dumps(info, indent=2, default=str), encoding="utf-8"
    )
    if not args.no_plots:
        from plots import make_plots

        make_plots(
            output,
            raw,
            fiji,
            principal["corrected"],
            shifts,
            expected,
            fiji_translation,
            metric_rows,
            (y0, x0),
        )
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    return all(checks.values())


def self_test_movie() -> Movie:
    fixture = REPOSITORY / "tests" / "data" / "fiji_macro" / "fiji_macro_reference.npz"
    with np.load(fixture) as data:
        raw = data["raw"]
        fiji = np.clip(np.floor(data["default__fiji_corrected"] + 0.5), 0, 65535)
    return Movie(
        raw=raw,
        fiji=fiji.astype(np.uint16),
        metadata={
            "SELF_TEST": f"{fixture.name}: synthetic movie, real Fiji macro output"
        },
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--data-dir", type=Path, default=REPOSITORY / ".validation-data"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY / "validation-results" / "large-drift-full-movie",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="download the archive from Zenodo if absent",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--gate", choices=sorted(GATES), default="baseline")
    parser.add_argument(
        "--ground-truth-csv", type=Path, help="published drift: frame,x,y,z"
    )
    parser.add_argument("--no-plots", action="store_true")
    parser.add_argument(
        "--omp-threads",
        default=os.environ["OMP_NUM_THREADS"],
        help="OpenMP threads for NanoPyx (default 1 for bit-reproducible estimates)",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="exercise the pipeline on the committed small real-Fiji fixture "
        "(tests/data/fiji_macro); results say nothing about the published movie",
    )
    args = parser.parse_args()
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
        movie, _ = load(args.data_dir, download=args.download)
    print(
        f"raw {movie.raw.shape} {movie.raw.dtype}; "
        f"fiji {movie.fiji.shape} {movie.fiji.dtype}"
    )
    return 0 if validate(movie, args, args.output_dir) else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())
