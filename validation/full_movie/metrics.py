"""Metrics and CSV helpers for full-movie validation."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from skimage.metrics import structural_similarity


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(np.ravel(a), np.ravel(b))[0, 1])


def image_metrics(ours: np.ndarray, reference: np.ndarray, prefix: str) -> dict:
    a = np.asarray(ours, dtype=np.float64)
    b = np.asarray(reference, dtype=np.float64)
    span = float(b.max() - b.min())
    if span <= 0:
        raise ValueError("reference image must contain intensity variation")
    rmse = float(np.sqrt(np.mean((a - b) ** 2)))
    return {
        f"{prefix}_pearson": pearson(a, b),
        f"{prefix}_rmse": rmse,
        f"{prefix}_nrmse_range": rmse / span,
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


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("cannot write an empty CSV")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
