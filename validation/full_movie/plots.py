"""Diagnostic figures for the full-movie validation (PNG audit artifacts)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
OURS = "#2a78d6"  # categorical slot 1
FIJI = "#eb6834"  # categorical slot 2
TRUTH = "#52514e"  # neutral reference line
# Diverging blue <-> red with a neutral gray midpoint.
DIVERGING = LinearSegmentedColormap.from_list(
    "f4d_diverging", ["#1f5fb4", "#8fb7ea", "#f0efec", "#f0a3a2", "#b8302f"]
)
AXES = ("dz", "dy", "dx")


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def trajectories(path: Path, ours, truth, fiji) -> None:
    frames = np.arange(ours.shape[0])
    fig, axes = plt.subplots(2, 3, figsize=(12, 6), facecolor=SURFACE, sharex=True)
    for axis, name in enumerate(AXES):
        top, bottom = axes[0, axis], axes[1, axis]
        for ax in (top, bottom):
            _style(ax)
        top.plot(frames, truth[:, axis], color=TRUTH, lw=2, label="ground truth")
        top.plot(
            frames, fiji[:, axis], color=FIJI, lw=2, ls="--", label="Fiji (recovered)"
        )
        top.plot(
            frames,
            ours[:, axis],
            color=OURS,
            lw=2,
            marker="o",
            ms=4,
            label="Fast4DRegPy",
        )
        top.set_title(
            f"{name}: translation to apply (px)", color=INK, fontsize=10, loc="left"
        )
        bottom.axhline(0, color=INK_2, lw=0.8)
        bottom.plot(
            frames,
            ours[:, axis] - truth[:, axis],
            color=OURS,
            lw=2,
            marker="o",
            ms=4,
            label="Fast4DRegPy - truth",
        )
        bottom.plot(
            frames,
            fiji[:, axis] - truth[:, axis],
            color=FIJI,
            lw=2,
            ls="--",
            label="Fiji - truth",
        )
        bottom.set_title(f"{name}: error (px)", color=INK, fontsize=10, loc="left")
        bottom.set_xlabel("frame", color=INK_2, fontsize=9)
    axes[0, 0].legend(frameon=False, fontsize=8, labelcolor=INK)
    axes[1, 0].legend(frameon=False, fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def metric_series(path: Path, rows: list[dict]) -> None:
    frames = [r["frame"] for r in rows]
    panels = [
        ("volume_pearson", "Pearson vs Fiji (3D volume)"),
        ("maxz_ssim", "SSIM vs Fiji (max-Z projection)"),
        ("volume_nrmse_range", "NRMSE vs Fiji (3D, /range)"),
        ("identical_voxel_fraction_uint16", "identical voxels after uint16 rounding"),
    ]
    fig, axes = plt.subplots(1, 5, figsize=(17, 3.4), facecolor=SURFACE)
    for ax, (key, title) in zip(axes[:4], panels, strict=True):
        _style(ax)
        ax.plot(frames, [r[key] for r in rows], color=OURS, lw=2, marker="o", ms=4)
        ax.set_title(title, color=INK, fontsize=9, loc="left")
        ax.set_xlabel("frame", color=INK_2, fontsize=8)
        ax.ticklabel_format(axis="y", useOffset=False)
    ax = axes[4]
    _style(ax)
    ax.plot(
        frames,
        [r["raw_vs_frame0_pearson"] for r in rows],
        color=TRUTH,
        lw=2,
        label="raw",
    )
    ax.plot(
        frames,
        [r["fiji_vs_frame0_pearson"] for r in rows],
        color=FIJI,
        lw=2,
        ls="--",
        label="Fiji",
    )
    ax.plot(
        frames,
        [r["ours_vs_frame0_pearson"] for r in rows],
        color=OURS,
        lw=2,
        marker="o",
        ms=4,
        label="Fast4DRegPy",
    )
    ax.set_title("Pearson vs own frame 0", color=INK, fontsize=9, loc="left")
    ax.set_xlabel("frame", color=INK_2, fontsize=8)
    ax.legend(frameon=False, fontsize=8, labelcolor=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def _panel(ax, image, title, *, cmap="gray", vmin=None, vmax=None):
    handle = ax.imshow(
        image, cmap=cmap, vmin=vmin, vmax=vmax, interpolation="nearest", aspect="auto"
    )
    ax.set_title(title, color=INK, fontsize=8, loc="left")
    ax.set_xticks([])
    ax.set_yticks([])
    return handle


def difference_panels(path: Path, frame: int, raw, fiji, ours, origin) -> None:
    """Rows: max-Z (XY) and max-Y (XZ) projections in Fiji's region."""
    y0, x0 = origin
    height, width = fiji.shape[-2:]
    region = (slice(None), slice(y0, y0 + height), slice(x0, x0 + width))
    reference = fiji[0].astype(np.float32)
    raw_t = raw[frame][region].astype(np.float32)
    ours_t = ours[frame][region]
    fiji_t = fiji[frame].astype(np.float32)
    fig, axes = plt.subplots(2, 5, figsize=(17, 6.4), facecolor=SURFACE)
    for row, axis in enumerate((0, 1)):
        project = lambda v, a=axis: v.max(axis=a)  # noqa: E731
        ref, rw, ou, fj = map(project, (reference, raw_t, ours_t, fiji_t))
        span = float(np.percentile(ref, 99.5))
        label = "max-Z (XY)" if axis == 0 else "max-Y (XZ)"
        _panel(axes[row, 0], ref, f"reference (frame 0), {label}", vmin=0, vmax=span)
        diff_span = max(float(np.percentile(np.abs(rw - ref), 99.5)), 1.0)
        _panel(
            axes[row, 1],
            rw - ref,
            f"raw t={frame} - reference",
            cmap=DIVERGING,
            vmin=-diff_span,
            vmax=diff_span,
        )
        _panel(
            axes[row, 2],
            ou - ref,
            "Fast4DRegPy - reference",
            cmap=DIVERGING,
            vmin=-diff_span,
            vmax=diff_span,
        )
        _panel(
            axes[row, 3],
            fj - ref,
            "Fiji - reference",
            cmap=DIVERGING,
            vmin=-diff_span,
            vmax=diff_span,
        )
        small = max(float(np.percentile(np.abs(ou - fj), 99.9)), 1.0)
        handle = _panel(
            axes[row, 4],
            ou - fj,
            f"Fast4DRegPy - Fiji (±{small:.0f})",
            cmap=DIVERGING,
            vmin=-small,
            vmax=small,
        )
        fig.colorbar(handle, ax=axes[row, 4], fraction=0.046)
    fig.suptitle(f"frame {frame}", color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)


def make_plots(output, raw, fiji, ours, shifts, truth, fiji_translation, rows, origin):
    output = Path(output)
    trajectories(output / "drift_trajectory.png", shifts, truth, fiji_translation)
    metric_series(output / "fiji_comparison_metrics.png", rows)
    frames = raw.shape[0]
    worst = int(np.argmin([r["volume_pearson"] for r in rows[1:]]) + 1)
    selected = sorted({0, min(1, frames - 1), frames // 2, frames - 1, worst})
    for frame in selected:
        difference_panels(
            output / f"difference_frame{frame:02d}.png", frame, raw, fiji, ours, origin
        )
