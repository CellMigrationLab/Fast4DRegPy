"""Write the small images the tool cases use, each with a known drift.

    python make_fixtures.py fixtures

Every image is cut out of one larger random scene (smoothed noise plus a few
bright, asymmetric spots, fixed seed), each frame or channel at a known integer
offset, so the translation that corrects it is known exactly. Y and X sizes
differ, so a swap of the axes shows. KNOWN lists the translation (dz, dy, dx)
that brings each frame or channel back onto the first or reference one, the
same quantity as Fast4DRegPy's drift table.
"""

import sys
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

# Offsets of the cut-outs in the scene, (z, y, x) per frame or channel.
TIME_OFFSETS = [(0, 0, 0), (0, 2, -3), (0, 5, -1), (0, 3, 4), (0, -2, 6)]
TIME_Z_OFFSETS = [(0, 0, 0), (1, 2, -1), (2, 3, 1), (1, -1, 3)]
CHANNEL_OFFSETS = [(0, 0, 0), (0, 3, -2), (0, -2, 4)]
CHANNEL_Z_OFFSETS = [(0, 0, 0), (2, 2, -3)]

# The translation applied to frame t: its offset minus the offset of frame 0.
KNOWN = {
    "drift_tyx.tif": [(0, y, x) for _, y, x in TIME_OFFSETS],
    "drift_tzyx.tif": list(TIME_Z_OFFSETS),
    "channels_cyx.tif": [(0, y, x) for _, y, x in CHANNEL_OFFSETS],
    "channels_zcyx.tif": list(CHANNEL_Z_OFFSETS),
}


def scene(shape: tuple[int, ...], seed: int) -> np.ndarray:
    """Smoothed noise with a few bright spots of different sizes, as uint16."""
    rng = np.random.default_rng(seed)
    image = ndimage.gaussian_filter(rng.random(shape), 2.0)
    spots = np.zeros(shape)
    for _ in range(12):
        spots[tuple(rng.integers(4, s - 4) for s in shape)] = rng.uniform(5, 20)
    image += ndimage.gaussian_filter(spots, 1.5)
    image -= image.min()
    return (image / image.max() * 4000 + 100).astype(np.uint16)


def cut(volume: np.ndarray, offset: tuple[int, int, int], size: tuple[int, int, int]):
    """The block of `size` that starts `offset` away from the centre region."""
    margin = 8
    z0, y0, x0 = (margin + o for o in offset)
    return volume[z0 : z0 + size[0], y0 : y0 + size[1], x0 : x0 + size[2]]


def write(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    flat = scene((20, 112, 128), seed=1)
    frames = [cut(flat, o, (1, 80, 96))[0] for o in TIME_OFFSETS]
    tifffile.imwrite(
        folder / "drift_tyx.tif",
        np.stack(frames),
        imagej=True,
        metadata={"axes": "TYX"},
    )

    volume = scene((38, 96, 104), seed=2)  # 20 slices: Z is underestimated on ~10
    frames = [cut(volume, o, (20, 64, 72)) for o in TIME_Z_OFFSETS]
    tifffile.imwrite(
        folder / "drift_tzyx.tif",
        np.stack(frames),
        imagej=True,
        metadata={"axes": "TZYX"},
    )

    channels = [cut(flat, o, (1, 80, 96))[0] for o in CHANNEL_OFFSETS]
    tifffile.imwrite(
        folder / "channels_cyx.tif",
        np.stack(channels),
        imagej=True,
        metadata={"axes": "CYX"},
    )

    channels = [cut(volume, o, (20, 64, 72)) for o in CHANNEL_Z_OFFSETS]
    zcyx = np.stack(channels, axis=1)  # Z C Y X, the order Fiji saves a composite
    tifffile.imwrite(
        folder / "channels_zcyx.tif", zcyx, imagej=True, metadata={"axes": "ZCYX"}
    )


if __name__ == "__main__":
    write(Path(sys.argv[1] if len(sys.argv) > 1 else "fixtures"))
