import os

import numpy as np
import pytest
from scipy.ndimage import shift as ndi_shift

from fast4dreg import estimate_channel_shifts, register_time


@pytest.fixture(scope="session", autouse=True)
def _writable_nanopyx_runtime(tmp_path_factory):
    """Keep NanoPyx/Liquid Engine caches writable in restricted CI sandboxes."""
    runtime_dir = tmp_path_factory.mktemp("nanopyx-runtime")
    original_expanduser = os.path.expanduser

    def expanduser(path):
        if path == "~":
            return str(runtime_dir)
        return original_expanduser(path)

    os.path.expanduser = expanduser
    try:
        yield
    finally:
        os.path.expanduser = original_expanduser


def _asymmetric_volume(shape=(9, 48, 52)):
    z, y, x = np.indices(shape, dtype=np.float32)
    volume = np.zeros(shape, dtype=np.float32)
    for center, amplitude, sigma in [
        ((2.0, 13.0, 17.0), 1.0, 2.0),
        ((6.0, 31.0, 36.0), 0.7, 3.0),
        ((4.0, 20.0, 41.0), 0.5, 1.5),
    ]:
        distance = (z - center[0]) ** 2 + (y - center[1]) ** 2 + (x - center[2]) ** 2
        volume += amplitude * np.exp(-distance / (2 * sigma**2))
    return volume


@pytest.mark.integration
def test_nanopyx_import_is_required():
    import nanopyx
    from nanopyx.methods.drift_alignment.estimator import DriftEstimator

    assert nanopyx.__version__
    assert DriftEstimator is not None


@pytest.mark.integration
def test_registration_improves_alignment_for_known_xyz_shift():
    reference = _asymmetric_volume()
    moving = ndi_shift(reference, shift=(2, 3, -4), order=1)
    image = np.stack([reference, moving])

    corrected, shifts = register_time(
        image,
        axes="TZYX",
        projection="max",
        reference="first",
        correct_z=True,
        workers=2,
    )

    before = np.mean((image[0] - image[1]) ** 2)
    after = np.mean((corrected[0] - corrected[1]) ** 2)
    assert shifts.shape == (2, 3)
    np.testing.assert_allclose(shifts[1], [-2, -3, 4], atol=0.35)
    assert after < before * 0.4


@pytest.mark.integration
def test_channel_registration_uses_selected_reference_channel():
    reference = _asymmetric_volume()
    channel_zero = ndi_shift(reference, shift=(-1, 2, 3), order=1)
    image = np.stack([channel_zero, reference])

    shifts = estimate_channel_shifts(
        image,
        axes="CZYX",
        reference_channel=1,
        projection="max",
        correct_z=True,
        workers=2,
    )

    np.testing.assert_allclose(shifts[1], 0, atol=0.25)
    np.testing.assert_allclose(shifts[0], [1, -2, -3], atol=0.35)
