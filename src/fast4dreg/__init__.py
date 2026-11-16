"""Projection-based registration for multidimensional microscopy images."""

from .core import register_channels, register_time
from .estimation import (
    estimate_channel_shifts,
    estimate_time_drift,
)
from .io import load_drift_csv, load_tiff, save_drift_csv, save_tiff
from .transform import (
    apply_channel_shifts,
    apply_drift,
    fiji_crop_bounds,
    fiji_z_padding,
)
from .validation import (
    FrameValidation,
    SimilarityMetrics,
    evaluate_registration,
    save_validation_csv,
    similarity_metrics,
)
from .visualization import (
    line_intensity_profile,
    registration_kymograph,
    signal_to_background_ratio,
    temporal_color_overlay,
    temporal_standard_deviation,
)

__all__ = [
    "FrameValidation",
    "SimilarityMetrics",
    "apply_channel_shifts",
    "apply_drift",
    "estimate_channel_shifts",
    "estimate_time_drift",
    "evaluate_registration",
    "fiji_crop_bounds",
    "fiji_z_padding",
    "line_intensity_profile",
    "load_drift_csv",
    "load_tiff",
    "register_channels",
    "register_time",
    "registration_kymograph",
    "save_drift_csv",
    "save_tiff",
    "save_validation_csv",
    "signal_to_background_ratio",
    "similarity_metrics",
    "temporal_color_overlay",
    "temporal_standard_deviation",
]

def _installed_version() -> str:
    """The version of the installed distribution: ``fast4dregpy`` from PyPI, or
    ``fast4dreg`` as the LabConstrictor installer installs it from setup.py."""
    from importlib.metadata import PackageNotFoundError, version

    for distribution in ("fast4dregpy", "fast4dreg"):
        try:
            return version(distribution)
        except PackageNotFoundError:
            continue
    return "0+unknown"


__version__ = _installed_version()
