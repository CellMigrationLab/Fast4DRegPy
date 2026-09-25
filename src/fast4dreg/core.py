"""Small orchestration API for projection-based registration."""

from __future__ import annotations

import numpy as np

from .estimation import estimate_channel_shifts, estimate_time_drift
from .transform import apply_channel_shifts, apply_drift


def register_time(
    image: np.ndarray,
    *,
    axes: str = "TYX",
    reference_channel: int = 0,
    projection: str = "max",
    reference: str = "first",
    correct_xy: bool = True,
    correct_z: bool = False,
    axial_projection_axis: str = "Y",
    time_averaging: int = 1,
    max_expected_drift: int = 0,
    backend: str = "threaded",
    interpolation_order: int = 3,
    cval: float = 0.0,
    output_dtype: str = "float32",
    workers: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate and apply time drift, returning ``(corrected, shifts)``."""
    shifts = estimate_time_drift(
        image,
        axes=axes,
        reference_channel=reference_channel,
        projection=projection,
        reference=reference,
        correct_xy=correct_xy,
        correct_z=correct_z,
        axial_projection_axis=axial_projection_axis,
        time_averaging=time_averaging,
        max_expected_drift=max_expected_drift,
        backend=backend,
        workers=workers,
    )
    corrected = apply_drift(
        image,
        shifts,
        axes=axes,
        interpolation_order=interpolation_order,
        cval=cval,
        output_dtype=output_dtype,
        workers=workers,
    )
    return corrected, shifts


def register_channels(
    image: np.ndarray,
    *,
    axes: str = "CYX",
    reference_channel: int = 0,
    projection: str = "max",
    correct_xy: bool = True,
    correct_z: bool = False,
    axial_projection_axis: str = "Y",
    max_expected_drift: int = 0,
    backend: str = "threaded",
    interpolation_order: int = 3,
    cval: float = 0.0,
    output_dtype: str = "float32",
    workers: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate and apply channel shifts, returning ``(corrected, shifts)``."""
    shifts = estimate_channel_shifts(
        image,
        axes=axes,
        reference_channel=reference_channel,
        projection=projection,
        correct_xy=correct_xy,
        correct_z=correct_z,
        axial_projection_axis=axial_projection_axis,
        max_expected_drift=max_expected_drift,
        backend=backend,
        workers=workers,
    )
    corrected = apply_channel_shifts(
        image,
        shifts,
        axes=axes,
        interpolation_order=interpolation_order,
        cval=cval,
        output_dtype=output_dtype,
        workers=workers,
    )
    return corrected, shifts


__all__ = [
    "apply_channel_shifts",
    "apply_drift",
    "estimate_channel_shifts",
    "estimate_time_drift",
    "register_channels",
    "register_time",
]
