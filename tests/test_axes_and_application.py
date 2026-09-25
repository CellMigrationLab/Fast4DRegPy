import numpy as np
import pytest

from fast4dreg import apply_channel_shifts, apply_drift
from fast4dreg.axes import from_ctzyx, to_ctzyx


@pytest.mark.parametrize(
    ("shape", "axes"),
    [
        ((3, 12, 16), "TYX"),
        ((3, 5, 12, 16), "TZYX"),
        ((2, 5, 12, 16), "CZYX"),
        ((2, 3, 5, 12, 16), "CTZYX"),
        ((3, 5, 2, 12, 16), "TZCYX"),
    ],
)
def test_axis_round_trip(shape, axes):
    image = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
    canonical, original_axes = to_ctzyx(image, axes)
    restored = from_ctzyx(canonical, original_axes)
    np.testing.assert_array_equal(restored, image)


def test_axis_validation_rejects_ambiguous_input():
    with pytest.raises(ValueError, match="duplicates"):
        to_ctzyx(np.zeros((2, 3, 4)), "YYX")
    with pytest.raises(ValueError, match="both Y and X"):
        to_ctzyx(np.zeros((2, 3)), "TZ")


def test_axes_are_case_insensitive_and_return_normalized():
    image = np.ones((2, 12, 16), dtype=np.float32)
    canonical, axes = to_ctzyx(image, "tyx")
    assert canonical.shape == (1, 2, 1, 12, 16)
    assert axes == "TYX"


def test_apply_time_drift_can_explicitly_preserve_input_dtype():
    image = np.zeros((2, 2, 3, 12, 12), dtype=np.uint16)
    image[:, :, 1, 5, 5] = 100
    shifts = np.asarray([[0, 0, 0], [0, 2, -1]], dtype=np.float32)
    corrected = apply_drift(
        image,
        shifts,
        axes="CTZYX",
        interpolation_order=0,
        output_dtype="input",
    )

    assert corrected.shape == image.shape
    assert corrected.dtype == image.dtype
    assert corrected[0, 1, 1, 7, 4] == 100
    assert corrected[1, 1, 1, 7, 4] == 100


def test_apply_channel_shifts_applies_each_shift_to_all_timepoints():
    image = np.zeros((2, 3, 1, 10, 10), dtype=np.uint8)
    image[:, :, 0, 4, 4] = 1
    shifts = np.asarray([[0, 0, 0], [0, -1, 2]], dtype=np.float32)
    corrected = apply_channel_shifts(image, shifts, axes="CTZYX", interpolation_order=0)

    assert np.all(corrected[0, :, 0, 4, 4] == 1)
    assert np.all(corrected[1, :, 0, 3, 6] == 1)
    assert corrected.dtype == np.float32


def test_float32_default_avoids_integer_subpixel_quantization():
    image = np.zeros((2, 8, 8), dtype=np.uint16)
    image[:, 3, 3] = 1
    corrected = apply_drift(
        image,
        [[0, 0, 0], [0, 0.5, 0]],
        axes="TYX",
        interpolation_order=1,
    )
    assert corrected.dtype == np.float32
    assert 0 < corrected[1, 3, 3] < 1




def test_default_transform_uses_cubic_interpolation():
    image = np.zeros((2, 12, 12), dtype=np.float32)
    image[:, 5, 5] = 1
    shifts = np.asarray([[0, 0, 0], [0, 0.5, 0.25]], dtype=np.float32)

    default = apply_drift(image, shifts, axes="TYX")
    cubic = apply_drift(image, shifts, axes="TYX", interpolation_order=3)
    linear = apply_drift(image, shifts, axes="TYX", interpolation_order=1)

    np.testing.assert_allclose(default, cubic, rtol=0, atol=0)
    assert not np.allclose(default, linear)


def test_invalid_transform_options_are_rejected_even_for_zero_shifts():
    image = np.ones((2, 8, 8), dtype=np.float32)
    shifts = np.zeros((2, 3), dtype=np.float32)
    with pytest.raises(ValueError, match="between 0 and 5"):
        apply_drift(image, shifts, axes="TYX", interpolation_order=6)
    with pytest.raises(ValueError, match="finite"):
        apply_drift(image, shifts, axes="TYX", cval=np.nan)
    with pytest.raises(ValueError, match="output_dtype"):
        apply_drift(image, shifts, axes="TYX", output_dtype="uint16")


@pytest.mark.parametrize(
    ("workers", "error"),
    [(0, ValueError), (-1, ValueError), (True, TypeError), (1.5, TypeError)],
)
def test_invalid_worker_counts_are_rejected(workers, error):
    image = np.ones((2, 8, 8), dtype=np.float32)
    with pytest.raises(error, match="workers"):
        apply_drift(image, np.zeros((2, 3)), axes="TYX", workers=workers)


def test_parallel_time_application_matches_serial_result():
    rng = np.random.default_rng(7)
    image = rng.normal(size=(2, 4, 3, 17, 19)).astype(np.float32)
    shifts = np.asarray(
        [[0, 0, 0], [0.5, -1.25, 2], [-0.75, 1, -2.5], [1, 0.25, 0.5]],
        dtype=np.float32,
    )

    serial = apply_drift(image, shifts, axes="CTZYX", workers=1)
    parallel = apply_drift(image, shifts, axes="CTZYX", workers=4)

    np.testing.assert_array_equal(parallel, serial)


def test_parallel_channel_application_matches_serial_result():
    rng = np.random.default_rng(11)
    image = rng.normal(size=(3, 2, 4, 16, 18)).astype(np.float32)
    shifts = np.asarray(
        [[0, 0, 0], [0.5, -1, 2.25], [-0.5, 1.5, -2]], dtype=np.float32
    )

    serial = apply_channel_shifts(image, shifts, axes="CTZYX", workers=1)
    parallel = apply_channel_shifts(image, shifts, axes="CTZYX", workers=3)

    np.testing.assert_array_equal(parallel, serial)


def test_parallel_worker_failure_is_propagated(monkeypatch):
    image = np.ones((3, 8, 8), dtype=np.float32)

    def fail(*args, **kwargs):
        raise RuntimeError("transform failed")

    monkeypatch.setattr("fast4dreg.transform._shift_volume_into", fail)
    with pytest.raises(RuntimeError, match="transform failed"):
        apply_drift(image, np.zeros((3, 3)), axes="TYX", workers=2)


def test_nonfinite_image_is_rejected():
    image = np.ones((2, 8, 8), dtype=np.float32)
    image[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        apply_drift(image, np.zeros((2, 3)), axes="TYX")
