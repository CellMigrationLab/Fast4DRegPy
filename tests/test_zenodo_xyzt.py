"""XYZ parity tests using the archived Fast4DReg Fiji reference output."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from fast4dreg import apply_drift, estimate_time_drift

FIXTURE_DIR = Path(__file__).parent / "data" / "zenodo_xyzt"
FIXTURE = FIXTURE_DIR / "large_drift_xyzt_fiji_reference.npz"
MANIFEST = FIXTURE_DIR / "manifest.json"
XY_FIXTURE = (
    Path(__file__).parent / "data" / "zenodo_synthetic" / "large_drift_xy_max.npz"
)


def _pearson(reference: np.ndarray, moving: np.ndarray) -> float:
    return float(np.corrcoef(reference.ravel(), moving.ravel())[0, 1])


def _load():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with np.load(FIXTURE) as data:
        image = data["image"]
        fiji = data["fiji_corrected"]
        margin_y = int(data["comparison_y_margin"])
        x_start = int(data["comparison_x_start"])
    return manifest, image, fiji, margin_y, x_start


def _to_fiji_region(volume, margin_y, x_start, fiji):
    return volume[..., margin_y:-margin_y, x_start : x_start + fiji.shape[-1]]


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
    assert manifest["axial_projection_full_lateral_width"] == 416


def test_archived_fiji_frame_is_reproduced_voxel_for_voxel():
    # The archived Fiji frame 6 is reproduced by the Fiji two-pass ImageJ
    # bicubic transform of the raw frame with the translation recovered from
    # the archive (manifest), followed by one conversion to uint16. This pins
    # down Fiji's interpolation, border handling and 32-bit ("Save RAM" off)
    # arithmetic independently of drift estimation.
    manifest, image, fiji, margin_y, x_start = _load()
    translation = np.asarray(manifest["fiji_frame6_translation_dzdydx"], np.float32)

    corrected = apply_drift(image, [[0, 0, 0], translation], axes="TZYX")
    ours = np.clip(
        np.floor(_to_fiji_region(corrected, margin_y, x_start, fiji) + 0.5), 0, 65535
    )

    np.testing.assert_array_equal(ours[0], fiji[0])
    difference = np.abs(ours[1] - fiji[1].astype(np.float64))
    assert difference.max() <= 1
    assert np.mean(difference == 0) > 0.9999


def test_xyzt_drift_matches_fiji_and_published_ground_truth():
    manifest, image, fiji, margin_y, x_start = _load()
    fiji_translation = np.asarray(manifest["fiji_frame6_translation_dzdydx"])
    published = np.asarray(manifest["selected_published_drift_xyz_pixels"])
    # The generator leaves frame 0 untouched and adds published[t] (x,y,z) to
    # frame t, so the translation to apply to frame 6 is -published[6].
    truth = -published[1, ::-1]

    # Fiji estimates XY from the full-field max-Z projection; the XY fixture
    # is exactly that projection (this XYZT fixture is cropped in Y).
    with np.load(XY_FIXTURE) as data:
        xy_movie = data["image"][:2]
    xy = estimate_time_drift(xy_movie, axes="TYX")[1]
    # Measured: 0.0013 px from Fiji, 0.054 px from the published drift.
    np.testing.assert_allclose(xy[1:], fiji_translation[1:], atol=0.005)
    np.testing.assert_allclose(xy[1:], truth[1:], atol=0.1)

    xy_corrected = apply_drift(image, [[0, 0, 0], [0, xy[1], xy[2]]], axes="TZYX")
    dz = estimate_time_drift(
        xy_corrected, axes="TZYX", correct_xy=False, correct_z=True
    )[1, 0]
    # Measured: 0.005 px from Fiji although the axial projection here only
    # spans the fixture's 192 Y rows instead of Fiji's full field.
    assert abs(dz - fiji_translation[0]) < 0.02
    assert abs(dz - truth[0]) < 0.1

    corrected = apply_drift(image, [[0, 0, 0], [dz, xy[1], xy[2]]], axes="TZYX")
    ours = _to_fiji_region(corrected, margin_y, x_start, fiji)
    assert _pearson(ours[0], fiji[0]) > 0.999999
    before = _pearson(_to_fiji_region(image, margin_y, x_start, fiji)[1], fiji[1])
    after = _pearson(ours[1], fiji[1])
    assert after > before
    # Measured: 0.9999989.
    assert after > 0.99999
