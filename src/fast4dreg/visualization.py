"""Image-based registration validation helpers used in the Fast4DReg paper."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from skimage.measure import profile_line

from .axes import to_ctzyx
from .validation import _validation_movie


def _reference_channel(value: object, *, channels: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError("reference_channel must be an integer")
    index = int(value)
    if not 0 <= index < channels:
        raise ValueError(
            f"reference_channel={index} is outside the available range "
            f"0..{channels - 1}"
        )
    return index


def temporal_standard_deviation(
    image: np.ndarray,
    *,
    axes: str = "TYX",
    reference_channel: int = 0,
    z_index: int | None = None,
) -> np.ndarray:
    """Return temporal sample standard deviation, matching ImageJ's projection."""
    canonical, original_axes = to_ctzyx(image, axes)
    if "T" not in original_axes or canonical.shape[1] < 2:
        raise ValueError("temporal standard deviation requires at least two timepoints")
    channel = _reference_channel(reference_channel, channels=canonical.shape[0])
    result = np.std(canonical[channel].astype(np.float64), axis=0, ddof=1).astype(
        np.float32
    )
    if z_index is not None:
        if isinstance(z_index, bool) or not isinstance(z_index, (int, np.integer)):
            raise TypeError("z_index must be an integer or None")
        if not 0 <= int(z_index) < result.shape[0]:
            raise ValueError(
                f"z_index={z_index} is outside the available range "
                f"0..{result.shape[0] - 1}"
            )
        return result[int(z_index)]
    if "Z" not in original_axes:
        return result[0]
    return result


def temporal_color_overlay(
    image: np.ndarray,
    *,
    axes: str = "TYX",
    frame_indices: tuple[int, int, int] = (0, 1, 2),
    reference_channel: int = 0,
    analysis: str = "slice",
    z_index: int | None = None,
) -> np.ndarray:
    """Create the blue/green/red three-frame overlays used in the paper."""
    movie = _validation_movie(
        image,
        axes=axes,
        reference_channel=reference_channel,
        analysis=analysis,
        z_index=z_index,
    )
    if not isinstance(frame_indices, tuple) or any(
        isinstance(index, bool) or not isinstance(index, (int, np.integer))
        for index in frame_indices
    ):
        raise TypeError("frame_indices must be a tuple of three integers")
    if len(frame_indices) != 3 or len(set(frame_indices)) != 3:
        raise ValueError("frame_indices must contain three distinct indices")
    if any(index < 0 or index >= movie.shape[0] for index in frame_indices):
        raise ValueError(
            f"frame_indices must be inside the available range 0..{movie.shape[0] - 1}"
        )

    selected = movie[np.asarray(frame_indices)].astype(np.float32)
    low, high = np.percentile(selected, (0.1, 99.9))
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        raise ValueError("selected overlay frames must contain intensity variation")
    selected = np.clip((selected - low) / (high - low), 0, 1)
    rgb = np.empty((*selected.shape[1:], 3), dtype=np.float32)
    rgb[..., 0] = selected[2]
    rgb[..., 1] = selected[1]
    rgb[..., 2] = selected[0]
    return rgb


def _point(
    point: Sequence[float], *, name: str, shape: tuple[int, int]
) -> tuple[float, float]:
    if isinstance(point, (str, bytes)):
        raise TypeError(f"{name} must be a two-item coordinate sequence")
    try:
        size = len(point)
    except TypeError as exc:
        raise TypeError(f"{name} must be a two-item coordinate sequence") from exc
    if size != 2:
        raise ValueError(f"{name} must contain exactly two (row,column) coordinates")
    try:
        row, column = float(point[0]), float(point[1])
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} coordinates must be real numbers") from exc
    if not np.isfinite(row) or not np.isfinite(column):
        raise ValueError(f"{name} coordinates must be finite")
    if not (0 <= row <= shape[0] - 1 and 0 <= column <= shape[1] - 1):
        raise ValueError(f"{name}={point!r} is outside image shape {shape}")
    return row, column


def line_intensity_profile(
    image: np.ndarray,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    linewidth: int = 1,
) -> np.ndarray:
    """Sample a finite, in-bounds line profile for visual overlap checks."""
    array = np.asarray(image)
    if array.ndim != 2:
        raise ValueError("line intensity profiles require a 2D image")
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(
        array.dtype, np.complexfloating
    ):
        raise TypeError("image must contain real numeric values")
    if not np.all(np.isfinite(array)):
        raise ValueError("image contains non-finite values")
    if isinstance(linewidth, bool) or not isinstance(linewidth, (int, np.integer)):
        raise TypeError("linewidth must be an integer")
    if linewidth < 1:
        raise ValueError("linewidth must be at least 1")
    start_point = _point(start, name="start", shape=array.shape)
    end_point = _point(end, name="end", shape=array.shape)
    return np.asarray(
        profile_line(
            array,
            start_point,
            end_point,
            linewidth=int(linewidth),
            order=1,
            mode="constant",
            cval=0,
            reduce_func=np.mean,
        ),
        dtype=np.float32,
    )


def registration_kymograph(
    image: np.ndarray,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    axes: str = "TYX",
    reference_channel: int = 0,
    analysis: str = "slice",
    z_index: int | None = None,
    linewidth: int = 1,
) -> np.ndarray:
    """Build a time-by-distance kymograph along a fixed line."""
    movie = _validation_movie(
        image,
        axes=axes,
        reference_channel=reference_channel,
        analysis=analysis,
        z_index=z_index,
    )
    return np.stack(
        [
            line_intensity_profile(frame, start, end, linewidth=linewidth)
            for frame in movie
        ]
    )


def signal_to_background_ratio(
    image: np.ndarray,
    signal_mask: np.ndarray,
    background_mask: np.ndarray,
) -> float:
    """Return the paper's mean-signal/mean-background ratio."""
    array = np.asarray(image)
    signal = np.asarray(signal_mask)
    background = np.asarray(background_mask)
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(
        array.dtype, np.complexfloating
    ):
        raise TypeError("image must contain real numeric values")
    if not np.all(np.isfinite(array)):
        raise ValueError("image contains non-finite values")
    if signal.dtype != np.bool_ or background.dtype != np.bool_:
        raise TypeError("signal_mask and background_mask must be boolean arrays")
    if signal.shape != array.shape or background.shape != array.shape:
        raise ValueError("signal and background masks must match the image shape")
    if not np.any(signal) or not np.any(background):
        raise ValueError("signal and background masks must both contain pixels")
    if np.any(signal & background):
        raise ValueError("signal and background masks must not overlap")
    float_image = array.astype(np.float64, copy=False)
    background_mean = float(np.mean(float_image[background]))
    if not np.isfinite(background_mean) or background_mean <= 0:
        raise ValueError("mean background intensity must be positive and finite")
    return float(np.mean(float_image[signal]) / background_mean)
