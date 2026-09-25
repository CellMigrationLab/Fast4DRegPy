"""Projection-based translation estimation using an explicit NanoPyx backend."""

from __future__ import annotations

import numpy as np

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


def _pad_movie_to_even_square(movie: np.ndarray) -> np.ndarray:
    """Pad frames so NanoPyx does not silently centre-crop rectangles."""
    height, width = movie.shape[-2:]
    size = max(height, width)
    if size % 2:
        size += 1
    pad_height = size - height
    pad_width = size - width
    padding = (
        (0, 0),
        (pad_height // 2, pad_height - pad_height // 2),
        (pad_width // 2, pad_width - pad_width // 2),
    )
    return np.pad(movie, padding, mode="constant")


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
    if averaging > frame_count // 2:
        raise ValueError(
            "time_averaging must not exceed half the number of frames; NanoPyx "
            "would otherwise change it silently"
        )
    if averaging > 1 and frame_count // averaging < 4:
        raise ValueError(
            "time_averaging > 1 requires at least four averaged frame groups "
            "for NanoPyx cubic interpolation"
        )

    padded_size = max(array.shape[1:]) + (max(array.shape[1:]) % 2)
    if maximum > 0 and 2 * maximum + 1 >= padded_size:
        raise ValueError(
            "max_expected_drift is too large for the projection dimensions; "
            "NanoPyx would otherwise ignore it silently"
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
        _pad_movie_to_even_square(array.astype(np.float32, copy=False))
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
        time_averaging=averaging,
        max_drift=maximum,
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
            xy_shifts = shifts.copy()
            xy_shifts[:, 0] = 0.0
            z_volumes = apply_drift(
                z_volumes,
                xy_shifts,
                axes="TZYX",
                interpolation_order=1,
                cval=0.0,
                output_dtype="float32",
                workers=worker_count,
            )
        projection_axis = 2 if axial_axis == "Y" else 3
        axial_shifts = _nanopyx_drift(
            _project(z_volumes, axis=projection_axis, projection=projection),
            reference=reference,
            time_averaging=time_averaging,
            max_expected_drift=max_expected_drift,
            backend=backend,
        )
        shifts[:, 0] = axial_shifts[:, 0]

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
