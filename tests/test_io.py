import numpy as np
import pytest

from fast4dreg.io import load_drift_csv, save_drift_csv, save_tiff


def test_drift_csv_round_trip(tmp_path):
    shifts = np.asarray([[0, 0, 0], [1.5, -2, 3.25]], dtype=np.float32)
    path = tmp_path / "drift.csv"
    save_drift_csv(path, shifts)
    np.testing.assert_allclose(load_drift_csv(path), shifts)


def test_saves_refuse_silent_overwrite(tmp_path):
    path = tmp_path / "drift.csv"
    shifts = np.zeros((1, 3), dtype=np.float32)
    save_drift_csv(path, shifts)
    with pytest.raises(FileExistsError, match="overwrite=True"):
        save_drift_csv(path, shifts)
    save_drift_csv(path, shifts, overwrite=True)


def test_load_drift_csv_rejects_nonsequential_indices(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("index,dz,dy,dx\n1,0,0,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sequential"):
        load_drift_csv(path)


def test_save_tiff_validates_axes(tmp_path):
    with pytest.raises(ValueError, match="entries"):
        save_tiff(tmp_path / "image.tif", np.zeros((2, 4, 5)), axes="YX")
