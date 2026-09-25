import numpy as np
import pytest

from fast4dreg import estimate_time_drift
from fast4dreg.estimation import (
    _crop_movie_to_even_square,
    _estimate_sequence_shifts,
    _nanopyx_drift,
    _scale_axial_projection,
)


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

def test_time_averaging_rejects_trailing_partial_block():
    with pytest.raises(ValueError, match="divide the number of frames exactly"):
        _nanopyx_drift(
            _movie(frames=14),
            reference="first",
            time_averaging=3,
            max_expected_drift=0,
            backend="threaded",
        )


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


def test_nanopyx_rejects_parameters_it_would_silently_change():
    with pytest.raises(ValueError, match="half the number"):
        _nanopyx_drift(
            _movie(frames=4),
            reference="first",
            time_averaging=3,
            max_expected_drift=0,
            backend="threaded",
        )
    with pytest.raises(ValueError, match="too large"):
        _nanopyx_drift(
            _movie(shape=(8, 8)),
            reference="first",
            time_averaging=1,
            max_expected_drift=4,
            backend="threaded",
        )


def test_selected_backend_error_is_not_swallowed(monkeypatch):
    class BrokenEstimator:
        def _run_threaded(self, *args, **kwargs):
            raise RuntimeError("backend failed")

    monkeypatch.setattr(
        "fast4dreg.estimation._load_nanopyx_estimator", lambda: BrokenEstimator()
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
