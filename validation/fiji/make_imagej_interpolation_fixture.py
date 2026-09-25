"""Create tests/data/imagej_interpolation/reference.npz with real ImageJ.

Requires Java and an ImageJ 1.x ``ij.jar``; ``ImageJReference.java`` in this
directory is compiled on the fly. The committed fixture records the ImageJ
version and lets normal CI check Fast4DRegPy's NumPy port without Java.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
TRANSLATIONS = [
    (0.37, -0.81),
    (-2.5, 1.25),
    (3.0, -2.0),
    (0.0, 0.6),
    (0.6, 0.0),
    (-0.999, 0.001),
    (11.3, 7.7),
    (-17.2, 0.4),
    (40.5, -3.3),
]
RESIZE_FACTORS = [2, 4, 5, 6]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ij_jar", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    rng = np.random.default_rng(20260925)
    plane = (rng.gamma(2.0, 300.0, size=(23, 31)) + 50).astype(np.float32)
    axial = (rng.gamma(2.0, 300.0, size=(9, 34)) + 50).astype(np.float32)
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        subprocess.run(
            [
                "javac",
                "-nowarn",
                "-cp",
                str(args.ij_jar),
                "-d",
                tmp,
                HERE / "java" / "ImageJReference.java",
            ],
            check=True,
        )
        classpath = f"{tmp}:{args.ij_jar}"

        def call(*arguments: object) -> None:
            subprocess.run(
                [
                    "java",
                    "-Djava.awt.headless=true",
                    "-cp",
                    classpath,
                    "ImageJReference",
                    *map(str, arguments),
                ],
                check=True,
            )

        (tmp / "plane.raw").write_bytes(plane.astype("<f4").tobytes())
        (tmp / "axial.raw").write_bytes(axial.astype("<f4").tobytes())
        translated = []
        for dx, dy in TRANSLATIONS:
            call("translate", tmp / "plane.raw", 31, 23, dx, dy, tmp / "out.raw")
            translated.append(
                np.frombuffer((tmp / "out.raw").read_bytes(), "<f4").reshape(23, 31)
            )
        resized = {}
        for factor in RESIZE_FACTORS:
            call("resize", tmp / "axial.raw", 34, 9, 9 * factor, tmp / "out.raw")
            resized[f"resized_x{factor}"] = np.frombuffer(
                (tmp / "out.raw").read_bytes(), "<f4"
            ).reshape(9 * factor, 34)
    np.savez_compressed(
        args.output,
        plane=plane,
        translations=np.asarray(TRANSLATIONS, dtype=np.float64),
        translated=np.stack(translated),
        axial=axial,
        imagej_jar_sha256=hashlib.sha256(args.ij_jar.read_bytes()).hexdigest(),
        **resized,
    )


if __name__ == "__main__":
    main()
