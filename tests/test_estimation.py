import numpy as np
import pytest

from fast4dreg import estimate_time_drift
from fast4dreg._drift import _crop_movie_to_even_square, _nanopyx_drift
from fast4dreg.estimation import _estimate_sequence_shifts, _scale_axial_projection


def _movie(frames=4, shape=(12, 14)):
    y, x = np.indices(shape, dtype=np.float32)
    base = np.exp(-((y - 4) ** 2 + (x - 7) ** 2) / 6)
    return np.stack([np.roll(base, index, axis=1) for index in range(frames)])




def test_even_square_preparation_matches_fiji_center_crop():
    movie = np.arange(2 * 7 * 10, dtype=np.float32).reshape(2, 7, 10)
    cropped = _crop_movie_to_even_square(movie)
    assert cropped.shape == (2, 6, 6)
    np.testing.assert_array_equal(cropped, movie[:, 0:6, 2:8])



def test_axial_projection_scaling_matches_fiji_shape_rule():
    movie = np.zeros((2, 9, 52), dtype=np.float32)
    movie[:, 4, 20] = 1.0

    scaled, factor = _scale_axial_projection(movie)

    assert factor == 6
    assert scaled.shape == (2, 54, 52)
    assert scaled.dtype == np.float32


def test_axial_projection_scaling_clamps_unusual_aspect_ratio_to_one():
    movie = np.ones((2, 20, 10), dtype=np.float32)

    scaled, factor = _scale_axial_projection(movie)

    assert factor == 1
    np.testing.assert_array_equal(scaled, movie)

def test_time_averaging_keeps_trailing_partial_block_like_fiji():
    # 14 frames in blocks of 3 give five blocks; Fiji keeps the last partial
    # block (NanoPyx 2.1.4 would silently drop it).
    shifts = _nanopyx_drift(
        _movie(frames=14, shape=(16, 18)),
        reference="first",
        time_averaging=3,
        max_expected_drift=0,
        backend="threaded",
    )
    assert shifts.shape == (14, 2)
    np.testing.assert_allclose(shifts[0], 0, atol=1e-6)


def test_time_estimation_accepts_lowercase_axes(monkeypatch):
    monkeypatch.setattr(
        "fast4dreg.estimation._nanopyx_drift",
        lambda movie, **kwargs: np.zeros((movie.shape[0], 2), dtype=np.float32),
    )
    result = estimate_time_drift(_movie(), axes="tyx")
    assert result.shape == (4, 3)


@pytest.mark.parametrize(
    ("keyword", "value", "error"),
    [
        ("time_averaging", 0, ValueError),
        ("time_averaging", 1.5, TypeError),
        ("max_expected_drift", -1, ValueError),
        ("max_expected_drift", 2.0, TypeError),
        ("backend", "gpu", ValueError),
    ],
)
def test_nanopyx_parameters_are_strict(keyword, value, error):
    options = {
        "reference": "first",
        "time_averaging": 1,
        "max_expected_drift": 0,
        "backend": "threaded",
    }
    options[keyword] = value
    with pytest.raises(error):
        _nanopyx_drift(_movie(), **options)


def test_estimation_rejects_parameters_fiji_would_silently_change():
    with pytest.raises(ValueError, match="fewer than two averaged blocks"):
        _nanopyx_drift(
            _movie(frames=4),
            reference="first",
            time_averaging=4,
            max_expected_drift=0,
            backend="threaded",
        )
    with pytest.raises(ValueError, match="too large"):
        _nanopyx_drift(
            _movie(shape=(8, 8)),
            reference="first",
            time_averaging=1,
            max_expected_drift=3,
            backend="threaded",
        )


def test_bounded_window_is_centred_2r_plus_1_like_fiji():
    # Fiji crops the correlation map to the centred 2r+1 window, so a +3 px
    # translation is found exactly with r=5. NanoPyx 2.1.4's own bounded mode
    # slices an off-centre 2r window and silently returns ~3.53 px here.
    y, x = np.indices((40, 40), dtype=np.float32)
    base = np.exp(-((y - 17) ** 2 + (x - 21) ** 2) / 8) + 0.5 * np.exp(
        -((y - 25) ** 2 + (x - 12) ** 2) / 5
    )
    movie = np.stack([base, np.roll(base, -3, axis=1), np.roll(base, 3, axis=0)])
    options = {"reference": "first", "time_averaging": 1, "backend": "threaded"}
    automatic = _nanopyx_drift(movie, max_expected_drift=0, **options)
    bounded = _nanopyx_drift(movie, max_expected_drift=5, **options)
    np.testing.assert_allclose(automatic, [[0, 0], [0, 3], [-3, 0]], atol=0.01)
    np.testing.assert_allclose(bounded, automatic, atol=0.01)


def test_fiji_compatibility_path_rejects_unthreaded_backend():
    with pytest.raises(ValueError, match="backend='unthreaded' is not available"):
        _nanopyx_drift(
            _movie(frames=6),
            reference="first",
            time_averaging=2,
            max_expected_drift=0,
            backend="unthreaded",
        )

    with pytest.raises(ValueError, match="backend='unthreaded' is not available"):
        _nanopyx_drift(
            _movie(frames=4, shape=(24, 24)),
            reference="first",
            time_averaging=1,
            max_expected_drift=3,
            backend="unthreaded",
        )


def test_selected_backend_error_is_not_swallowed(monkeypatch):
    class BrokenEstimator:
        def _run_threaded(self, *args, **kwargs):
            raise RuntimeError("backend failed")

    monkeypatch.setattr(
        "fast4dreg._drift._load_nanopyx_estimator", lambda: BrokenEstimator()
    )
    with pytest.raises(RuntimeError, match="backend failed"):
        _nanopyx_drift(
            _movie(),
            reference="first",
            time_averaging=1,
            max_expected_drift=0,
            backend="threaded",
        )


def test_z_projection_is_computed_after_xy_correction(monkeypatch):
    volumes = np.zeros((2, 3, 8, 8), dtype=np.float32)
    volumes[:, 1, 3, 3] = 1
    calls = []

    def fake_drift(movie, **kwargs):
        calls.append(movie.copy())
        if len(calls) == 1:
            return np.asarray([[0, 0], [0, 1]], dtype=np.float32)
        return np.zeros((2, 2), dtype=np.float32)

    monkeypatch.setattr("fast4dreg.estimation._nanopyx_drift", fake_drift)
    # This test isolates operation ordering. Axial scaling has its own tests.
    monkeypatch.setattr(
        "fast4dreg.estimation._scale_axial_projection",
        lambda movie: (movie, 1),
    )
    _estimate_sequence_shifts(
        volumes,
        projection="max",
        reference="first",
        correct_xy=True,
        correct_z=True,
        axial_projection_axis="Y",
        time_averaging=1,
        max_expected_drift=0,
        backend="threaded",
        workers=1,
    )

    assert len(calls) == 2
    # Moving volume was translated by dx=+1 before the Y projection.
    assert calls[1][1, 1, 3] == pytest.approx(0, abs=1e-6)
    assert calls[1][1, 1, 4] == pytest.approx(1)


def test_z_projection_parallel_preparation_matches_serial(monkeypatch):
    rng = np.random.default_rng(19)
    volumes = rng.normal(size=(4, 3, 12, 14)).astype(np.float32)

    def run(workers):
        calls = []

        def fake_drift(movie, **kwargs):
            calls.append(movie.copy())
            if len(calls) == 1:
                return np.asarray(
                    [[0, 0], [0.5, -1], [-0.25, 1.5], [1, 0.25]],
                    dtype=np.float32,
                )
            return np.zeros((4, 2), dtype=np.float32)

        monkeypatch.setattr("fast4dreg.estimation._nanopyx_drift", fake_drift)
        _estimate_sequence_shifts(
            volumes,
            projection="max",
            reference="first",
            correct_xy=True,
            correct_z=True,
            axial_projection_axis="Y",
            time_averaging=1,
            max_expected_drift=0,
            backend="threaded",
            workers=workers,
        )
        return calls[1]

    np.testing.assert_array_equal(run(4), run(1))
