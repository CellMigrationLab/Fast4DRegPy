import csv

import numpy as np
import pytest

from fast4dreg import (
    evaluate_registration,
    line_intensity_profile,
    registration_kymograph,
    save_validation_csv,
    signal_to_background_ratio,
    similarity_metrics,
    temporal_color_overlay,
    temporal_standard_deviation,
)


def _image(shape=(24, 28)):
    y, x = np.indices(shape, dtype=np.float32)
    return np.exp(-((y - 8) ** 2 + (x - 9) ** 2) / 12) + 0.6 * np.exp(
        -((y - 17) ** 2 + (x - 20) ** 2) / 8
    )


def test_similarity_metrics_are_perfect_for_affine_intensity_change():
    reference = _image()
    moving = reference * 4.0 + 17.0

    metrics = similarity_metrics(reference, moving)

    assert metrics.mssim == pytest.approx(1.0, abs=1e-5)
    # The archived notebook mixes sample covariance with population variance,
    # leaving a small residual even for an affine-equivalent pair.
    assert metrics.paper_nrmse < 0.02
    assert metrics.standard_nrmse < 0.002
    assert metrics.pearson == pytest.approx(1.0, abs=1e-6)
    assert metrics.psnr > 70


def test_paper_nrmse_reproduces_archived_notebook_formula():
    reference = _image()
    moving = np.roll(reference, 2, axis=1)
    metrics = similarity_metrics(reference, moving)

    # The archived notebook computes sqrt(mean(abs(error))), not conventional
    # normalized RMSE. Keeping both values prevents accidental relabelling.
    assert metrics.paper_nrmse > 0
    assert metrics.paper_nrmse != pytest.approx(metrics.standard_nrmse)


def test_evaluate_registration_supports_first_and_previous_modes():
    base = _image()
    movie = np.stack([base, base * 2 + 3, base * 3 + 7])

    first = evaluate_registration(movie, axes="TYX", reference="first")
    previous = evaluate_registration(movie, axes="TYX", reference="previous")

    assert [(row.reference_index, row.moving_index) for row in first] == [
        (0, 1),
        (0, 2),
    ]
    assert [(row.reference_index, row.moving_index) for row in previous] == [
        (0, 1),
        (1, 2),
    ]
    assert all(row.mssim == pytest.approx(1.0, abs=1e-5) for row in first)


def test_evaluate_registration_uses_selected_slice_or_projection():
    base = _image()
    image = np.stack(
        [
            np.stack([base, base * 2]),
            np.stack([base * 3 + 1, base * 6 + 1]),
        ]
    )

    slice_rows = evaluate_registration(image, axes="TZYX", z_index=1)
    max_rows = evaluate_registration(image, axes="TZYX", analysis="max")

    assert slice_rows[0].mssim == pytest.approx(1.0, abs=1e-5)
    assert max_rows[0].mssim == pytest.approx(1.0, abs=1e-5)


def test_temporal_standard_deviation_matches_imagej_sample_std():
    movie = np.stack(
        [np.zeros((2, 12, 14)), np.full((2, 12, 14), 2.0)],
        dtype=np.float32,
    )

    projection = temporal_standard_deviation(movie, axes="TZYX")
    selected = temporal_standard_deviation(movie, axes="TZYX", z_index=1)

    expected = np.sqrt(2.0)
    assert projection.shape == (2, 12, 14)
    np.testing.assert_allclose(projection, expected)
    np.testing.assert_allclose(selected, expected)


def test_temporal_overlay_profile_and_kymograph_shapes():
    base = _image()
    movie = np.stack([np.roll(base, index, axis=1) for index in range(3)])

    overlay = temporal_color_overlay(movie, axes="TYX")
    profile = line_intensity_profile(base, (2, 3), (18, 22))
    kymograph = registration_kymograph(movie, (2, 3), (18, 22), axes="TYX")

    assert overlay.shape == (*base.shape, 3)
    assert overlay.dtype == np.float32
    assert profile.ndim == 1
    assert kymograph.shape == (3, profile.size)


def test_signal_to_background_ratio_uses_paper_definition():
    image = np.asarray([[2, 2, 10, 10]], dtype=np.float32)
    signal = np.asarray([[False, False, True, True]])
    background = ~signal

    assert signal_to_background_ratio(image, signal, background) == pytest.approx(5)


def test_save_validation_csv(tmp_path):
    movie = np.stack([_image(), _image() * 2 + 1])
    rows = evaluate_registration(movie, axes="TYX")
    path = tmp_path / "validation.csv"

    save_validation_csv(path, rows)

    with path.open(newline="", encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    assert len(saved) == 1
    assert saved[0]["reference_index"] == "0"
    assert saved[0]["moving_index"] == "1"
    assert set(saved[0]) == {
        "reference_index",
        "moving_index",
        "mssim",
        "paper_nrmse",
        "standard_nrmse",
        "psnr",
        "pearson",
    }


def test_validation_helpers_reject_ambiguous_inputs(tmp_path):
    base = _image()
    movie = np.stack([base, base, base])
    with pytest.raises(ValueError, match="intensity variation"):
        temporal_color_overlay(np.ones_like(movie), axes="TYX")
    with pytest.raises(ValueError, match="outside image"):
        line_intensity_profile(base, (-1, 0), (4, 4))
    with pytest.raises(TypeError, match="boolean"):
        signal_to_background_ratio(base, np.ones_like(base), np.zeros_like(base))
    with pytest.raises(TypeError, match="reference_channel"):
        evaluate_registration(movie, axes="TYX", reference_channel=0.0)
    with pytest.raises(TypeError, match="z_index"):
        evaluate_registration(movie[:, None], axes="TZYX", z_index=0.0)

    path = tmp_path / "validation.csv"
    rows = evaluate_registration(movie, axes="TYX")
    save_validation_csv(path, rows)
    with pytest.raises(FileExistsError, match="overwrite=True"):
        save_validation_csv(path, rows)
