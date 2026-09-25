"""Projection-based translation estimation using an explicit NanoPyx backend."""

from __future__ import annotations

import numpy as np

from ._imagej import resize_rows
from .axes import to_ctzyx
from .transform import apply_drift, validate_workers

_VALID_PROJECTIONS = {"max", "mean", "average"}
_VALID_REFERENCES = {"first", "previous"}
_VALID_BACKENDS = {"threaded", "unthreaded"}


def _choice(value: object, *, name: str, choices: set[str]) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.lower().strip()
    if normalized not in choices:
        raise ValueError(f"{name} must be one of {sorted(choices)}, not {value!r}")
    return normalized


def _nonnegative_int(value: object, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer")
    integer = int(value)
    if integer < 0:
        raise ValueError(f"{name} must be at least 0")
    return integer


def _positive_int(value: object, *, name: str) -> int:
    integer = _nonnegative_int(value, name=name)
    if integer < 1:
        raise ValueError(f"{name} must be at least 1")
    return integer


def _channel_index(value: object, *, channels: int) -> int:
    index = _nonnegative_int(value, name="reference_channel")
    if index >= channels:
        raise ValueError(
            f"reference_channel={index} is outside the available range "
            f"0..{channels - 1}"
        )
    return index


def _project(sequence: np.ndarray, axis: int, projection: str) -> np.ndarray:
    method = _choice(projection, name="projection", choices=_VALID_PROJECTIONS)
    if method == "max":
        return np.max(sequence, axis=axis)
    return np.mean(sequence, axis=axis)


def _crop_movie_to_even_square(movie: np.ndarray) -> np.ndarray:
    """Centre-crop frames to the closest even square, as Fiji/NanoPyx do."""
    height, width = movie.shape[-2:]
    size = min(height, width)
    if size % 2:
        size -= 1
    if size < 2:
        raise ValueError("projection frames are too small for even-square cropping")
    y0 = (height - size) // 2
    x0 = (width - size) // 2
    return movie[:, y0 : y0 + size, x0 : x0 + size]

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
        return np.ascontiguousarray(array), scale_factor

    scaled = np.stack([resize_rows(frame, scale_factor) for frame in array])
    return np.ascontiguousarray(scaled, dtype=np.float32), scale_factor


def _load_nanopyx_estimator():
    try:
        from nanopyx.core.analysis._le_drift_calculator import DriftEstimator
    except ImportError as exc:  # pragma: no cover - covered by package smoke test
        raise ImportError(
            "NanoPyx 2.1.4 is required for drift estimation. Install this "
            "project with `python -m pip install -e .`."
        ) from exc
    return DriftEstimator(verbose=False)


def _validate_nanopyx_movie(
    movie: np.ndarray,
    *,
    time_averaging: object,
    max_expected_drift: object,
) -> tuple[np.ndarray, int, int]:
    array = np.asarray(movie)
    if array.ndim != 3:
        raise ValueError(
            f"NanoPyx projection must have shape (N,Y,X), got {array.shape}"
        )
    if array.shape[0] < 2:
        raise ValueError("registration requires at least two images")
    if min(array.shape[1:]) < 2:
        raise ValueError("projection frames must be at least 2 x 2 pixels")
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(
        array.dtype, np.complexfloating
    ):
        raise TypeError("projection frames must contain real numeric values")
    if not np.all(np.isfinite(array)):
        raise ValueError("projection frames contain non-finite values")
    if np.any(np.ptp(array, axis=(1, 2)) == 0):
        raise ValueError("every projection frame must contain intensity variation")

    averaging = _positive_int(time_averaging, name="time_averaging")
    maximum = _nonnegative_int(max_expected_drift, name="max_expected_drift")
    frame_count = array.shape[0]
    blocks = -(-frame_count // averaging)
    if blocks < 2:
        raise ValueError(
            f"time_averaging={averaging} leaves fewer than two averaged blocks "
            f"for {frame_count} frames; Fiji would silently report zero drift"
        )

    cropped_size = min(array.shape[1:])
    if cropped_size % 2:
        cropped_size -= 1
    # NanoJ correlation maps are (size-1) wide and Fiji silently ignores a
    # search radius whose 2r+1 window does not fit inside them.
    if maximum > 0 and 2 * maximum + 1 >= cropped_size - 1:
        raise ValueError(
            "max_expected_drift is too large for the projection dimensions; "
            "Fiji Fast4DReg would otherwise ignore it silently"
        )
    return array, averaging, maximum


def _nanopyx_drift(
    movie: np.ndarray,
    *,
    reference: str,
    time_averaging: int,
    max_expected_drift: int,
    backend: str,
) -> np.ndarray:
    """Return NanoPyx translations as ``(dy,dx)`` without backend fallback."""
    array, averaging, maximum = _validate_nanopyx_movie(
        movie,
        time_averaging=time_averaging,
        max_expected_drift=max_expected_drift,
    )
    reference_mode = _choice(reference, name="reference", choices=_VALID_REFERENCES)
    backend_name = _choice(backend, name="backend", choices=_VALID_BACKENDS)
    prepared = np.ascontiguousarray(
        _crop_movie_to_even_square(array.astype(np.float32, copy=False))
    )

    if averaging > 1 or maximum > 0:
        # NanoPyx 2.1.4's DriftEstimator differs from NanoJ here (off-centre
        # 2r window, averaged-block reference, dropped partial block, cubic
        # knots); use NanoPyx's correlation primitives with NanoJ semantics.
        return _fiji_drift(
            prepared,
            reference=reference_mode,
            time_averaging=averaging,
            max_expected_drift=maximum,
        )

    estimator = _load_nanopyx_estimator()
    runner_name = f"_run_{backend_name}"
    runner = getattr(estimator, runner_name, None)
    if runner is None:
        raise RuntimeError(
            f"NanoPyx 2.1.4 does not provide the requested {backend_name!r} backend"
        )

    # Call the chosen implementation directly. LiquidEngine's public dispatch
    # catches backend exceptions and retries a different backend, which would
    # make failures and performance choices invisible to callers.
    result = runner(
        prepared,
        time_averaging=1,
        max_drift=0,
        ref_option=0 if reference_mode == "first" else 1,
    )
    table = np.asarray(result, dtype=np.float32)
    expected_shape = (array.shape[0], 3)
    if table.shape != expected_shape:
        raise RuntimeError(
            "NanoPyx returned an unexpected drift table with shape "
            f"{table.shape}; expected {expected_shape}"
        )
    if not np.all(np.isfinite(table)):
        raise RuntimeError("NanoPyx returned non-finite drift estimates")
    return table[:, [2, 1]]


def _load_nanopyx_ccm():
    try:
        from nanopyx.core.analysis.ccm import calculate_ccm, calculate_ccm_from_ref
        from nanopyx.core.analysis.estimate_shift import GetMaxOptimizer
    except ImportError as exc:  # pragma: no cover - covered by package smoke test
        raise ImportError(
            "NanoPyx 2.1.4 is required for drift estimation. Install this "
            "project with `python -m pip install -e .`."
        ) from exc
    return calculate_ccm, calculate_ccm_from_ref, GetMaxOptimizer


def _fiji_drift(
    movie: np.ndarray,
    *,
    reference: str,
    time_averaging: int,
    max_expected_drift: int,
) -> np.ndarray:
    """NanoJ ``DriftEstimation_.runAnalysis`` on an even-square movie.

    Returns ``(dy,dx)`` translations to apply for every frame. Frames are
    averaged in blocks of ``time_averaging`` (a trailing partial block is
    kept); in "first" mode every block is correlated with the raw first frame
    and in "previous" mode with the preceding block. A bounded search crops
    the correlation map to the centred ``2r+1`` window. Block drifts are
    expressed relative to block 0 and linearly interpolated to frames the way
    ImageJ resizes a one-row image (block ``b`` sits at frame
    ``b*(N-1)/(blocks-1)``).
    """
    calculate_ccm, calculate_ccm_from_ref, get_max_optimizer = _load_nanopyx_ccm()
    frames = movie.shape[0]
    blocks = -(-frames // time_averaging)
    averaged = np.stack(
        [
            np.mean(
                movie[b * time_averaging : min((b + 1) * time_averaging, frames)],
                axis=0,
                dtype=np.float64,
            )
            for b in range(blocks)
        ]
    ).astype(np.float32)

    if reference == "first":
        first_frame = np.ascontiguousarray(movie[0])
        ccm = np.asarray(calculate_ccm_from_ref(averaged, first_frame))
    else:
        ccm = np.asarray(calculate_ccm(averaged, 1))
    size = ccm.shape[-1]
    center = size // 2 - 1  # zero translation in NanoPyx and NanoJ maps
    radius = max_expected_drift if max_expected_drift > 0 else None
    if radius is not None:
        window = slice(center - radius, center + radius + 1)
        ccm = ccm[:, window, window]
        center = radius

    block_drift = np.zeros((blocks, 2), dtype=np.float64)
    for index, slice_ccm in enumerate(ccm):
        slice_ccm = np.ascontiguousarray(slice_ccm, dtype=np.float32)
        peak = np.unravel_index(int(np.argmax(slice_ccm)), slice_ccm.shape)
        if radius is not None and (
            min(peak) <= 1 or max(peak) >= slice_ccm.shape[0] - 2
        ):
            raise ValueError(
                f"the correlation peak of averaged block {index} lies at the "
                f"edge of the max_expected_drift={radius} search window "
                "(for Z this radius is in stretched axial pixels). Fiji "
                "Fast4DReg would report NaN or a clamped drift here; increase "
                "max_expected_drift or use 0 (automatic)"
            )
        row, col = get_max_optimizer(slice_ccm).get_max()
        block_drift[index] = (center - row, center - col)
    block_drift -= block_drift[0]
    if reference == "previous":
        block_drift = np.cumsum(block_drift, axis=0)

    if time_averaging == 1:
        drift = block_drift
    else:
        scale = (blocks - 1) / (frames - 1)
        position = np.arange(frames) * scale
        lower = position.astype(np.intp)
        upper = np.minimum(lower + 1, blocks - 1)
        fraction = (position - lower)[:, None]
        drift = (1.0 - fraction) * block_drift[lower] + fraction * block_drift[upper]
    if not np.all(np.isfinite(drift)):
        raise RuntimeError("NanoPyx returned non-finite drift estimates")
    return drift.astype(np.float32)


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
    worker_count = validate_workers(workers)

    shifts = np.zeros((volumes.shape[0], 3), dtype=np.float32)
    if correct_xy:
        shifts[:, 1:] = _nanopyx_drift(
            _project(volumes, axis=1, projection=projection),
            reference=reference,
            time_averaging=time_averaging,
            max_expected_drift=max_expected_drift,
            backend=backend,
        )

    if correct_z:
        if volumes.shape[1] < 2:
            raise ValueError("Z correction requires at least two Z slices")
        if not isinstance(axial_projection_axis, str):
            raise TypeError("axial_projection_axis must be a string")
        axial_axis = axial_projection_axis.upper().strip()
        if axial_axis not in {"X", "Y"}:
            raise ValueError("axial_projection_axis must be 'X' or 'Y'")

        z_volumes = np.asarray(volumes, dtype=np.float32)
        if correct_xy:
            # Fiji estimates Z from the XY-corrected stack, which it produces
            # with ImageJ bicubic translation; use the same interpolation here
            # regardless of the interpolation chosen for the final output.
            xy_shifts = shifts.copy()
            xy_shifts[:, 0] = 0.0
            z_volumes = apply_drift(
                z_volumes,
                xy_shifts,
                axes="TZYX",
                interpolation="imagej",
                crop_output=crop_output,
                output_dtype="float32",
                workers=worker_count,
            )
        projection_axis = 2 if axial_axis == "Y" else 3
        axial_movie = _project(
            z_volumes, axis=projection_axis, projection=projection
        )
        scaled_axial_movie, axial_scale_factor = _scale_axial_projection(
            axial_movie
        )
        axial_shifts = _nanopyx_drift(
            scaled_axial_movie,
            reference=reference,
            time_averaging=time_averaging,
            max_expected_drift=max_expected_drift,
            backend=backend,
        )
        shifts[:, 0] = axial_shifts[:, 0] / axial_scale_factor

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
    """Estimate per-timepoint translations in ``(dz,dy,dx)`` order.

    ``crop_output=True`` reproduces Fiji's "Crop output": the XY-corrected
    stack is cropped to the XY overlap before the axial projection is made,
    which changes the Z estimate (and Fiji's axial stretch factor).
    """
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
    reordered_shifts = _estimate_sequence_shifts(
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
    shifts = np.zeros_like(reordered_shifts)
    for reordered_index, original_channel in enumerate(order):
        shifts[original_channel] = reordered_shifts[reordered_index]
    return shifts
