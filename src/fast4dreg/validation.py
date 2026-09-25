"""Registration-quality measurements used in the Fast4DReg paper.

The paper compared a selected Z slice (or a maximum projection) between the
first and subsequent frames, or between adjacent frames. Its archived notebook
affinely normalizes every image pair before calculating mSSIM, PSNR, Pearson's
correlation coefficient, and a value labelled NRMSE.

``paper_nrmse`` intentionally reproduces that notebook's historical formula,
``sqrt(mean(abs(reference - moving)))``. ``standard_nrmse`` is also reported
using the conventional Euclidean normalization so new analyses do not mistake
the historical value for the standard definition.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from skimage.metrics import (
    normalized_root_mse,
    peak_signal_noise_ratio,
    structural_similarity,
)

from .axes import to_ctzyx
from .io import prepare_output_path


def _index(value: object, *, name: str, size: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise TypeError(f"{name} must be an integer")
    index = int(value)
    if not 0 <= index < size:
        raise ValueError(f"{name}={index} is outside the available range 0..{size - 1}")
    return index


@dataclass(frozen=True)
class SimilarityMetrics:
    """Paper-compatible similarity measurements for one image pair."""

    mssim: float
    paper_nrmse: float
    standard_nrmse: float
    psnr: float
    pearson: float


@dataclass(frozen=True)
class FrameValidation:
    """Similarity measurements and indices for one time-frame comparison."""

    reference_index: int
    moving_index: int
    mssim: float
    paper_nrmse: float
    standard_nrmse: float
    psnr: float
    pearson: float


def _percentile_normalize(
    image: np.ndarray,
    *,
    pmin: float = 0.1,
    pmax: float = 99.9,
    eps: float = 1e-20,
) -> np.ndarray:
    """Match the percentile normalization in the archived paper notebook."""
    array = np.asarray(image, dtype=np.float32)
    low, high = np.percentile(array, (pmin, pmax))
    return (array - np.float32(low)) / np.float32(high - low + eps)


def _affine_min_mse_pair(
    moving: np.ndarray,
    reference: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Normalize a pair exactly as the paper's assessment notebook does.

    The notebook treats the moving image as ``gt``: it percentile-normalizes
    and mean-centres it, then mean-centres and scales the reference image to
    minimize their mean squared error.
    """
    moving_normalized = _percentile_normalize(moving)
    moving_centered = moving_normalized - np.mean(moving_normalized)
    if np.var(moving_centered.ravel()) <= 0:
        raise ValueError("similarity metrics require a non-constant moving image")
    reference_centered = np.asarray(reference, dtype=np.float32)
    reference_centered = reference_centered - np.mean(reference_centered)

    variance = np.var(reference_centered.ravel())
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError("similarity metrics require a non-constant reference image")

    covariance = np.cov(reference_centered.ravel(), moving_centered.ravel())[0, 1]
    return moving_centered, np.float32(covariance / variance) * reference_centered


def similarity_metrics(
    reference: np.ndarray,
    moving: np.ndarray,
) -> SimilarityMetrics:
    """Calculate the image-similarity metrics used for Fast4DReg validation.

    Both inputs must be matching 2D images. The returned ``paper_nrmse`` is
    retained for numerical comparison with the archived notebook; prefer
    ``standard_nrmse`` when reporting a conventional NRMSE in new work.
    """
    reference_array = np.asarray(reference)
    moving_array = np.asarray(moving)
    if reference_array.ndim != 2 or moving_array.ndim != 2:
        raise ValueError("similarity metrics require two 2D images")
    if reference_array.shape != moving_array.shape:
        raise ValueError(
            "reference and moving images must have matching shapes, got "
            f"{reference_array.shape} and {moving_array.shape}"
        )
    for name, array in (("reference", reference_array), ("moving", moving_array)):
        if not np.issubdtype(array.dtype, np.number) or np.issubdtype(
            array.dtype, np.complexfloating
        ):
            raise TypeError(f"{name} image must contain real numeric values")
    if not np.all(np.isfinite(reference_array)) or not np.all(
        np.isfinite(moving_array)
    ):
        raise ValueError("similarity metrics require finite image values")
    if min(reference_array.shape) < 11:
        raise ValueError(
            "paper-compatible Gaussian mSSIM requires both image dimensions "
            "to be at least 11 pixels"
        )

    moving_normalized, reference_scaled = _affine_min_mse_pair(
        moving_array, reference_array
    )
    difference = moving_normalized - reference_scaled

    mssim = structural_similarity(
        moving_normalized,
        reference_scaled,
        data_range=1.0,
        gaussian_weights=True,
        use_sample_covariance=False,
        sigma=1.5,
    )
    paper_nrmse = np.sqrt(np.mean(np.abs(difference)))
    standard_nrmse = normalized_root_mse(
        moving_normalized,
        reference_scaled,
        normalization="euclidean",
    )
    psnr = peak_signal_noise_ratio(
        moving_normalized,
        reference_scaled,
        data_range=1.0,
    )
    pearson = np.corrcoef(moving_normalized.ravel(), reference_scaled.ravel())[0, 1]

    return SimilarityMetrics(
        mssim=float(mssim),
        paper_nrmse=float(paper_nrmse),
        standard_nrmse=float(standard_nrmse),
        psnr=float(psnr),
        pearson=float(pearson),
    )


def _validation_movie(
    image: np.ndarray,
    *,
    axes: str,
    reference_channel: int,
    analysis: str,
    z_index: int | None,
) -> np.ndarray:
    canonical, original_axes = to_ctzyx(image, axes)
    if "T" not in original_axes or canonical.shape[1] < 2:
        raise ValueError("registration validation requires at least two timepoints")
    channel = _index(
        reference_channel,
        name="reference_channel",
        size=canonical.shape[0],
    )

    volumes = canonical[channel]
    if not isinstance(analysis, str):
        raise TypeError("analysis must be a string")
    analysis = analysis.lower().strip()
    if analysis == "slice":
        if z_index is None:
            z_index = volumes.shape[1] // 2
        selected_z = _index(z_index, name="z_index", size=volumes.shape[1])
        return volumes[:, selected_z]
    if z_index is not None:
        raise ValueError("z_index is only valid when analysis='slice'")
    if analysis == "max":
        return np.max(volumes, axis=1)
    if analysis in {"mean", "average"}:
        return np.mean(volumes, axis=1)
    raise ValueError("analysis must be 'slice', 'max', 'mean', or 'average'")


def evaluate_registration(
    image: np.ndarray,
    *,
    axes: str = "TZYX",
    reference: str = "first",
    reference_channel: int = 0,
    analysis: str = "slice",
    z_index: int | None = None,
) -> list[FrameValidation]:
    """Evaluate a registered time series using the paper's comparison modes.

    ``reference='first'`` compares the first frame with every later frame, as
    in the synthetic-data experiments. ``reference='previous'`` compares each
    adjacent pair, as in the acquired HUVEC experiment.
    """
    movie = _validation_movie(
        image,
        axes=axes,
        reference_channel=reference_channel,
        analysis=analysis,
        z_index=z_index,
    )
    if not isinstance(reference, str):
        raise TypeError("reference must be a string")
    reference = reference.lower().strip()
    if reference not in {"first", "previous"}:
        raise ValueError("reference must be 'first' or 'previous'")

    rows: list[FrameValidation] = []
    for moving_index in range(1, movie.shape[0]):
        reference_index = 0 if reference == "first" else moving_index - 1
        metrics = similarity_metrics(movie[reference_index], movie[moving_index])
        rows.append(
            FrameValidation(
                reference_index=reference_index,
                moving_index=moving_index,
                **asdict(metrics),
            )
        )
    return rows


def save_validation_csv(
    path: str | Path,
    rows: list[FrameValidation],
    *,
    overwrite: bool = False,
) -> None:
    """Write :func:`evaluate_registration` results to a CSV file."""
    import csv

    if not isinstance(rows, list) or not all(
        isinstance(row, FrameValidation) for row in rows
    ):
        raise TypeError("rows must be a list of FrameValidation objects")
    destination = prepare_output_path(path, overwrite=overwrite)
    fieldnames = [field.name for field in FrameValidation.__dataclass_fields__.values()]
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
