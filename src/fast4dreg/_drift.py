"""NanoPyx drift estimation with Fiji-compatible edge cases.

The simple case delegates directly to NanoPyx's selected DriftEstimator backend.
Fiji-compatible time averaging and bounded searches use NanoPyx's correlation
primitives because NanoPyx 2.1.4 and NanoJ differ in those two behaviours.
"""

from __future__ import annotations

import numpy as np

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


def _load_nanopyx_estimator():
    try:
        from nanopyx.core.analysis._le_drift_calculator import DriftEstimator
    except ImportError as exc:  # pragma: no cover - package smoke test covers this
        raise ImportError(
            "NanoPyx 2.1.4 is required for drift estimation. Install this "
            "project with `python -m pip install -e .`."
        ) from exc
    return DriftEstimator(verbose=False)


def _load_nanopyx_ccm():
    try:
        from nanopyx.core.analysis.ccm import calculate_ccm, calculate_ccm_from_ref
        from nanopyx.core.analysis.estimate_shift import GetMaxOptimizer
    except ImportError as exc:  # pragma: no cover - package smoke test covers this
        raise ImportError(
            "NanoPyx 2.1.4 is required for drift estimation. Install this "
            "project with `python -m pip install -e .`."
        ) from exc
    return calculate_ccm, calculate_ccm_from_ref, GetMaxOptimizer


def _validate_movie(
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
    blocks = -(-array.shape[0] // averaging)
    if blocks < 2:
        raise ValueError(
            f"time_averaging={averaging} leaves fewer than two averaged blocks "
            f"for {array.shape[0]} frames; Fiji would silently report zero drift"
        )

    cropped_size = min(array.shape[1:])
    if cropped_size % 2:
        cropped_size -= 1
    if maximum > 0 and 2 * maximum + 1 >= cropped_size - 1:
        raise ValueError(
            "max_expected_drift is too large for the projection dimensions; "
            "Fiji Fast4DReg would otherwise ignore it silently"
        )
    return array, averaging, maximum


def _average_blocks(movie: np.ndarray, block_size: int) -> np.ndarray:
    frames = movie.shape[0]
    blocks = -(-frames // block_size)
    averaged = [
        np.mean(
            movie[start : min(start + block_size, frames)],
            axis=0,
            dtype=np.float64,
        )
        for start in range(0, frames, block_size)
    ]
    if len(averaged) != blocks:
        raise RuntimeError("internal error while constructing averaged frame blocks")
    return np.asarray(averaged, dtype=np.float32)


def _correlation_maps(
    averaged: np.ndarray,
    *,
    first_frame: np.ndarray,
    reference: str,
) -> tuple[np.ndarray, type]:
    calculate_ccm, calculate_ccm_from_ref, optimizer = _load_nanopyx_ccm()
    if reference == "first":
        maps = calculate_ccm_from_ref(averaged, np.ascontiguousarray(first_frame))
    else:
        maps = calculate_ccm(averaged, 1)
    return np.asarray(maps), optimizer


def _crop_search_window(
    ccm: np.ndarray,
    max_expected_drift: int,
) -> tuple[np.ndarray, int, int | None]:
    center = ccm.shape[-1] // 2 - 1
    if max_expected_drift == 0:
        return ccm, center, None
    radius = max_expected_drift
    window = slice(center - radius, center + radius + 1)
    return ccm[:, window, window], radius, radius


def _measure_block_drifts(
    ccm: np.ndarray,
    *,
    center: int,
    radius: int | None,
    optimizer: type,
) -> np.ndarray:
    drifts = np.zeros((ccm.shape[0], 2), dtype=np.float64)
    for index, correlation in enumerate(ccm):
        correlation = np.ascontiguousarray(correlation, dtype=np.float32)
        peak = np.unravel_index(int(np.argmax(correlation)), correlation.shape)
        if radius is not None and (
            min(peak) <= 1 or max(peak) >= correlation.shape[0] - 2
        ):
            raise ValueError(
                f"the correlation peak of averaged block {index} lies at the "
                f"edge of the max_expected_drift={radius} search window "
                "(for Z this radius is in stretched axial pixels). Fiji "
                "Fast4DReg would report NaN or a clamped drift here; increase "
                "max_expected_drift or use 0 (automatic)"
            )
        row, col = optimizer(correlation).get_max()
        drifts[index] = (center - row, center - col)
    drifts -= drifts[0]
    return drifts


def _interpolate_block_drifts(
    block_drifts: np.ndarray,
    *,
    frames: int,
) -> np.ndarray:
    blocks = block_drifts.shape[0]
    if blocks == frames:
        return block_drifts
    scale = (blocks - 1) / (frames - 1)
    position = np.arange(frames) * scale
    lower = position.astype(np.intp)
    upper = np.minimum(lower + 1, blocks - 1)
    fraction = (position - lower)[:, None]
    return (1.0 - fraction) * block_drifts[lower] + fraction * block_drifts[upper]


def _fiji_drift(
    movie: np.ndarray,
    *,
    reference: str,
    time_averaging: int,
    max_expected_drift: int,
) -> np.ndarray:
    """Estimate ``(dy,dx)`` with NanoJ/Fiji averaging and search semantics."""
    averaged = _average_blocks(movie, time_averaging)
    ccm, optimizer = _correlation_maps(
        averaged,
        first_frame=movie[0],
        reference=reference,
    )
    ccm, center, radius = _crop_search_window(ccm, max_expected_drift)
    block_drifts = _measure_block_drifts(
        ccm,
        center=center,
        radius=radius,
        optimizer=optimizer,
    )
    if reference == "previous":
        block_drifts = np.cumsum(block_drifts, axis=0)
    drift = _interpolate_block_drifts(block_drifts, frames=movie.shape[0])
    if not np.all(np.isfinite(drift)):
        raise RuntimeError("NanoPyx returned non-finite drift estimates")
    return drift.astype(np.float32)


def _run_estimator(
    movie: np.ndarray,
    *,
    reference: str,
    backend: str,
) -> np.ndarray:
    estimator = _load_nanopyx_estimator()
    runner = getattr(estimator, f"_run_{backend}", None)
    if runner is None:
        raise RuntimeError(
            f"NanoPyx 2.1.4 does not provide the requested {backend!r} backend"
        )
    result = runner(
        movie,
        time_averaging=1,
        max_drift=0,
        ref_option=0 if reference == "first" else 1,
    )
    table = np.asarray(result, dtype=np.float32)
    expected_shape = (movie.shape[0], 3)
    if table.shape != expected_shape:
        raise RuntimeError(
            "NanoPyx returned an unexpected drift table with shape "
            f"{table.shape}; expected {expected_shape}"
        )
    if not np.all(np.isfinite(table)):
        raise RuntimeError("NanoPyx returned non-finite drift estimates")
    return table[:, [2, 1]]


def _nanopyx_drift(
    movie: np.ndarray,
    *,
    reference: str,
    time_averaging: int,
    max_expected_drift: int,
    backend: str,
) -> np.ndarray:
    """Return NanoPyx/Fiji-compatible translations as ``(dy,dx)``."""
    array, averaging, maximum = _validate_movie(
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
        if backend_name != "threaded":
            raise ValueError(
                "backend='unthreaded' is not available with time_averaging > 1 "
                "or max_expected_drift > 0. These Fiji-compatible modes use "
                "NanoPyx's compiled correlation primitives directly."
            )
        return _fiji_drift(
            prepared,
            reference=reference_mode,
            time_averaging=averaging,
            max_expected_drift=maximum,
        )
    return _run_estimator(prepared, reference=reference_mode, backend=backend_name)
