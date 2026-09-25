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
    """ImageJ ``getBilinearInterpolatedPixel`` for a float image."""
    height, width = image.shape
    out = np.zeros(xs.shape, dtype=np.float64)
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
    lower_left = image[yb, xb]
    lower_right = image[yb, xb + 1]
    upper_right = image[yb + 1, xb + 1]
    upper_left = image[yb + 1, xb]
    upper = upper_left + fx * (upper_right - upper_left)
    lower = lower_left + fx * (lower_right - lower_left)
    out[inside] = lower + fy * (upper - lower)
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
    edge = edge_y[:, None] | edge_x[None, :]
    if np.any(edge):
        grid_y, grid_x = np.meshgrid(ys, xs, indexing="ij")
        result[edge] = _bilinear(image, grid_x[edge], grid_y[edge])
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


def translate_plane(plane: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """Return ``ImageProcessor.translate(dx, dy)`` with BICUBIC interpolation.

    Positive ``dx``/``dy`` move content towards larger column/row indices.
    Integer offsets are an exact pixel shift with zero fill, as in ImageJ.
    """
    image = _validate_plane(plane)
    height, width = image.shape
    dx = float(dx)
    dy = float(dy)
    if dx == int(dx) and dy == int(dy):
        out = np.zeros_like(image)
        ix, iy = int(dx), int(dy)
        dst_y = slice(max(iy, 0), min(height, height + iy))
        dst_x = slice(max(ix, 0), min(width, width + ix))
        src_y = slice(max(-iy, 0), min(height, height - iy))
        src_x = slice(max(-ix, 0), min(width, width - ix))
        if dst_y.start < dst_y.stop and dst_x.start < dst_x.stop:
            out[dst_y, dst_x] = image[src_y, src_x]
        return out
    xs = np.arange(width, dtype=np.float64) - dx
    ys = np.arange(height, dtype=np.float64) - dy
    return _bicubic_rows_cols(image, xs, ys)


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
    result = source
    if dx != 0 or dy != 0:
        result = np.stack([translate_plane(plane, dx, dy) for plane in result])
    if crop_yx is not None:
        y0, y1, x0, x1 = crop_yx
        result = result[:, y0:y1, x0:x1]
    if dz != 0:
        if axial_projection_axis == "Y":
            planes = [
                translate_plane(result[:, y, :], 0.0, dz)
                for y in range(result.shape[1])
            ]
            result = np.stack(planes, axis=1)
        elif axial_projection_axis == "X":
            planes = [
                translate_plane(result[:, :, x], 0.0, dz)
                for x in range(result.shape[2])
            ]
            result = np.stack(planes, axis=2)
        else:
            raise ValueError("axial_projection_axis must be 'X' or 'Y'")
    return result
