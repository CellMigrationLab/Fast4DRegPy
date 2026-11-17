"""The napari / Fiji tools (src/fast4dreg_lc_tools): axes, sign and table layout.

The tools only pass the image and the settings to the public API, so these tests
check what the bridge adds: the axes a host sends, the drift table and the clear
refusals. The fixtures of lc_tests/ are cut out of one scene at known integer
offsets (Y and X sizes differ), so an axis swap or a sign error shows as a
drift of at least 1 pixel. Precision is checked against Fiji elsewhere.

They need labconstrictor-tools, which the app installer installs; the tests
workflow installs the version the installer pins.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import tifffile

pytest.importorskip(
    "labconstrictor_tools", reason="labconstrictor-tools is not installed"
)
from labconstrictor_tools import ToolError

import fast4dreg_lc_tools as tools

LC_TESTS = Path(__file__).resolve().parents[1] / "lc_tests"
sys.path.insert(0, str(LC_TESTS))
import make_fixtures  # noqa: E402

TOLERANCE_PX = 0.4  # the shifts are whole pixels, at least 1 apart


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    folder = tmp_path_factory.mktemp("lc_fixtures")
    make_fixtures.write(folder)
    return folder


def image_of(result):
    """The array of an image result (returned with its axes when Tools has WithAxes)."""
    return getattr(result, "array", result)


def table_shifts(table, index_name):
    assert list(table) == [index_name, "dz", "dy", "dx"]
    assert table[index_name] == list(range(len(table["dz"])))
    return np.column_stack([table["dz"], table["dy"], table["dx"]])


@pytest.mark.parametrize(
    ("name", "axes", "correct_z"),
    [("drift_tyx.tif", "TYX", False), ("drift_tzyx.tif", "TZYX", True)],
)
def test_correct_drift_finds_the_known_drift(fixtures, name, axes, correct_z):
    image = tifffile.imread(fixtures / name)
    corrected, table = tools.correct_drift(image, axes=axes, correct_z=correct_z)
    corrected = image_of(corrected)
    assert corrected.shape == image.shape
    assert corrected.dtype == np.float32
    shifts = table_shifts(table, "timepoint")
    np.testing.assert_allclose(shifts, make_fixtures.KNOWN[name], atol=TOLERANCE_PX)


@pytest.mark.parametrize(
    ("name", "axes", "correct_z"),
    [("channels_cyx.tif", "CYX", False), ("channels_zcyx.tif", "ZCYX", True)],
)
def test_align_channels_finds_the_known_shifts(fixtures, name, axes, correct_z):
    image = tifffile.imread(fixtures / name)
    aligned, table = tools.align_channels(image, axes=axes, correct_z=correct_z)
    aligned = image_of(aligned)
    assert aligned.shape == image.shape
    shifts = table_shifts(table, "channel")
    np.testing.assert_allclose(shifts, make_fixtures.KNOWN[name], atol=TOLERANCE_PX)


def test_lower_case_axes_are_accepted(fixtures):
    image = tifffile.imread(fixtures / "drift_tyx.tif")
    _, table = tools.correct_drift(image, axes="tyx")
    shifts = table_shifts(table, "timepoint")
    np.testing.assert_allclose(
        shifts, make_fixtures.KNOWN["drift_tyx.tif"], atol=TOLERANCE_PX
    )


@pytest.mark.parametrize(
    ("tool", "name", "axes", "settings", "words"),
    [
        (tools.correct_drift, "drift_tzyx.tif", "TYX", {}, "(4, 20, 64, 72)"),
        (tools.correct_drift, "drift_tyx.tif", "TYQ", {}, "unsupported axes"),
        (tools.correct_drift, "drift_tyx.tif", "TYX", {"correct_z": True}, "Z axis"),
        (tools.correct_drift, "channels_cyx.tif", "CYX", {}, "T axis"),
        (tools.align_channels, "drift_tyx.tif", "TYX", {}, "C axis"),
        (
            tools.align_channels,
            "channels_cyx.tif",
            "CYX",
            {"correct_z": True},
            "Z axis",
        ),
    ],
)
def test_axes_that_do_not_fit_are_refused(fixtures, tool, name, axes, settings, words):
    image = tifffile.imread(fixtures / name)
    with pytest.raises(ToolError) as caught:
        tool(image, axes=axes, **settings)
    assert caught.value.code == "bad_axes"
    assert words in str(caught.value)


def test_a_setting_fast4dregpy_refuses_is_a_tool_error(fixtures):
    image = tifffile.imread(fixtures / "channels_cyx.tif")
    with pytest.raises(ToolError) as caught:
        tools.align_channels(image, axes="CYX", reference_channel=5)
    assert caught.value.code == "invalid_settings"


@pytest.mark.parametrize(
    ("tool", "name", "axes"),
    [
        (tools.correct_drift, "drift_tzyx.tif", "TZYX"),
        (tools.align_channels, "channels_zcyx.tif", "ZCYX"),
    ],
)
def test_the_image_result_carries_the_input_axes(fixtures, tool, name, axes):
    """With Tools 0.3.0a4 or later, Fiji opens the result as a hyperstack: the tool
    returns it with the axes the person gave (normalised), in the same order."""
    import labconstrictor_tools

    if not hasattr(labconstrictor_tools, "WithAxes"):
        pytest.skip("labconstrictor-tools before 0.3.0a4 has no WithAxes")
    image = tifffile.imread(fixtures / name)
    result, _ = tool(image, axes=axes.lower())
    assert isinstance(result, labconstrictor_tools.WithAxes)
    assert result.axes == axes
    assert result.array.shape == image.shape
