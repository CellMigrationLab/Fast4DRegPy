"""Projection-based translation estimation for Fast4DRegPy."""

from __future__ import annotations

import numpy as np

from ._drift import _nanopyx_drift
from ._imagej import resize_rows
from .axes import to_ctzyx
from .transform import apply_drift, validate_workers

_VALID_PROJECTIONS = {"max", "mean", "average"}


def _channel_index(value: object, *, channels: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError("reference_channel must be an integer")
    index = int(value)
    if not 0 <= index < channels:
        raise ValueError(
            f"reference_channel={index} is outside the available range "
            f"0..{channels - 1}"
        )
    return index


def _project(sequence: np.ndarray, axis: int, projection: str) -> np.ndarray:
    if not isinstance(projection, str):
        raise TypeError("projection must be a string")
    method = projection.lower().strip()
    if method not in _VALID_PROJECTIONS:
        raise ValueError(
            f"projection must be one of {sorted(_VALID_PROJECTIONS)}, "
            f"not {projection!r}"
        )
    if method == "max":
        return np.max(sequence, axis=axis)
    return np.mean(sequence, axis=axis)


def _axial_axis(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("axial_projection_axis must be a string")
    axis = value.upper().strip()
    if axis not in {"X", "Y"}:
        raise ValueError("axial_projection_axis must be 'X' or 'Y'")
    return axis


def _scale_axial_projection(movie: np.ndarray) -> tuple[np.ndarray, int]:
    """Stretch the axial dimension exactly as Fiji Fast4DReg's ``Scale...``.

    Fiji computes ``round(width / height)`` on the resliced axial projection,
    stretches the axial (height) dimension by that integer factor with ImageJ
    bicubic ``resize`` before correlation, and divides the measured axial
    translation by the same factor. ImageJ's resize maps a displacement of
    ``d`` rows to exactly ``factor * d`` rows, so the division is exact. Here
    ``movie`` is shaped ``(N, axial, lateral)``.
    """
    array = np.asarray(movie, dtype=np.float32)
    if array.ndim != 3:
        raise ValueError(
            f"axial projection must have shape (N,axial,lateral), got {array.shape}"
        )
    axial_size, lateral_size = array.shape[-2:]
    if axial_size < 2 or lateral_size < 2:
        raise ValueError("axial projection dimensions must both be at least 2 pixels")

    # ImageJ macro round() is Math.round (half up) for positive dimensions.
    # Clamp to one for volumes whose axial dimension is not the smaller axis.
    scale_factor = max(1, int(np.floor(lateral_size / axial_size + 0.5)))
    if scale_factor == 1:
        return np.ascontiguousarray(array), 1

    scaled = np.stack([resize_rows(frame, scale_factor) for frame in array])
    return np.ascontiguousarray(scaled, dtype=np.float32), scale_factor


def _validate_sequence_options(
    volumes: np.ndarray,
    *,
    correct_xy: object,
    correct_z: object,
    crop_output: object,
    workers: object,
) -> int:
    if volumes.ndim != 4:
        raise ValueError(f"volumes must have shape (N,Z,Y,X), got {volumes.shape}")
    if not isinstance(correct_xy, (bool, np.bool_)):
        raise TypeError("correct_xy must be a boolean")
    if not isinstance(correct_z, (bool, np.bool_)):
        raise TypeError("correct_z must be a boolean")
    if not correct_xy and not correct_z:
        raise ValueError("at least one of correct_xy or correct_z must be enabled")
    if not isinstance(crop_output, (bool, np.bool_)):
        raise TypeError("crop_output must be a boolean")
    if crop_output and not correct_xy:
        raise ValueError(
            "crop_output crops to the XY-drift overlap and requires correct_xy=True"
        )
    return validate_workers(workers)


def _estimate_xy(
    volumes: np.ndarray,
    *,
    projection: str,
    reference: str,
    time_averaging: int,
    max_expected_drift: int,
    backend: str,
) -> np.ndarray:
    movie = _project(volumes, axis=1, projection=projection)
    return _nanopyx_drift(
        movie,
        reference=reference,
        time_averaging=time_averaging,
        max_expected_drift=max_expected_drift,
        backend=backend,
    )


def _prepare_for_z(
    volumes: np.ndarray,
    shifts: np.ndarray,
    *,
    correct_xy: bool,
    crop_output: bool,
    workers: int,
) -> np.ndarray:
    if not correct_xy:
        return np.asarray(volumes, dtype=np.float32)

    xy_shifts = shifts.copy()
    xy_shifts[:, 0] = 0.0
    return apply_drift(
        np.asarray(volumes, dtype=np.float32),
        xy_shifts,
        axes="TZYX",
        interpolation="imagej",
        crop_output=crop_output,
        output_dtype="float32",
        workers=workers,
    )


def _estimate_z(
    volumes: np.ndarray,
    *,
    projection: str,
    reference: str,
    axial_projection_axis: str,
    time_averaging: int,
    max_expected_drift: int,
    backend: str,
) -> np.ndarray:
    if volumes.shape[1] < 2:
        raise ValueError("Z correction requires at least two Z slices")

    axis = _axial_axis(axial_projection_axis)
    projection_axis = 2 if axis == "Y" else 3
    axial_movie = _project(volumes, axis=projection_axis, projection=projection)
    scaled, scale_factor = _scale_axial_projection(axial_movie)
    axial_shifts = _nanopyx_drift(
        scaled,
        reference=reference,
        time_averaging=time_averaging,
        max_expected_drift=max_expected_drift,
        backend=backend,
    )
    return axial_shifts[:, 0] / scale_factor


def _estimate_sequence_shifts(
    volumes: np.ndarray,
    *,
    projection: str,
    reference: str,
    correct_xy: bool,
    correct_z: bool,
    axial_projection_axis: str,
    time_averaging: int,
    max_expected_drift: int,
    backend: str,
    workers: int,
    crop_output: bool = False,
) -> np.ndarray:
    """Estimate ``(dz,dy,dx)`` shifts for ``volumes`` shaped ``(N,Z,Y,X)``."""
    worker_count = _validate_sequence_options(
        volumes,
        correct_xy=correct_xy,
        correct_z=correct_z,
        crop_output=crop_output,
        workers=workers,
    )

    shifts = np.zeros((volumes.shape[0], 3), dtype=np.float32)
    if correct_xy:
        shifts[:, 1:] = _estimate_xy(
            volumes,
            projection=projection,
            reference=reference,
            time_averaging=time_averaging,
            max_expected_drift=max_expected_drift,
            backend=backend,
        )

    if correct_z:
        z_volumes = _prepare_for_z(
            volumes,
            shifts,
            correct_xy=correct_xy,
            crop_output=crop_output,
            workers=worker_count,
        )
        shifts[:, 0] = _estimate_z(
            z_volumes,
            projection=projection,
            reference=reference,
            axial_projection_axis=axial_projection_axis,
            time_averaging=time_averaging,
            max_expected_drift=max_expected_drift,
            backend=backend,
        )
    return shifts


def estimate_time_drift(
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
    workers: int = 1,
    crop_output: bool = False,
) -> np.ndarray:
    """Estimate per-timepoint translations in ``(dz,dy,dx)`` order."""
    canonical, original_axes = to_ctzyx(image, axes)
    if "T" not in original_axes:
        raise ValueError("time registration requires a T axis (for example TZYX)")
    if canonical.shape[1] < 2:
        raise ValueError("time registration requires at least two timepoints")
    channel = _channel_index(reference_channel, channels=canonical.shape[0])
    return _estimate_sequence_shifts(
        canonical[channel],
        projection=projection,
        reference=reference,
        correct_xy=correct_xy,
        correct_z=correct_z,
        axial_projection_axis=axial_projection_axis,
        time_averaging=time_averaging,
        max_expected_drift=max_expected_drift,
        backend=backend,
        workers=workers,
        crop_output=crop_output,
    )


def estimate_channel_shifts(
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
    workers: int = 1,
) -> np.ndarray:
    """Estimate per-channel translations relative to ``reference_channel``."""
    canonical, original_axes = to_ctzyx(image, axes)
    if "C" not in original_axes:
        raise ValueError("channel registration requires a C axis (for example CZYX)")
    if canonical.shape[0] < 2:
        raise ValueError("channel registration requires at least two channels")
    if canonical.shape[1] != 1:
        raise ValueError(
            "channel registration expects one timepoint; select a timepoint "
            "before estimating channel shifts"
        )
    channel = _channel_index(reference_channel, channels=canonical.shape[0])

    order = [channel] + [
        index for index in range(canonical.shape[0]) if index != channel
    ]
    reordered = _estimate_sequence_shifts(
        canonical[order, 0],
        projection=projection,
        reference="first",
        correct_xy=correct_xy,
        correct_z=correct_z,
        axial_projection_axis=axial_projection_axis,
        time_averaging=1,
        max_expected_drift=max_expected_drift,
        backend=backend,
        workers=workers,
    )
    shifts = np.zeros_like(reordered)
    for reordered_index, original_channel in enumerate(order):
        shifts[original_channel] = reordered[reordered_index]
    return shifts
