"""Apply explicit ``(dz, dy, dx)`` translations to microscopy data."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from ._translation import (
    apply_translation_jobs as _apply_translation_jobs,
)
from ._translation import (
    axial_axis as _axial_axis,
)
from ._translation import (
    output_dtype as _output_dtype,
)
from ._translation import (
    shift_volume_into as _shift_volume_into,
)
from ._translation import (
    validate_shifts,
    validate_transform_options,
    validate_workers,
)
from ._translation import (
    validated_translation as _validated_translation,
)
from .axes import from_ctzyx, to_ctzyx


def fiji_crop_bounds(
    shifts: Sequence[Sequence[float]], height: int, width: int
) -> tuple[int, int, int, int]:
    """Return Fiji Fast4DReg's overlap crop as ``(y0, y1, x0, x1)``."""
    array = np.asarray(shifts, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"shifts must have shape (N,3), got {array.shape}")

    min_dy = min(0.0, array[:, 1].min())
    max_dy = max(0.0, array[:, 1].max())
    min_dx = min(0.0, array[:, 2].min())
    max_dx = max(0.0, array[:, 2].max())

    x0 = int(np.ceil(max_dx))
    y0 = int(np.ceil(max_dy))
    new_width = width - x0 + int(np.ceil(min_dx))
    new_height = height - y0 + int(np.ceil(min_dy))
    if new_width < 1 or new_height < 1:
        raise ValueError(
            "the XY drift is larger than the image; Fiji-compatible cropping "
            "would leave no pixels"
        )
    return y0, y0 + new_height, x0, x0 + new_width


def fiji_z_padding(shifts: Sequence[Sequence[float]]) -> int:
    """Return the total Z padding used by Fiji's "Extend stack to fit"."""
    array = np.asarray(shifts, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"shifts must have shape (N,3), got {array.shape}")
    minimum = int(np.floor(min(0.0, array[:, 0].min())))
    maximum = int(np.ceil(max(0.0, array[:, 0].max())))
    return 2 * max(-minimum, maximum)


def shift_volume(
    volume: np.ndarray,
    translation: np.ndarray,
    *,
    interpolation: str = "imagej",
    interpolation_order: int | None = None,
    cval: float = 0.0,
    axial_projection_axis: str = "Y",
    output_dtype: str = "input",
) -> np.ndarray:
    """Translate one ``ZYX`` volume."""
    mode, order, fill_value = validate_transform_options(
        interpolation, interpolation_order, cval
    )
    source = np.asarray(volume)
    if source.ndim != 3:
        raise ValueError(f"volume must have shape (Z,Y,X), got {source.shape}")

    destination = np.empty(source.shape, dtype=_output_dtype(source, output_dtype))
    _shift_volume_into(
        source,
        destination,
        _validated_translation(translation),
        interpolation=mode,
        interpolation_order=order,
        cval=fill_value,
        axial_projection_axis=_axial_axis(axial_projection_axis),
    )
    return destination


def _time_jobs(
    canonical: np.ndarray,
    shifts: np.ndarray,
) -> list[tuple[int, int, np.ndarray]]:
    return [
        (channel, timepoint, shifts[timepoint])
        for channel in range(canonical.shape[0])
        for timepoint in range(canonical.shape[1])
    ]


def _channel_jobs(
    canonical: np.ndarray,
    shifts: np.ndarray,
) -> list[tuple[int, int, np.ndarray]]:
    return [
        (channel, timepoint, shifts[channel])
        for channel in range(canonical.shape[0])
        for timepoint in range(canonical.shape[1])
    ]


def _time_output_geometry(
    canonical: np.ndarray,
    shifts: np.ndarray,
    *,
    crop_output: bool,
    extend_z: bool,
    has_z_axis: bool,
) -> tuple[tuple[int, ...], tuple[int, int, int, int] | None, int]:
    if not isinstance(crop_output, (bool, np.bool_)):
        raise TypeError("crop_output must be a boolean")
    if not isinstance(extend_z, (bool, np.bool_)):
        raise TypeError("extend_z must be a boolean")

    crop_yx = (
        fiji_crop_bounds(shifts, canonical.shape[3], canonical.shape[4])
        if crop_output
        else None
    )
    z_padding = fiji_z_padding(shifts) if extend_z else 0
    if z_padding and not has_z_axis:
        raise ValueError("extend_z requires a Z axis")

    y0, y1, x0, x1 = crop_yx or (0, canonical.shape[3], 0, canonical.shape[4])
    shape = (
        canonical.shape[0],
        canonical.shape[1],
        canonical.shape[2] + z_padding,
        y1 - y0,
        x1 - x0,
    )
    return shape, crop_yx, z_padding


def apply_drift(
    image: np.ndarray,
    shifts: Sequence[Sequence[float]],
    *,
    axes: str = "TZYX",
    interpolation: str = "imagej",
    interpolation_order: int | None = None,
    cval: float = 0.0,
    axial_projection_axis: str = "Y",
    crop_output: bool = False,
    extend_z: bool = False,
    output_dtype: str = "float32",
    workers: int = 1,
) -> np.ndarray:
    """Apply one translation per timepoint.

    ``crop_output`` and ``extend_z`` reproduce the corresponding Fiji
    Fast4DReg output-shape options. They are never enabled implicitly.
    """
    canonical, original_axes = to_ctzyx(image, axes)
    if "T" not in original_axes:
        raise ValueError("applying time drift requires a T axis")

    shifts_array = validate_shifts(shifts, canonical.shape[1])
    mode, order, fill_value = validate_transform_options(
        interpolation, interpolation_order, cval
    )
    axial_axis = _axial_axis(axial_projection_axis)
    worker_count = validate_workers(workers)
    shape, crop_yx, z_padding = _time_output_geometry(
        canonical,
        shifts_array,
        crop_output=crop_output,
        extend_z=extend_z,
        has_z_axis="Z" in original_axes,
    )

    corrected = np.empty(shape, dtype=_output_dtype(canonical, output_dtype))
    _apply_translation_jobs(
        canonical,
        corrected,
        _time_jobs(canonical, shifts_array),
        interpolation=mode,
        interpolation_order=order,
        cval=fill_value,
        axial_projection_axis=axial_axis,
        workers=worker_count,
        crop_yx=crop_yx,
        z_padding=z_padding,
    )
    return from_ctzyx(corrected, original_axes)


def apply_channel_shifts(
    image: np.ndarray,
    shifts: Sequence[Sequence[float]],
    *,
    axes: str = "CZYX",
    interpolation: str = "imagej",
    interpolation_order: int | None = None,
    cval: float = 0.0,
    axial_projection_axis: str = "Y",
    output_dtype: str = "float32",
    workers: int = 1,
) -> np.ndarray:
    """Apply one translation per channel to every timepoint."""
    canonical, original_axes = to_ctzyx(image, axes)
    if "C" not in original_axes:
        raise ValueError("applying channel shifts requires a C axis")

    shifts_array = validate_shifts(shifts, canonical.shape[0])
    mode, order, fill_value = validate_transform_options(
        interpolation, interpolation_order, cval
    )
    corrected = np.empty(
        canonical.shape,
        dtype=_output_dtype(canonical, output_dtype),
    )
    _apply_translation_jobs(
        canonical,
        corrected,
        _channel_jobs(canonical, shifts_array),
        interpolation=mode,
        interpolation_order=order,
        cval=fill_value,
        axial_projection_axis=_axial_axis(axial_projection_axis),
        workers=validate_workers(workers),
    )
    return from_ctzyx(corrected, original_axes)
