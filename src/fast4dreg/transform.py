"""Application of explicit registration translations."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from scipy.ndimage import shift as ndi_shift

from .axes import from_ctzyx, to_ctzyx


def _strict_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer")
    integer = int(value)
    if not minimum <= integer <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return integer


def validate_shifts(shifts: Sequence[Sequence[float]], expected: int) -> np.ndarray:
    """Validate translations in public ``(dz, dy, dx)`` order."""
    try:
        array = np.asarray(shifts, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise TypeError("shifts must contain numeric values") from exc
    if array.shape != (expected, 3):
        raise ValueError(f"shifts must have shape {(expected, 3)}, got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError("shifts contain non-finite values")
    return array


def validate_transform_options(
    interpolation_order: int, cval: float
) -> tuple[int, float]:
    """Validate SciPy interpolation settings before any zero-shift shortcut."""
    order = _strict_int(
        interpolation_order,
        name="interpolation_order",
        minimum=0,
        maximum=5,
    )
    if isinstance(cval, (str, bytes)):
        raise TypeError("cval must be a real number")
    try:
        fill_value = float(cval)
    except (TypeError, ValueError) as exc:
        raise TypeError("cval must be a real number") from exc
    if not np.isfinite(fill_value):
        raise ValueError("cval must be finite")
    return order, fill_value


def validate_workers(workers: object) -> int:
    """Validate the explicit number of concurrent volume transformations."""
    if isinstance(workers, bool) or not isinstance(workers, (int, np.integer)):
        raise TypeError("workers must be an integer")
    count = int(workers)
    if count < 1:
        raise ValueError("workers must be at least 1")
    return count


def _output_dtype(volume: np.ndarray, output_dtype: str) -> np.dtype:
    if not isinstance(output_dtype, str):
        raise TypeError("output_dtype must be 'float32' or 'input'")
    normalized = output_dtype.lower().strip()
    if normalized == "float32":
        return np.dtype(np.float32)
    if normalized == "input":
        return np.asarray(volume).dtype
    raise ValueError("output_dtype must be 'float32' or 'input'")


def _validated_translation(translation: np.ndarray) -> np.ndarray:
    try:
        array = np.asarray(translation, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise TypeError("translation must contain numeric values") from exc
    if array.shape != (3,) or not np.all(np.isfinite(array)):
        raise ValueError("translation must contain three finite (dz,dy,dx) values")
    return array


def _shift_volume_into(
    source: np.ndarray,
    destination: np.ndarray,
    translation: np.ndarray,
    *,
    interpolation_order: int,
    cval: float,
) -> None:
    """Apply one already-validated translation directly into an output view."""
    if np.all(translation == 0):
        destination[...] = source
        return
    ndi_shift(
        source,
        shift=tuple(float(value) for value in translation),
        order=interpolation_order,
        mode="constant",
        cval=cval,
        prefilter=interpolation_order > 1,
        output=destination,
    )


def shift_volume(
    volume: np.ndarray,
    translation: np.ndarray,
    *,
    interpolation_order: int,
    cval: float,
    output_dtype: str = "input",
) -> np.ndarray:
    """Translate one ``ZYX`` volume without hiding small non-zero shifts."""
    order, fill_value = validate_transform_options(interpolation_order, cval)
    source = np.asarray(volume)
    if source.ndim != 3:
        raise ValueError(f"volume must have shape (Z,Y,X), got {source.shape}")
    destination = np.empty(source.shape, dtype=_output_dtype(source, output_dtype))
    _shift_volume_into(
        source,
        destination,
        _validated_translation(translation),
        interpolation_order=order,
        cval=fill_value,
    )
    return destination


def _apply_translation_jobs(
    source: np.ndarray,
    destination: np.ndarray,
    jobs: Sequence[tuple[int, int, np.ndarray]],
    *,
    interpolation_order: int,
    cval: float,
    workers: int,
) -> None:
    """Apply independent CT volume translations serially or in a thread pool."""

    def apply_one(job: tuple[int, int, np.ndarray]) -> None:
        channel, timepoint, translation = job
        _shift_volume_into(
            source[channel, timepoint],
            destination[channel, timepoint],
            translation,
            interpolation_order=interpolation_order,
            cval=cval,
        )

    if workers == 1 or len(jobs) == 1:
        for job in jobs:
            apply_one(job)
        return

    with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as executor:
        for _ in executor.map(apply_one, jobs):
            pass


def apply_drift(
    image: np.ndarray,
    shifts: Sequence[Sequence[float]],
    *,
    axes: str = "TZYX",
    interpolation_order: int = 1,
    cval: float = 0.0,
    output_dtype: str = "float32",
    workers: int = 1,
) -> np.ndarray:
    """Apply one shift per timepoint using an explicit worker count."""
    canonical, original_axes = to_ctzyx(image, axes)
    if "T" not in original_axes:
        raise ValueError("applying time drift requires a T axis")
    shifts_array = validate_shifts(shifts, canonical.shape[1])
    order, fill_value = validate_transform_options(interpolation_order, cval)
    dtype = _output_dtype(canonical, output_dtype)
    worker_count = validate_workers(workers)

    corrected = np.empty(canonical.shape, dtype=dtype)
    jobs = [
        (channel, timepoint, shifts_array[timepoint])
        for channel in range(canonical.shape[0])
        for timepoint in range(canonical.shape[1])
    ]
    _apply_translation_jobs(
        canonical,
        corrected,
        jobs,
        interpolation_order=order,
        cval=fill_value,
        workers=worker_count,
    )
    return from_ctzyx(corrected, original_axes)


def apply_channel_shifts(
    image: np.ndarray,
    shifts: Sequence[Sequence[float]],
    *,
    axes: str = "CZYX",
    interpolation_order: int = 1,
    cval: float = 0.0,
    output_dtype: str = "float32",
    workers: int = 1,
) -> np.ndarray:
    """Apply one shift per channel using an explicit worker count."""
    canonical, original_axes = to_ctzyx(image, axes)
    if "C" not in original_axes:
        raise ValueError("applying channel shifts requires a C axis")
    shifts_array = validate_shifts(shifts, canonical.shape[0])
    order, fill_value = validate_transform_options(interpolation_order, cval)
    dtype = _output_dtype(canonical, output_dtype)
    worker_count = validate_workers(workers)

    corrected = np.empty(canonical.shape, dtype=dtype)
    jobs = [
        (channel, timepoint, shifts_array[channel])
        for channel in range(canonical.shape[0])
        for timepoint in range(canonical.shape[1])
    ]
    _apply_translation_jobs(
        canonical,
        corrected,
        jobs,
        interpolation_order=order,
        cval=fill_value,
        workers=worker_count,
    )
    return from_ctzyx(corrected, original_axes)
