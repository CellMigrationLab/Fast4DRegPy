"""Run the original Fast4DReg Fiji macro on a small synthetic movie.

Creates ``tests/data/fiji_macro/fiji_macro_reference.npz``: a deterministic
synthetic TZYX movie, the Fiji drift tables for several macro settings, and
the Fiji-corrected stacks for the cases that exercise output geometry.

Requirements: Java, ``xvfb-run`` and an ImageJ directory containing ``ij.jar``
plus ``plugins/`` with the compiled Fast4DReg jar and its dependencies (see
``validation/fiji/README.md``). The macro itself is only patched for headless
parameters (``patch_macro.py``); all registration commands are original.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import tifffile
from scipy.ndimage import shift as ndi_shift

HERE = Path(__file__).parent
FIRST = "first frame (default, better for fixed)"
PREVIOUS = "previous frame (better for live)"
DEFAULT = {
    "exp_nro": 1,
    "XY_registration": True,
    "projection_type_xy": "Max Intensity",
    "time_xy": 1,
    "max_xy": 0,
    "reference_xy": FIRST,
    "crop_output": False,
    "z_registration": True,
    "projection_type_z": "Max Intensity",
    "reslice_mode": "Top",
    "time_z": 1,
    "max_z": 0,
    "reference_z": FIRST,
    "extend_stack_to_fit": False,
    "ram_conservative_mode": False,
}
CASES = {
    "default": ({}, True),
    "previous_average": (
        {
            "projection_type_xy": "Average Intensity",
            "projection_type_z": "Average Intensity",
            "reference_xy": PREVIOUS,
            "reference_z": PREVIOUS,
        },
        False,
    ),
    "bounded_r3": ({"max_xy": 3, "max_z": 3}, False),
    "bounded_r6": ({"max_xy": 6, "max_z": 6}, False),
    "average_t3": ({"time_xy": 3, "time_z": 3}, False),
    "average_t5_partial": ({"time_xy": 5, "time_z": 5}, False),
    "left": ({"reslice_mode": "Left"}, True),
    "crop_extend": ({"crop_output": True, "extend_stack_to_fit": True}, True),
}

# Displacement added to each frame, (dz, dy, dx). Values near +/-2.7 px probe
# the bounded search window with r=3.
DISPLACEMENT = np.asarray(
    [
        [0.0, 0.0, 0.0],
        [0.4, -0.6, 0.9],
        [0.9, -1.3, 1.6],
        [1.3, -1.9, 2.4],
        [1.8, -2.6, 2.7],
        [2.3, -2.7, 2.6],
        [2.6, -2.2, 1.9],
        [2.1, -1.1, 0.8],
        [1.4, 0.3, -0.7],
        [0.6, 1.4, -1.8],
        [-0.3, 2.6, -2.7],
        [-1.2, 2.7, -2.4],
    ],
    dtype=np.float64,
)


def synthetic_movie() -> np.ndarray:
    rng = np.random.default_rng(4012)
    shape = (12, 36, 44)
    z, y, x = np.indices(shape, dtype=np.float64)
    base = np.zeros(shape)
    for _ in range(45):
        center = rng.uniform([2, 4, 4], [shape[0] - 2, shape[1] - 4, shape[2] - 4])
        sigma = rng.uniform(1.1, 2.4, size=3)
        base += rng.uniform(300, 1500) * np.exp(
            -(
                ((z - center[0]) / sigma[0]) ** 2
                + ((y - center[1]) / sigma[1]) ** 2
                + ((x - center[2]) / sigma[2]) ** 2
            )
            / 2
        )
    frames = [ndi_shift(base, d, order=3, mode="constant") for d in DISPLACEMENT]
    return np.clip(np.stack(frames) + 100, 0, 65535).astype(np.uint16)


def read_njt(path: Path) -> dict[str, np.ndarray]:
    text = zipfile.ZipFile(path).read("data.txt").decode()
    table = {}
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        name, *values = line.split("\t")
        table[name] = np.asarray([float(v) for v in values], dtype=np.float64)
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("imagej_dir", type=Path)
    parser.add_argument("macro", type=Path, help="original time_estimate+apply.ijm")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    movie = synthetic_movie()
    result: dict[str, object] = {
        "raw": movie,
        "displacement_zyx": DISPLACEMENT,
        "macro_sha256": hashlib.sha256(args.macro.read_bytes()).hexdigest(),
        "imagej_jar_sha256": hashlib.sha256(
            (args.imagej_dir / "ij.jar").read_bytes()
        ).hexdigest(),
    }
    settings_record = {}
    with tempfile.TemporaryDirectory() as tmp_name:
        for case, (overrides, keep_output) in CASES.items():
            work = Path(tmp_name) / case
            work.mkdir()
            source = work / "synth.tif"
            tifffile.imwrite(
                source,
                movie,
                imagej=True,
                metadata={"axes": "TZYX", "spacing": 0.5, "unit": "um"},
                resolution=(10.0, 10.0),
            )
            settings = {**DEFAULT, **overrides, "files": str(source)}
            settings_record[case] = {**DEFAULT, **overrides}
            (work / "settings.json").write_text(json.dumps(settings))
            subprocess.run(
                [
                    HERE / "run_fiji_macro.sh",
                    args.imagej_dir,
                    args.macro,
                    work / "settings.json",
                    work / "run",
                    "300",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            (results,) = [
                p for p in work.iterdir() if p.is_dir() and p.name.startswith("synth_")
            ]
            xy = read_njt(next(results.glob("*_xy_DriftTable.njt")))
            z = read_njt(next(results.glob("*_z_DriftTable.njt")))
            result[f"{case}__fiji_dzdydx"] = np.column_stack(
                [z["Y-Drift (pixels)"], xy["Y-Drift (pixels)"], xy["X-Drift (pixels)"]]
            )
            if keep_output:
                corrected = tifffile.imread(next(results.glob("*_xyzCorrected.tif")))
                result[f"{case}__fiji_corrected"] = corrected.astype(np.float32)
            shutil.rmtree(work)
    result["settings_json"] = json.dumps(settings_record, sort_keys=True)
    np.savez_compressed(args.output, **result)


if __name__ == "__main__":
    main()
