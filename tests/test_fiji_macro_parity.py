"""End-to-end parity with the original Fast4DReg Fiji macro.

``tests/data/fiji_macro/fiji_macro_reference.npz`` holds a small synthetic
TZYX movie together with the drift tables and corrected stacks written by the
unmodified ``time_estimate+apply.ijm`` (v2.1) running in ImageJ 1.53t with the
Fast4DReg/NanoJ Java plugin. Only the dialog parameters were replaced for
headless execution; see ``validation/fiji/``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fast4dreg import estimate_time_drift, register_time

FIXTURE = Path(__file__).parent / "data" / "fiji_macro" / "fiji_macro_reference.npz"
# NanoPyx and NanoJ locate the subpixel CCM maximum with different simplex
# optimizers on the same Catmull-Rom surface; measured agreement is <=0.004 px.
SHIFT_ATOL = 0.01
PROJECTIONS = {"Max Intensity": "max", "Average Intensity": "mean"}


@pytest.fixture(scope="module")
def fiji():
    with np.load(FIXTURE) as data:
        values = {key: data[key] for key in data.files}
    values["settings"] = json.loads(str(values["settings_json"]))
    return values


def _options(settings: dict) -> dict:
    # Fast4DRegPy currently shares one setting for XY and Z; the fixture cases
    # use identical XY and Z settings.
    assert settings["projection_type_xy"] == settings["projection_type_z"]
    assert settings["reference_xy"] == settings["reference_z"]
    assert settings["time_xy"] == settings["time_z"]
    assert settings["max_xy"] == settings["max_z"]
    return {
        "projection": PROJECTIONS[settings["projection_type_xy"]],
        "reference": "first"
        if settings["reference_xy"].startswith("first")
        else "previous",
        "axial_projection_axis": "Y" if settings["reslice_mode"] == "Top" else "X",
        "time_averaging": settings["time_xy"],
        "max_expected_drift": settings["max_xy"],
        "crop_output": settings["crop_output"],
    }


@pytest.mark.parametrize(
    "case",
    [
        "default",
        "previous_average",
        "left",
        "average_t3",
        "average_t5_partial",
        "crop_extend",
    ],
)
def test_estimated_xyz_drift_matches_fiji_macro(fiji, case):
    shifts = estimate_time_drift(
        fiji["raw"], axes="TZYX", correct_z=True, **_options(fiji["settings"][case])
    )
    np.testing.assert_allclose(
        shifts, fiji[f"{case}__fiji_dzdydx"], rtol=0, atol=SHIFT_ATOL
    )


def test_bounded_window_matches_fiji_when_drift_is_inside_bound(fiji):
    # r=6 contains every XY shift (<=2.8 px) with room to spare. Fiji's
    # centred 2r+1 window must give the same result as the unbounded search.
    shifts = estimate_time_drift(
        fiji["raw"], axes="TZYX", correct_z=False, max_expected_drift=6
    )
    np.testing.assert_allclose(
        shifts[:, 1:], fiji["bounded_r6__fiji_dzdydx"][:, 1:], rtol=0, atol=SHIFT_ATOL
    )
    np.testing.assert_allclose(
        shifts[:, 1:], fiji["default__fiji_dzdydx"][:, 1:], rtol=0, atol=SHIFT_ATOL
    )


@pytest.mark.parametrize("correct_z", [False, True])
def test_drift_at_the_bound_raises_instead_of_fiji_nan_or_clamping(fiji, correct_z):
    # Fiji writes NaN or values clamped to +/-(r-1) into its drift table when
    # the correlation peak is within one pixel of the bounded window (r=3 XY;
    # r=6 stretched axial pixels for Z). Fast4DRegPy refuses instead.
    radius = 3 if not correct_z else 6
    assert np.isnan(fiji["bounded_r3__fiji_dzdydx"]).any()
    with pytest.raises(ValueError, match="max_expected_drift"):
        estimate_time_drift(
            fiji["raw"],
            axes="TZYX",
            correct_xy=not correct_z,
            correct_z=correct_z,
            max_expected_drift=radius,
        )


@pytest.mark.parametrize("case", ["default", "left", "crop_extend"])
def test_corrected_stack_matches_fiji_macro_output(fiji, case):
    settings = fiji["settings"][case]
    corrected, _ = register_time(
        fiji["raw"],
        axes="TZYX",
        correct_z=True,
        extend_z=settings["extend_stack_to_fit"],
        **_options(settings),
    )
    expected = fiji[f"{case}__fiji_corrected"]
    assert corrected.shape == expected.shape
    for frame, reference in zip(corrected, expected, strict=True):
        assert np.corrcoef(frame.ravel(), reference.ravel())[0, 1] > 0.9999
    # Voxel values: remaining differences come from the <=0.004 px shift
    # differences above, not from interpolation or geometry.
    scale = float(expected.max())
    assert np.abs(corrected - expected).max() / scale < 0.01
