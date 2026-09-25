"""Strict TIFF and drift-table helpers."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import tifffile

from .axes import normalize_axes, validate_image


def prepare_output_path(path: str | Path, *, overwrite: bool) -> Path:
    """Validate a destination and require explicit permission to overwrite."""
    if not isinstance(overwrite, bool):
        raise TypeError("overwrite must be a boolean")
    destination = Path(path)
    if destination.exists() and not overwrite:
        raise FileExistsError(
            f"refusing to overwrite existing file: {destination}. "
            "Pass overwrite=True to replace it."
        )
    if not destination.parent.exists():
        raise FileNotFoundError(
            f"output directory does not exist: {destination.parent}"
        )
    if not destination.parent.is_dir():
        raise NotADirectoryError(
            f"output parent is not a directory: {destination.parent}"
        )
    return destination


def load_tiff(path: str | Path) -> np.ndarray:
    """Load a TIFF image as a NumPy array."""
    return tifffile.imread(Path(path))


def save_tiff(
    path: str | Path,
    image: np.ndarray,
    *,
    axes: str | None = None,
    overwrite: bool = False,
) -> None:
    """Save an image as TIFF, optionally recording an ImageJ axes string."""
    array = validate_image(image)
    if axes is None:
        metadata = None
    else:
        metadata = {"axes": normalize_axes(array, axes)}
    destination = prepare_output_path(path, overwrite=overwrite)
    tifffile.imwrite(destination, array, metadata=metadata)


def save_drift_csv(
    path: str | Path,
    shifts: np.ndarray,
    *,
    overwrite: bool = False,
) -> None:
    """Save ``(dz,dy,dx)`` shifts to CSV."""
    array = np.asarray(shifts, dtype=np.float32)
    if array.ndim != 2 or array.shape[1:] != (3,):
        raise ValueError(f"shifts must have shape (N,3), got {array.shape}")
    if array.shape[0] == 0:
        raise ValueError("shifts must contain at least one row")
    if not np.all(np.isfinite(array)):
        raise ValueError("shifts contain non-finite values")

    destination = prepare_output_path(path, overwrite=overwrite)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "dz", "dy", "dx"])
        for index, (dz, dy, dx) in enumerate(array):
            writer.writerow([index, float(dz), float(dy), float(dx)])


def load_drift_csv(path: str | Path) -> np.ndarray:
    """Load a CSV created by :func:`save_drift_csv`."""
    shifts: list[list[float]] = []
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        expected = ["index", "dz", "dy", "dx"]
        if reader.fieldnames != expected:
            raise ValueError(f"drift CSV must have columns in this order: {expected}")
        for expected_index, row in enumerate(reader):
            try:
                index = int(row["index"])
                values = [float(row["dz"]), float(row["dy"]), float(row["dx"])]
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"drift CSV row {expected_index + 2} contains invalid numbers"
                ) from exc
            if index != expected_index:
                raise ValueError(
                    "drift CSV index column must be sequential starting at 0; "
                    f"expected {expected_index}, found {index}"
                )
            shifts.append(values)
    array = np.asarray(shifts, dtype=np.float32)
    if array.shape == (0,):
        raise ValueError("drift CSV contains no shift rows")
    if not np.all(np.isfinite(array)):
        raise ValueError("drift CSV contains non-finite shifts")
    return array
