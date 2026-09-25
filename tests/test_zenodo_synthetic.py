"""Regression tests using pixels derived from the published Fast4DReg dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from fast4dreg import register_time

FIXTURE_DIR = Path(__file__).parent / "data" / "zenodo_synthetic"
FIXTURE = FIXTURE_DIR / "large_drift_xy_max.npz"
MANIFEST = FIXTURE_DIR / "manifest.json"


def _pearson(reference: np.ndarray, moving: np.ndarray) -> float:
    return float(np.corrcoef(reference.ravel(), moving.ravel())[0, 1])


def test_zenodo_fixture_checksum_and_provenance():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

    assert digest == manifest["fixture_sha256"]
    assert manifest["source_doi"] == "10.5281/zenodo.7514913"
    assert manifest["requested_archival_record"].endswith("/6534570")
    assert manifest["source_shape"] == [25, 69, 416, 416]
    assert manifest["source_axes"] == "TZYX"
    assert manifest["selected_time_indices"] == [0, 6, 12, 18, 24]


def test_published_large_drift_xy_is_recovered_and_corrected():
    with np.load(FIXTURE) as data:
        image = data["image"]
        time_indices = data["time_indices"].astype(np.int64)
        assert str(data["axes"]) == "TYX"

    corrected, shifts = register_time(
        image,
        axes="TYX",
        reference="first",
        correct_xy=True,
        correct_z=False,
        max_expected_drift=0,
        interpolation_order=3,
        workers=2,
    )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    published = np.asarray(
        manifest["selected_published_drift_xyz_pixels"], dtype=np.float32
    )
    assert published.shape == (len(time_indices), 3)

    # Fig. S1A reports the actual stochastic drift added to each archived frame.
    # Fast4DRegPy stores translations to apply relative to the first frame, so
    # subtract the first published drift and invert the XY signs.
    expected_dx = -(published[:, 0] - published[0, 0])
    expected_dy = -(published[:, 1] - published[0, 1])

    np.testing.assert_allclose(shifts[:, 0], 0, atol=0)
    np.testing.assert_allclose(shifts[:, 2], expected_dx, atol=1.5)
    np.testing.assert_allclose(shifts[:, 1], expected_dy, atol=1.5)

    # Ignore the border region affected by the largest synthetic translation.
    margin = 80
    reference = corrected[0, margin:-margin, margin:-margin]
    before = np.mean(
        [
            _pearson(reference, frame[margin:-margin, margin:-margin])
            for frame in image[1:]
        ]
    )
    after = np.mean(
        [
            _pearson(reference, frame[margin:-margin, margin:-margin])
            for frame in corrected[1:]
        ]
    )

    assert after > before
    assert after > 0.9
