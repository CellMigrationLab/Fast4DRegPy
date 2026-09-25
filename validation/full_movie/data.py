"""Pinned Fast4DReg validation dataset loading and provenance."""

from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile

REPOSITORY = Path(__file__).resolve().parents[2]
ZENODO_RECORD = "7514913"
ARCHIVE = "2-Synthetic-drift-dataset.zip"
ARCHIVE_MD5 = "27e3623f58d23d7c50674edc9432fe1b"
RAW_MEMBER = (
    "2-Synthetic-drift-dataset/2.1-Synthetic-drift-files/2.1.2-LargeDrift_original.tif"
)
FIJI_MEMBER = (
    "2-Synthetic-drift-dataset/2.2-Synthetic-drift-expected-results/"
    "2.2.1-LargeDrift_F4DReg.tif"
)


@dataclass
class Movie:
    raw: np.ndarray
    fiji: np.ndarray
    metadata: dict


def _digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch_archive(data_dir: Path, *, download: bool) -> Path:
    """Return the pinned archive and reject any checksum mismatch."""
    archive = data_dir / ARCHIVE
    if not archive.exists():
        if not download:
            raise FileNotFoundError(
                f"{archive} not found. Pass --download to fetch it from Zenodo "
                f"record {ZENODO_RECORD}, or place the verified archive there."
            )
        with urllib.request.urlopen(
            f"https://zenodo.org/api/records/{ZENODO_RECORD}", timeout=60
        ) as response:
            record = json.load(response)
        entries = [entry for entry in record["files"] if entry["key"] == ARCHIVE]
        if len(entries) != 1:
            raise RuntimeError(f"{ARCHIVE} is not in Zenodo record {ZENODO_RECORD}")
        entry = entries[0]
        if entry["checksum"] != f"md5:{ARCHIVE_MD5}":
            raise RuntimeError(
                f"Zenodo reports checksum {entry['checksum']} for {ARCHIVE}; "
                f"expected md5:{ARCHIVE_MD5}. Refusing a different dataset version."
            )
        partial = archive.with_suffix(".partial")
        print(f"downloading {entry['links']['self']} ({entry['size']} B)")
        urllib.request.urlretrieve(entry["links"]["self"], partial)
        partial.rename(archive)

    checksum = _digest(archive, "md5")
    if checksum != ARCHIVE_MD5:
        raise RuntimeError(
            f"{archive} has MD5 {checksum}, expected {ARCHIVE_MD5}; delete it and "
            "download again. No other dataset version is accepted."
        )
    return archive


def extract(archive: Path, data_dir: Path) -> tuple[Path, Path, list[str]]:
    """Extract the pinned raw and Fiji TIFFs, checking member names and sizes."""
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        for member in (RAW_MEMBER, FIJI_MEMBER):
            if member not in names:
                raise RuntimeError(f"{member} missing from {archive}")
            target = data_dir / member
            expected_size = bundle.getinfo(member).file_size
            if not target.exists() or target.stat().st_size != expected_size:
                target.parent.mkdir(parents=True, exist_ok=True)
                bundle.extract(member, data_dir)
    return data_dir / RAW_MEMBER, data_dir / FIJI_MEMBER, names


def tiff_metadata(path: Path) -> dict:
    with tifffile.TiffFile(path) as tif:
        series = tif.series[0]
        page = tif.pages[0]
        info = {
            "shape": list(series.shape),
            "axes": series.axes,
            "dtype": str(series.dtype),
            "imagej_metadata": {
                key: value
                for key, value in (tif.imagej_metadata or {}).items()
                if key != "Info"
            },
        }
        for key, tag_name in (
            ("x_pixels_per_unit", "XResolution"),
            ("y_pixels_per_unit", "YResolution"),
        ):
            tag = page.tags.get(tag_name)
            if tag is not None:
                numerator, denominator = tag.value
                info[key] = numerator / denominator
        return info


def load(data_dir: Path, *, download: bool) -> Movie:
    archive = fetch_archive(data_dir, download=download)
    raw_path, fiji_path, names = extract(archive, data_dir)
    metadata = {
        "zenodo_record": ZENODO_RECORD,
        "archive": ARCHIVE,
        "archive_md5": ARCHIVE_MD5,
        "raw_member": RAW_MEMBER,
        "raw_sha256": _digest(raw_path, "sha256"),
        "fiji_member": FIJI_MEMBER,
        "fiji_sha256": _digest(fiji_path, "sha256"),
        "raw_metadata": tiff_metadata(raw_path),
        "fiji_metadata": tiff_metadata(fiji_path),
        "expected_results_members": [
            name for name in names if "2.2-Synthetic-drift-expected-results" in name
        ],
        "possible_settings_or_tables": [
            name
            for name in names
            if name.lower().endswith((".csv", ".njt", ".txt", ".xlsx"))
        ],
    }
    return Movie(
        raw=tifffile.imread(raw_path),
        fiji=tifffile.imread(fiji_path),
        metadata=metadata,
    )


def self_test_movie() -> Movie:
    fixture = REPOSITORY / "tests" / "data" / "fiji_macro" / "fiji_macro_reference.npz"
    with np.load(fixture) as data:
        raw = data["raw"]
        fiji = np.clip(np.floor(data["default__fiji_corrected"] + 0.5), 0, 65535)
    return Movie(
        raw=raw,
        fiji=fiji.astype(np.uint16),
        metadata={
            "SELF_TEST": f"{fixture.name}: synthetic movie, real Fiji macro output"
        },
    )
