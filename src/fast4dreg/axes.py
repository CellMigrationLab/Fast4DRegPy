"""Axis normalization and input validation.

All public registration functions accept an explicit axes string.  Arrays are
converted to ``CTZYX`` internally and restored to their original order before
being returned.
"""

from __future__ import annotations

import numpy as np

CANONICAL_AXES = "CTZYX"


def validate_image(image: np.ndarray, *, name: str = "image") -> np.ndarray:
    """Return ``image`` as an array after strict numeric validation."""
    array = np.asarray(image)
    if array.ndim < 2:
        raise ValueError(f"{name} must have at least two dimensions")
    if array.size == 0 or any(size == 0 for size in array.shape):
        raise ValueError(f"{name} must not contain empty dimensions")
    if not np.issubdtype(array.dtype, np.number) or np.issubdtype(
        array.dtype, np.complexfloating
    ):
        raise TypeError(f"{name} must contain real numeric values, got {array.dtype}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains non-finite values")
    return array


def normalize_axes(image: np.ndarray, axes: str) -> str:
    """Validate and normalize an axes string for ``image``."""
    if not isinstance(axes, str):
        raise TypeError("axes must be a string")
    normalized = axes.upper().strip()
    if len(normalized) != image.ndim:
        raise ValueError(
            f"axes={normalized!r} has {len(normalized)} entries, but image has "
            f"{image.ndim} dimensions"
        )
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"axes must not contain duplicates: {normalized!r}")
    unknown = set(normalized) - set(CANONICAL_AXES)
    if unknown:
        raise ValueError(f"unsupported axes {sorted(unknown)} in {normalized!r}")
    if "Y" not in normalized or "X" not in normalized:
        raise ValueError("axes must contain both Y and X")
    return normalized


def to_ctzyx(image: np.ndarray, axes: str) -> tuple[np.ndarray, str]:
    """Convert a validated image to canonical ``CTZYX`` order."""
    array = validate_image(image)
    normalized_axes = normalize_axes(array, axes)
    current_axes = list(normalized_axes)
    expanded = array

    for axis in CANONICAL_AXES:
        if axis not in current_axes:
            expanded = np.expand_dims(expanded, axis=-1)
            current_axes.append(axis)

    permutation = [current_axes.index(axis) for axis in CANONICAL_AXES]
    return np.transpose(expanded, permutation), normalized_axes


def from_ctzyx(image: np.ndarray, axes: str) -> np.ndarray:
    """Restore a canonical ``CTZYX`` array to ``axes`` order."""
    array = np.asarray(image)
    if array.ndim != 5:
        raise ValueError("canonical image must have five CTZYX dimensions")
    if not isinstance(axes, str):
        raise TypeError("axes must be a string")
    normalized_axes = axes.upper().strip()
    if len(set(normalized_axes)) != len(normalized_axes):
        raise ValueError(f"axes must not contain duplicates: {normalized_axes!r}")
    unknown = set(normalized_axes) - set(CANONICAL_AXES)
    if unknown:
        raise ValueError(f"unsupported axes {sorted(unknown)} in {normalized_axes!r}")

    current_axes = list(CANONICAL_AXES)
    restored = array
    for axis in CANONICAL_AXES:
        if axis not in normalized_axes:
            index = current_axes.index(axis)
            if restored.shape[index] != 1:
                raise ValueError(
                    f"cannot remove non-singleton {axis} dimension with size "
                    f"{restored.shape[index]}"
                )
            restored = np.take(restored, 0, axis=index)
            current_axes.pop(index)

    permutation = [current_axes.index(axis) for axis in normalized_axes]
    return np.transpose(restored, permutation)
