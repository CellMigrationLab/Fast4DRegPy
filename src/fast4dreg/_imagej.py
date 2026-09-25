"""NumPy ports of the ImageJ 1.x interpolation used by Fiji Fast4DReg.

Fast4DReg applies drift with ``ImageProcessor.translate`` (bicubic) and
stretches the axial projection with ``Image > Scale...`` (bicubic
``FloatProcessor.resize``). ImageJ's bicubic kernel is Catmull-Rom (``a=0.5``)
without prefiltering, falls back to edge-clamped bilinear interpolation within
one pixel of the border, and returns 0 outside ``[-1, size)``. These functions
reproduce that arithmetic for 32-bit (float) images, which is what the Fiji
macros use when "Save RAM" is off. They were verified against ImageJ 1.53t.
"""

from __future__ import annotations

import numpy as np

_A = 0.5  # ImageJ ImageProcessor.cubic(): Catmull-Rom


def _cubic(x: np.ndarray) -> np.ndarray:
    x = np.abs(np.asarray(x, dtype=np.float64))
    z = np.zeros_like(x)
    near = x < 1.0
    far = (x >= 1.0) & (x < 2.0)
    z[near] = x[near] ** 2 * (x[near] * (-_A + 2.0) + (_A - 3.0)) + 1.0
    z[far] = -_A * x[far] ** 3 + 5.0 * _A * x[far] ** 2 - 8.0 * _A * x[far] + 4.0 * _A
    return z


def _bilinear(image: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """ImageJ ``getBilinearInterpolatedPixel`` for a float image.

    ``image`` may carry leading batch axes; the same sample grid is used for
    every plane.
    """
    height, width = image.shape[-2:]
    out = np.zeros(image.shape[:-2] + xs.shape, dtype=np.float64)
    inside = (xs >= -1) & (xs < width) & (ys >= -1) & (ys < height)
    if not np.any(inside):
        return out
    x = np.maximum(xs[inside], 0.0)
    x = np.where(x >= width - 1.0, width - 1.001, x)
    y = np.maximum(ys[inside], 0.0)
    y = np.where(y >= height - 1.0, height - 1.001, y)
    xb = x.astype(np.intp)
    yb = y.astype(np.intp)
    fx = x - xb
    fy = y - yb
    lower_left = image[..., yb, xb]
    lower_right = image[..., yb, xb + 1]
    upper_right = image[..., yb + 1, xb + 1]
    upper_left = image[..., yb + 1, xb]
    upper = upper_left + fx * (upper_right - upper_left)
    lower = lower_left + fx * (lower_right - lower_left)
    out[..., inside] = lower + fy * (upper - lower)
    return out


def _bicubic_rows_cols(image: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """ImageJ ``getBicubicInterpolatedPixel`` on a separable sampling grid.

    ``xs`` has shape ``(W,)`` and ``ys`` shape ``(H,)``; the result is sampled
    at every ``(ys[j], xs[i])``.
    """
    height, width = image.shape
    u0 = np.floor(xs).astype(np.intp)
    v0 = np.floor(ys).astype(np.intp)
    uc = np.clip(u0, 1, max(width - 3, 1))
    vc = np.clip(v0, 1, max(height - 3, 1))

    columns = np.zeros((height, xs.size), dtype=np.float64)
    # Pixels whose support leaves the image are overwritten by ImageJ's
    # bilinear edge rule below, so clipped indices only need to be valid.
    for i in range(4):
        u = uc - 1 + i
        columns += image[:, np.clip(u, 0, width - 1)] * _cubic(xs - u)[None, :]
    result = np.zeros((ys.size, xs.size), dtype=np.float64)
    for j in range(4):
        v = vc - 1 + j
        result += columns[np.clip(v, 0, height - 1), :] * _cubic(ys - v)[:, None]

    edge_x = (u0 <= 0) | (u0 >= width - 2)
    edge_y = (v0 <= 0) | (v0 >= height - 2)
    _apply_edge_rule(image, result, xs, ys, edge_x, edge_y)
    return result


def _apply_edge_rule(
    image: np.ndarray,
    result: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    edge_x: np.ndarray,
    edge_y: np.ndarray,
) -> None:
    """Overwrite border samples with ImageJ's bilinear fallback, in place.

    Only the affected rows and columns are evaluated, so the cost scales with
    the border rather than with the whole plane.
    """
    if np.any(edge_y):
        rows = np.flatnonzero(edge_y)
        grid_y, grid_x = np.meshgrid(ys[rows], xs, indexing="ij")
        result[..., rows, :] = _bilinear(image, grid_x, grid_y)
    if np.any(edge_x):
        columns = np.flatnonzero(edge_x)
        grid_y, grid_x = np.meshgrid(ys, xs[columns], indexing="ij")
        result[..., columns] = _bilinear(image, grid_x, grid_y)


def _translate_bicubic(image: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Fast path of :func:`_bicubic_rows_cols` for a constant translation.

    Every output pixel shares the same fractional offset, so the Catmull-Rom
    weights are scalars and the taps are contiguous slices of a zero-padded
    copy. Samples whose support leaves the image are replaced by the edge rule.
    """
    height, width = image.shape[-2:]
    kx = int(np.floor(-dx))
    ky = int(np.floor(-dy))
    fx = -dx - kx
    fy = -dy - ky
    pad = max(abs(kx), abs(ky)) + 3
    padded = np.pad(image, [(0, 0)] * (image.ndim - 2) + [(pad, pad), (pad, pad)])
    columns = np.zeros((*image.shape[:-2], height + 2 * pad, width), dtype=np.float64)
    for i in range(4):
        start = pad + kx - 1 + i
        weight = _cubic(np.float64(fx + 1 - i))
        columns += padded[..., start : start + width] * weight
    result = np.zeros(image.shape, dtype=np.float64)
    for j in range(4):
        start = pad + ky - 1 + j
        weight = _cubic(np.float64(fy + 1 - j))
        result += columns[..., start : start + height, :] * weight
    u0 = np.arange(width) + kx
    v0 = np.arange(height) + ky
    _apply_edge_rule(
        image,
        result,
        np.arange(width, dtype=np.float64) - dx,
        np.arange(height, dtype=np.float64) - dy,
        (u0 <= 0) | (u0 >= width - 2),
        (v0 <= 0) | (v0 >= height - 2),
    )
    return result


def _validate_plane(plane: np.ndarray) -> np.ndarray:
    array = np.asarray(plane, dtype=np.float64)
    if array.ndim != 2:
        raise ValueError(f"expected a 2D plane, got shape {array.shape}")
    if min(array.shape) < 2:
        raise ValueError(
            "ImageJ interpolation requires planes of at least 2 x 2 pixels, "
            f"got {array.shape}"
        )
    return array


def _translate_stack(stack: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """``ImageProcessor.translate`` applied to every plane of ``(..., H, W)``."""
    height, width = stack.shape[-2:]
    if dx == int(dx) and dy == int(dy):
        out = np.zeros_like(stack)
        ix, iy = int(dx), int(dy)
        dst_y = slice(max(iy, 0), min(height, height + iy))
        dst_x = slice(max(ix, 0), min(width, width + ix))
        src_y = slice(max(-iy, 0), min(height, height - iy))
        src_x = slice(max(-ix, 0), min(width, width - ix))
        if dst_y.start < dst_y.stop and dst_x.start < dst_x.stop:
            out[..., dst_y, dst_x] = stack[..., src_y, src_x]
        return out
    return _translate_bicubic(stack, dx, dy)


def translate_plane(plane: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Return ``ImageProcessor.translate(dx, dy)`` with BICUBIC interpolation.

    Positive ``dx``/``dy`` move content towards larger column/row indices.
    Integer offsets are an exact pixel shift with zero fill, as in ImageJ.
    """
    return _translate_stack(_validate_plane(plane), float(dx), float(dy))


def resize_rows(plane: np.ndarray, factor: int) -> np.ndarray:
    """Return ``FloatProcessor.resize(width, factor * height)`` (BICUBIC).

    This is what Fiji's ``Scale... y=<factor> interpolation=Bicubic`` does to
    the axial projection. ImageJ maps pixel centres with an exact scale of
    ``factor`` (plus its quarter-pixel offset), so a displacement of ``d``
    rows becomes exactly ``factor * d`` rows.
    """
    image = _validate_plane(plane)
    height, width = image.shape
    new_height = height * factor
    scale = new_height / height
    dst_center = new_height / 2.0
    if new_height != height:
        dst_center += scale / 4.0
    ys = (np.arange(new_height, dtype=np.float64) - dst_center) / scale + height / 2.0
    xs = np.arange(width, dtype=np.float64)
    return _bicubic_rows_cols(image, xs, ys)


def translate_volume(
    volume: np.ndarray,
    translation: np.ndarray,
    *,
    axial_projection_axis: str,
    crop_yx: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    """Apply a ``(dz,dy,dx)`` translation in Fiji Fast4DReg's two-pass order.

    Fiji translates every Z plane by ``(dx,dy)`` and then translates every
    resliced axial plane by ``dz`` along Z. For the "Top" reslice
    (``axial_projection_axis="Y"``) the axial planes are X-by-Z images, one per
    Y row; for "Left" (``"X"``) they are Y-by-Z images, one per X column. The
    axis choice only changes which lateral columns use ImageJ's edge rule.
    ``crop_yx=(y0, y1, x0, x1)`` crops between the two passes, as Fiji's
    "Crop output" does before Z correction.
    """
    source = np.asarray(volume, dtype=np.float64)
    if source.ndim != 3:
        raise ValueError(f"volume must have shape (Z,Y,X), got {source.shape}")
    dz, dy, dx = (float(value) for value in translation)
    if min(source.shape[1:]) < 2 or (dz != 0 and source.shape[0] < 2):
        raise ValueError(
            f"ImageJ interpolation requires planes of at least 2 x 2 pixels, "
            f"got volume shape {source.shape}"
        )
    result = source
    if dx != 0 or dy != 0:
        result = _translate_stack(result, dx, dy)
    if crop_yx is not None:
        y0, y1, x0, x1 = crop_yx
        result = result[:, y0:y1, x0:x1]
    if dz != 0:
        # Axial planes are Z rows by lateral columns: (Y, Z, X) for "Top" and
        # (X, Z, Y) for "Left"; translate all of them at once along Z.
        if axial_projection_axis == "Y":
            order, inverse = (1, 0, 2), (1, 0, 2)
        elif axial_projection_axis == "X":
            order, inverse = (2, 0, 1), (1, 2, 0)
        else:
            raise ValueError("axial_projection_axis must be 'X' or 'Y'")
        planes = np.ascontiguousarray(result.transpose(order))
        result = _translate_stack(planes, 0.0, dz).transpose(inverse)
    return np.ascontiguousarray(result)
