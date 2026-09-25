"""Low-level validation and volume translation helpers."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from scipy.ndimage import shift as ndi_shift

from ._imagej import translate_volume

_INTERPOLATIONS = {"imagej", "scipy"}


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
    interpolation: str,
    interpolation_order: int | None,
    cval: float,
) -> tuple[str, int, float]:
    """Validate interpolation settings."""
    if not isinstance(interpolation, str):
        raise TypeError("interpolation must be 'imagej' or 'scipy'")
    mode = interpolation.lower().strip()
    if mode not in _INTERPOLATIONS:
        raise ValueError(
            f"interpolation must be 'imagej' or 'scipy', not {interpolation!r}"
        )
    if isinstance(cval, (str, bytes)):
        raise TypeError("cval must be a real number")
    try:
        fill_value = float(cval)
    except (TypeError, ValueError) as exc:
        raise TypeError("cval must be a real number") from exc
    if not np.isfinite(fill_value):
        raise ValueError("cval must be finite")

    if mode == "imagej":
        if interpolation_order is not None:
            raise ValueError(
                "interpolation_order applies only to interpolation='scipy'; "
                "Fiji-compatible 'imagej' interpolation is always bicubic"
            )
        if fill_value != 0.0:
            raise ValueError(
                "interpolation='imagej' fills uncovered voxels with 0 as Fiji "
                "does; use interpolation='scipy' for another cval"
            )
        return mode, 3, fill_value

    order = _strict_int(
        3 if interpolation_order is None else interpolation_order,
        name="interpolation_order",
        minimum=0,
        maximum=5,
    )
    return mode, order, fill_value


def validate_workers(workers: object) -> int:
    """Validate the explicit number of concurrent volume transformations."""
    if isinstance(workers, bool) or not isinstance(workers, (int, np.integer)):
        raise TypeError("workers must be an integer")
    count = int(workers)
    if count < 1:
        raise ValueError("workers must be at least 1")
    return count


def output_dtype(volume: np.ndarray, output_dtype: str) -> np.dtype:
    if not isinstance(output_dtype, str):
        raise TypeError("output_dtype must be 'float32' or 'input'")
    normalized = output_dtype.lower().strip()
    if normalized == "float32":
        return np.dtype(np.float32)
    if normalized == "input":
        return np.asarray(volume).dtype
    raise ValueError("output_dtype must be 'float32' or 'input'")


def validated_translation(translation: np.ndarray) -> np.ndarray:
    try:
        array = np.asarray(translation, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise TypeError("translation must contain numeric values") from exc
    if array.shape != (3,) or not np.all(np.isfinite(array)):
        raise ValueError("translation must contain three finite (dz,dy,dx) values")
    return array


def _cast_like(values: np.ndarray, dtype: np.dtype) -> np.ndarray:
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return np.clip(np.floor(values + 0.5), info.min, info.max).astype(dtype)
    return values.astype(dtype, copy=False)


def axial_axis(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("axial_projection_axis must be a string")
    axis = value.upper().strip()
    if axis not in {"X", "Y"}:
        raise ValueError("axial_projection_axis must be 'X' or 'Y'")
    return axis


def shift_volume_into(
    source: np.ndarray,
    destination: np.ndarray,
    translation: np.ndarray,
    *,
    interpolation: str,
    interpolation_order: int,
    cval: float,
    axial_projection_axis: str,
    crop_yx: tuple[int, int, int, int] | None = None,
    z_padding: int = 0,
) -> None:
    """Apply one validated translation directly into an output view."""
    y0, y1, x0, x1 = crop_yx or (0, source.shape[1], 0, source.shape[2])
    if z_padding:
        half = z_padding // 2
        source = np.pad(source, ((half, half), (0, 0), (0, 0)))

    if np.all(translation == 0):
        destination[...] = source[:, y0:y1, x0:x1]
        return

    if interpolation == "imagej":
        destination[...] = _cast_like(
            translate_volume(
                source,
                translation,
                axial_projection_axis=axial_projection_axis,
                crop_yx=(y0, y1, x0, x1),
            ),
            destination.dtype,
        )
        return

    if crop_yx is None:
        ndi_shift(
            source,
            shift=tuple(float(value) for value in translation),
            order=interpolation_order,
            mode="constant",
            cval=cval,
            prefilter=interpolation_order > 1,
            output=destination,
        )
        return

    shifted = ndi_shift(
        np.asarray(source, dtype=np.float64),
        shift=tuple(float(value) for value in translation),
        order=interpolation_order,
        mode="constant",
        cval=cval,
        prefilter=interpolation_order > 1,
    )
    destination[...] = _cast_like(shifted[:, y0:y1, x0:x1], destination.dtype)


def apply_translation_jobs(
    source: np.ndarray,
    destination: np.ndarray,
    jobs: Sequence[tuple[int, int, np.ndarray]],
    *,
    interpolation: str,
    interpolation_order: int,
    cval: float,
    axial_projection_axis: str,
    workers: int,
    crop_yx: tuple[int, int, int, int] | None = None,
    z_padding: int = 0,
) -> None:
    """Apply independent translations serially or with a fixed thread pool."""

    def apply_one(job: tuple[int, int, np.ndarray]) -> None:
        channel, timepoint, translation = job
        shift_volume_into(
            source[channel, timepoint],
            destination[channel, timepoint],
            translation,
            interpolation=interpolation,
            interpolation_order=interpolation_order,
            cval=cval,
            axial_projection_axis=axial_projection_axis,
            crop_yx=crop_yx,
            z_padding=z_padding,
        )

    if workers == 1 or len(jobs) == 1:
        for job in jobs:
            apply_one(job)
        return

    with ThreadPoolExecutor(max_workers=min(workers, len(jobs))) as executor:
        list(executor.map(apply_one, jobs))
