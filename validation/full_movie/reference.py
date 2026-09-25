"""Reference fitting helpers for full-movie validation."""

from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from fast4dreg._imagej import translate_volume


def fit_translation(
    source: np.ndarray,
    target: np.ndarray,
    initial: np.ndarray,
    *,
    target_offset: tuple[int, int, int],
    round_uint16: bool,
    margin: int = 6,
) -> tuple[np.ndarray, float, float]:
    """Fit ``target ~ T(source, d)`` using the ImageJ two-pass transform."""
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    target_start = np.asarray(target_offset)
    shape = np.asarray(target.shape)
    whole = np.rint(initial).astype(int)

    def translated_block(displacement: np.ndarray) -> np.ndarray:
        start = target_start - whole - margin
        stop = start + shape + 2 * margin
        clipped_start = np.maximum(start, 0)
        clipped_stop = np.minimum(stop, source.shape)
        window = np.zeros(tuple(stop - start))
        inner = tuple(
            slice(a - s, b - s)
            for a, b, s in zip(clipped_start, clipped_stop, start, strict=True)
        )
        source_slices = tuple(
            slice(a, b) for a, b in zip(clipped_start, clipped_stop, strict=True)
        )
        window[inner] = source[source_slices]
        moved = translate_volume(
            window,
            displacement - whole,
            axial_projection_axis="Y",
        )
        moved = moved[margin:-margin, margin:-margin, margin:-margin]
        if round_uint16:
            moved = np.clip(np.floor(moved + 0.5), 0, 65535)
        return moved

    def cost(displacement: np.ndarray) -> float:
        difference = translated_block(displacement) - target
        return float(np.mean(difference**2))

    result = minimize(
        cost,
        np.asarray(initial, dtype=np.float64),
        method="Nelder-Mead",
        options={"xatol": 1e-4, "fatol": 1e-9, "maxiter": 600},
    )
    if not result.success:
        raise RuntimeError(f"translation fit failed: {result.message}")

    best = translated_block(result.x)
    exact = float(np.mean(best == target)) if round_uint16 else float("nan")
    return result.x, float(np.sqrt(result.fun)), exact


def locate_fiji_crop(raw0: np.ndarray, fiji0: np.ndarray) -> tuple[int, int]:
    """Locate the archived Fiji crop by exact frame-0 matching."""
    height, width = fiji0.shape[-2:]
    reference = fiji0[fiji0.shape[0] // 2]
    plane = raw0[raw0.shape[0] // 2]

    matches = [
        (y, x)
        for y in range(plane.shape[0] - height + 1)
        for x in range(plane.shape[1] - width + 1)
        if plane[y, x] == reference[0, 0]
        and np.array_equal(plane[y : y + height, x : x + width], reference)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one exact frame-0 crop match, found {matches}")

    y0, x0 = matches[0]
    if not np.array_equal(raw0[:, y0 : y0 + height, x0 : x0 + width], fiji0):
        raise RuntimeError("Fiji frame 0 is not an exact crop of raw frame 0")
    return y0, x0


def central_block(
    shape: tuple[int, ...],
    size: tuple[int, int, int],
) -> tuple[slice, ...]:
    return tuple(
        slice((n - s) // 2, (n - s) // 2 + s)
        for n, s in zip(shape, size, strict=True)
    )
