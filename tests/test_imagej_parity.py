"""Parity with ImageJ 1.x interpolation as used by Fiji Fast4DReg.

``tests/data/imagej_interpolation/reference.npz`` was produced by calling
ImageJ 1.53t's own ``ImageProcessor.translate`` and ``FloatProcessor.resize``
(see ``validation/fiji/make_imagej_interpolation_fixture.py``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fast4dreg import apply_drift
from fast4dreg._imagej import resize_rows, translate_plane, translate_volume
from fast4dreg.estimation import _scale_axial_projection

FIXTURE = Path(__file__).parent / "data" / "imagej_interpolation" / "reference.npz"
# ImageJ computes in double precision and stores float32 pixels.
ATOL = 2e-4


@pytest.fixture(scope="module")
def reference():
    with np.load(FIXTURE) as data:
        return {key: data[key] for key in data.files}


def test_translate_plane_matches_imagej(reference):
    for (dx, dy), expected in zip(
        reference["translations"], reference["translated"], strict=True
    ):
        np.testing.assert_allclose(
            translate_plane(reference["plane"], dx, dy), expected, rtol=0, atol=ATOL
        )


@pytest.mark.parametrize("factor", [2, 4, 5, 6])
def test_resize_rows_matches_imagej_scale(reference, factor):
    np.testing.assert_allclose(
        resize_rows(reference["axial"], factor),
        reference[f"resized_x{factor}"],
        rtol=0,
        atol=ATOL,
    )


def test_axial_projection_scaling_matches_fiji_scale_command(reference):
    # A 9 x 34 axial projection gives Fiji's round(34/9) = 4.
    scaled, factor = _scale_axial_projection(reference["axial"][None])
    assert factor == 4
    np.testing.assert_allclose(scaled[0], reference["resized_x4"], rtol=0, atol=ATOL)


def test_axial_projection_scaling_preserves_displacement_scale():
    # Fiji divides the measured axial shift by the integer factor, so the
    # stretch must map a displacement of d rows to exactly factor*d rows.
    z = np.arange(20, dtype=np.float64)
    columns = np.arange(80, dtype=np.float64)
    profile = np.exp(-((z[:, None] - 8.0) ** 2) / 4.0) * (1 + 0 * columns)
    moved = np.exp(-((z[:, None] - 9.0) ** 2) / 4.0) * (1 + 0 * columns)
    scaled, factor = _scale_axial_projection(np.stack([profile, moved]))

    def centroid(image):
        column = image[:, 40].astype(np.float64)
        return float(np.sum(np.arange(column.size) * column) / np.sum(column))

    assert factor == 4
    assert centroid(scaled[1]) - centroid(scaled[0]) == pytest.approx(4.0, abs=1e-3)


def test_default_transform_is_fiji_two_pass_imagej_bicubic():
    rng = np.random.default_rng(3)
    image = rng.gamma(2.0, 100.0, size=(2, 6, 12, 14)).astype(np.float32)
    shifts = np.asarray([[0, 0, 0], [0.4, -1.3, 2.7]], dtype=np.float32)

    corrected = apply_drift(image, shifts, axes="TZYX")

    np.testing.assert_array_equal(corrected[0], image[0])
    expected = translate_volume(image[1], shifts[1], axial_projection_axis="Y")
    np.testing.assert_allclose(corrected[1], expected, rtol=0, atol=1e-3)


def test_imagej_integer_output_rounds_and_clips_like_imagej_16_bit():
    # Catmull-Rom overshoots next to sharp edges; an integer output must clip
    # to the dtype range (ImageJ's 16-bit conversion) instead of wrapping.
    image = np.zeros((2, 3, 10, 10), dtype=np.uint16)
    image[:, :, 4:6, 4:6] = 60000
    shifts = [[0, 0, 0], [0, 0.5, 0.5]]

    as_float = apply_drift(image, shifts, axes="TZYX")
    as_input = apply_drift(image, shifts, axes="TZYX", output_dtype="input")

    assert as_float.min() < 0
    assert as_input.dtype == np.uint16
    expected = np.clip(np.floor(as_float + 0.5), 0, 65535).astype(np.uint16)
    np.testing.assert_array_equal(as_input, expected)
