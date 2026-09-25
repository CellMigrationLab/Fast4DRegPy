"""Build machine-readable reports for full-movie validation."""

from __future__ import annotations

import json
import resource
from pathlib import Path

import numpy as np
from metrics import image_metrics, pearson, write_csv
from scipy.stats import spearmanr

REPRESENTATIVE_Z = (17, 34, 51)
GATES = {
    "baseline": {"truth_px": 0.75, "fiji_px": 0.75, "pearson": 0.98},
    "strict": {"truth_px": 0.15, "fiji_px": 0.01, "pearson": 0.99999},
}


def write_shift_table(
    path: Path,
    shifts: np.ndarray,
    expected: np.ndarray,
    fiji_translation: np.ndarray,
    cropped_shifts: np.ndarray,
) -> None:
    names = ("dz", "dy", "dx")
    rows = []
    for frame in range(shifts.shape[0]):
        row = {"frame": frame}
        for axis, name in enumerate(names):
            row[f"expected_{name}"] = float(expected[frame, axis])
            row[f"estimated_{name}"] = float(shifts[frame, axis])
            row[f"error_{name}"] = float(shifts[frame, axis] - expected[frame, axis])
            row[f"fiji_{name}"] = float(fiji_translation[frame, axis])
            row[f"fiji_minus_estimated_{name}"] = float(
                fiji_translation[frame, axis] - shifts[frame, axis]
            )
            row[f"fiji_error_{name}"] = float(
                fiji_translation[frame, axis] - expected[frame, axis]
            )
            row[f"crop_before_z_{name}"] = float(cropped_shifts[frame, axis])
        rows.append(row)
    write_csv(path, rows)


def compare_images(
    raw: np.ndarray,
    corrected: np.ndarray,
    fiji: np.ndarray,
    *,
    crop: tuple[int, int, int, int],
) -> tuple[list[dict], dict]:
    y0, x0, height, width = crop
    ours = corrected[:, :, y0 : y0 + height, x0 : x0 + width]
    raw_region = raw[:, :, y0 : y0 + height, x0 : x0 + width].astype(np.float32)
    fiji_float = fiji.astype(np.float32)
    ours_u16 = np.clip(np.floor(ours + 0.5), 0, 65535)

    rows = []
    for frame in range(raw.shape[0]):
        row = {"frame": frame}
        row.update(image_metrics(ours[frame], fiji_float[frame], "volume"))
        row.update(
            image_metrics(
                ours[frame].max(axis=0),
                fiji_float[frame].max(axis=0),
                "maxz",
            )
        )
        row.update(
            image_metrics(
                ours[frame].max(axis=1),
                fiji_float[frame].max(axis=1),
                "maxy_xz",
            )
        )
        for z_index in REPRESENTATIVE_Z:
            if z_index < ours.shape[1]:
                row[f"slice{z_index}_pearson"] = pearson(
                    ours[frame, z_index],
                    fiji_float[frame, z_index],
                )
        row["identical_voxel_fraction_uint16"] = float(
            np.mean(ours_u16[frame] == fiji_float[frame])
        )
        row["max_abs_difference"] = float(
            np.abs(ours[frame] - fiji_float[frame]).max()
        )
        row["raw_vs_frame0_pearson"] = pearson(raw_region[frame], raw_region[0])
        row["ours_vs_frame0_pearson"] = pearson(ours[frame], ours[0])
        row["fiji_vs_frame0_pearson"] = pearson(
            fiji_float[frame],
            fiji_float[0],
        )
        row["registration_improves"] = bool(
            frame == 0
            or row["ours_vs_frame0_pearson"] > row["raw_vs_frame0_pearson"]
        )
        rows.append(row)

    distributions = _metric_distributions(rows)
    return rows, distributions


def _metric_distributions(rows: list[dict]) -> dict:
    metric_names = [
        key
        for key in rows[0]
        if key != "frame" and not isinstance(rows[0][key], bool)
    ]
    distributions = {}
    for name in metric_names:
        values = np.asarray([row[name] for row in rows], dtype=np.float64)
        higher_is_better = any(
            token in name for token in ("pearson", "ssim", "identical")
        )
        tail = values[1:]
        worst = int(
            np.argmin(tail) + 1 if higher_is_better else np.argmax(tail) + 1
        )
        distributions[name] = {
            "min": float(values.min()),
            "median": float(np.median(values)),
            "mean": float(values.mean()),
            "max": float(values.max()),
            "worst_frame_excluding_0": worst,
        }
    return distributions


def z_error_correlates(
    shifts: np.ndarray,
    expected: np.ndarray,
    raw_shape: tuple[int, ...],
) -> dict:
    z_error = np.abs(shifts[:, 0] - expected[:, 0])
    overlap = np.asarray(
        [
            float(
                np.prod(
                    [
                        1 - abs(expected[frame, axis]) / raw_shape[axis + 1]
                        for axis in range(3)
                    ]
                )
            )
            for frame in range(shifts.shape[0])
        ]
    )
    correlates = {
        "abs_dz": np.abs(expected[:, 0]),
        "abs_dy": np.abs(expected[:, 1]),
        "abs_dx": np.abs(expected[:, 2]),
        "frame": np.arange(shifts.shape[0]),
        "overlap_fraction": overlap,
    }
    return {
        name: float(spearmanr(values[1:], z_error[1:]).statistic)
        for name, values in correlates.items()
    }


def gate_results(
    summary: dict,
    metric_rows: list[dict],
    *,
    preset: str,
    serial_parallel_identical: dict,
) -> dict:
    gate = GATES[preset]
    names = ("dz", "dy", "dx")
    worst_truth = max(summary["per_axis_vs_truth"][name]["max_abs"] for name in names)
    worst_fiji = max(summary["per_axis_vs_fiji"][name]["max_abs"] for name in names)
    worst_pearson = summary["fiji_image_metrics"]["volume_pearson"]["min"]
    worsened = [
        row["frame"] for row in metric_rows if not row["registration_improves"]
    ]
    checks = {
        "shift_vs_truth": worst_truth <= gate["truth_px"],
        "shift_vs_fiji": worst_fiji <= gate["fiji_px"],
        "volume_pearson_vs_fiji": worst_pearson > gate["pearson"],
        "registration_never_worsens": not worsened,
        "serial_equals_parallel": all(serial_parallel_identical.values()),
    }
    summary["frames_where_registration_worsens"] = worsened
    return {"preset": preset, **gate, "checks": checks}


def write_results(
    output: Path,
    *,
    info: dict,
    summary: dict,
    shift_table: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    metric_rows: list[dict],
) -> None:
    shifts, expected, fiji_translation, cropped_shifts = shift_table
    write_shift_table(
        output / "shifts_per_frame.csv",
        shifts,
        expected,
        fiji_translation,
        cropped_shifts,
    )
    write_csv(output / "fiji_comparison_metrics.csv", metric_rows)
    info["peak_rss_gb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    (output / "run_info.json").write_text(
        json.dumps(info, indent=2, default=str),
        encoding="utf-8",
    )
