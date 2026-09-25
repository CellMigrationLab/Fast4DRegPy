"""Application of explicit registration translations."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from scipy.ndimage import shift as ndi_shift

from ._imagej import translate_volume
from .axes import from_ctzyx, to_ctzyx

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
    """Validate interpolation settings before any zero-shift shortcut.

    ``interpolation="imagej"`` reproduces Fiji Fast4DReg: ImageJ bicubic
    (Catmull-Rom) translation of every Z plane, then of every axial plane, with
    zero fill. ``interpolation="scipy"`` uses one ``scipy.ndimage.shift`` spline
    of ``interpolation_order`` (default 3) with constant ``cval`` fill.
    """
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


def fiji_crop_bounds(
    shifts: Sequence[Sequence[float]], height: int, width: int
) -> tuple[int, int, int, int]:
    """Return Fiji Fast4DReg's "Crop output" rectangle ``(y0, y1, x0, x1)``.

    This is ``getMinMaxXYFromDriftTable_xy`` plus the ``makeRectangle`` call in
    ``time_estimate+apply.ijm``: the extrema of the XY translations (both
    starting from 0) are rounded up with ``ceil`` and the rectangle starts at
    ``(ceil(max dx), ceil(max dy))``.
    """
    array = np.asarray(shifts, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"shifts must have shape (N,3), got {array.shape}")
    min_dy, max_dy = min(0.0, array[:, 1].min()), max(0.0, array[:, 1].max())
    min_dx, max_dx = min(0.0, array[:, 2].min()), max(0.0, array[:, 2].max())
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
    """Return Fiji Fast4DReg's total "Extend stack to fit" Z padding.

    ``2 * max(-floor(min dz), ceil(max dz))`` slices, split equally above and
    below the stack (``Canvas Size... position=Center``).
    """
    array = np.asarray(shifts, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 3:
        raise ValueError(f"shifts must have shape (N,3), got {array.shape}")
    minimum = int(np.floor(min(0.0, array[:, 0].min())))
    maximum = int(np.ceil(max(0.0, array[:, 0].max())))
    return 2 * max(-minimum, maximum)


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


def _cast_like(values: np.ndarray, dtype: np.dtype) -> np.ndarray:
    """Convert float results, rounding and clipping for integer outputs."""
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return np.clip(np.floor(values + 0.5), info.min, info.max).astype(dtype)
    return values.astype(dtype, copy=False)


def _shift_volume_into(
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
    """Apply one already-validated translation directly into an output view.

    ``crop_yx`` and ``z_padding`` reproduce Fiji's "Crop output" (applied to
    the XY-corrected stack, before the Z pass) and "Extend stack to fit".
    """
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


def _axial_axis(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("axial_projection_axis must be a string")
    axis = value.upper().strip()
    if axis not in {"X", "Y"}:
        raise ValueError("axial_projection_axis must be 'X' or 'Y'")
    return axis


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
    """Translate one ``ZYX`` volume without hiding small non-zero shifts."""
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


def _apply_translation_jobs(
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
    """Apply independent CT volume translations serially or in a thread pool."""

    def apply_one(job: tuple[int, int, np.ndarray]) -> None:
        channel, timepoint, translation = job
        _shift_volume_into(
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
        for _ in executor.map(apply_one, jobs):
            pass


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
    """Apply one shift per timepoint using an explicit worker count.

    ``crop_output=True`` crops Y/X to the region covered in every frame using
    Fiji's rectangle (:func:`fiji_crop_bounds`). ``extend_z=True`` pads Z by
    :func:`fiji_z_padding` slices so that Z-shifted content is kept. Both are
    off by default, so the output keeps the input shape unless requested.
    """
    canonical, original_axes = to_ctzyx(image, axes)
    if "T" not in original_axes:
        raise ValueError("applying time drift requires a T axis")
    shifts_array = validate_shifts(shifts, canonical.shape[1])
    mode, order, fill_value = validate_transform_options(
        interpolation, interpolation_order, cval
    )
    axial_axis = _axial_axis(axial_projection_axis)
    dtype = _output_dtype(canonical, output_dtype)
    worker_count = validate_workers(workers)

    if not isinstance(crop_output, (bool, np.bool_)):
        raise TypeError("crop_output must be a boolean")
    if not isinstance(extend_z, (bool, np.bool_)):
        raise TypeError("extend_z must be a boolean")
    crop_yx = (
        fiji_crop_bounds(shifts_array, canonical.shape[3], canonical.shape[4])
        if crop_output
        else None
    )
    z_padding = fiji_z_padding(shifts_array) if extend_z else 0
    y0, y1, x0, x1 = crop_yx or (0, canonical.shape[3], 0, canonical.shape[4])
    shape = (
        canonical.shape[0],
        canonical.shape[1],
        canonical.shape[2] + z_padding,
        y1 - y0,
        x1 - x0,
    )
    if z_padding and "Z" not in original_axes:
        raise ValueError("extend_z requires a Z axis")

    corrected = np.empty(shape, dtype=dtype)
    jobs = [
        (channel, timepoint, shifts_array[timepoint])
        for channel in range(canonical.shape[0])
        for timepoint in range(canonical.shape[1])
    ]
    _apply_translation_jobs(
        canonical,
        corrected,
        jobs,
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
    """Apply one shift per channel using an explicit worker count."""
    canonical, original_axes = to_ctzyx(image, axes)
    if "C" not in original_axes:
        raise ValueError("applying channel shifts requires a C axis")
    shifts_array = validate_shifts(shifts, canonical.shape[0])
    mode, order, fill_value = validate_transform_options(
        interpolation, interpolation_order, cval
    )
    axial_axis = _axial_axis(axial_projection_axis)
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
        interpolation=mode,
        interpolation_order=order,
        cval=fill_value,
        axial_projection_axis=axial_axis,
        workers=worker_count,
    )
    return from_ctzyx(corrected, original_axes)
