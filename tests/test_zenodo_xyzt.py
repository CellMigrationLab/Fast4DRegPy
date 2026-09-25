"""XYZ parity tests using the archived Fast4DReg Fiji reference output."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from fast4dreg import register_time

FIXTURE_DIR = Path(__file__).parent / "data" / "zenodo_xyzt"
FIXTURE = FIXTURE_DIR / "large_drift_xyzt_fiji_reference.npz"
MANIFEST = FIXTURE_DIR / "manifest.json"


def _pearson(reference: np.ndarray, moving: np.ndarray) -> float:
    return float(np.corrcoef(reference.ravel(), moving.ravel())[0, 1])


def test_xyzt_fixture_checksum_and_provenance():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    digest = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()

    assert digest == manifest["fixture_sha256"]
    assert manifest["source_doi"] == "10.5281/zenodo.7514913"
    assert manifest["requested_archival_record"].endswith("/6534570")
    assert manifest["source_axes"] == "TZYX"
    assert manifest["fiji_axes"] == "TZYX"
    assert manifest["selected_time_indices"] == [0, 6]
    assert manifest["license"] == "CC BY 4.0"
    assert manifest["frame0_match_score"] > 0.999


def test_xyzt_registration_matches_published_xyz_and_fiji_reference():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with np.load(FIXTURE) as data:
        image = data["image"]
        fiji_corrected = data["fiji_corrected"]
        axes = str(data["axes"])
        margin = int(data["comparison_margin"])

    corrected, shifts = register_time(
        image,
        axes=axes,
        reference="first",
        projection="max",
        correct_xy=True,
        correct_z=True,
        max_expected_drift=0,
        workers=2,
    )

    published = np.asarray(
        manifest["selected_published_drift_xyz_pixels"], dtype=np.float32
    )
    # Published drift is stored as (x,y,z) displacement added to the source.
    # Fast4DRegPy reports (dz,dy,dx) translations to apply relative to frame 0.
    relative = published - published[0]
    expected = np.column_stack((-relative[:, 2], -relative[:, 1], -relative[:, 0]))

    np.testing.assert_allclose(shifts, expected, atol=0.75)

    # The raw fixture has an XY safety margin around the region corresponding
    # to the archived Fiji overlap crop. Remove that margin after registration.
    ours = corrected[:, :, margin:-margin, margin:-margin]
    assert ours.shape == fiji_corrected.shape

    # Frame 0 validates the geometric mapping between the raw and Fiji crops.
    assert _pearson(ours[0], fiji_corrected[0]) > 0.999

    # Frame 6 is the actual end-to-end XYZ parity check.
    before = _pearson(
        image[1, :, margin:-margin, margin:-margin],
        fiji_corrected[1],
    )
    after = _pearson(ours[1], fiji_corrected[1])

    assert after > before
    assert after > 0.98
