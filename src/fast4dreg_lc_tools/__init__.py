"""Fast4DRegPy in napari, Fiji and on the command line (LabConstrictor tools).

The LabConstrictor installer finds this module next to the package `fast4dreg`
and registers its tools for the hosts listed in labconstrictor-app.yaml. The
tools only call the public API of `fast4dreg`; the science is there, not here.

napari and Fiji hand over the image as an array without saying what its
dimensions are, and Fast4DRegPy never guesses them, so each tool asks for the
axes. Fiji saves a hyperstack in the order T Z C Y X and leaves out the
dimensions of size 1.

Only `labconstrictor_tools` and the standard library are imported at module
level: hosts import this module to list the tools. The app's installer installs
`labconstrictor_tools`; the rest of `fast4dreg` does not need it.
"""

from typing import Annotated, Literal

from labconstrictor_tools import (
    Advanced,
    Description,
    Group,
    Image,
    ImageOut,
    Label,
    Min,
    Name,
    TableOut,
    ToolError,
    progress,
    tool,
)

AXES_HELP = (
    "One letter per dimension of the image, in order: T time, Z slices, "
    "C channels, Y and X. From Fiji (dimensions of size 1 left out): TYX, TZYX, "
    "TCYX, TZCYX. A napari layer usually is TYX or TZYX."
)
WORKERS_HELP = (
    "Number of volumes transformed at the same time. Never changes the result; "
    "more uses more memory. 1 is safe."
)
INTERPOLATION_HELP = (
    "imagej: ImageJ bicubic, as in Fiji Fast4DReg. scipy: SciPy spline interpolation."
)
OUTPUT_DTYPE_HELP = (
    "float32 keeps the interpolated values; input rounds them back to the type "
    "of the image."
)
AXIAL_HELP = "The reslice used to measure Z drift: Y as Fiji's 'Top', X as 'Left'."

DECIMALS = 4

Axes = Annotated[str, Label("Axes"), Description(AXES_HELP)]


def _axes(image, axes: str, needs: str) -> str:
    """The axes as Fast4DRegPy reads them, or a message the person can act on."""
    from fast4dreg.axes import normalize_axes

    try:
        normalized = normalize_axes(image, axes)
    except (TypeError, ValueError) as error:
        shape = tuple(image.shape)
        raise ToolError(
            "bad_axes",
            f"{error}. The image has shape {shape}: give one letter per dimension.",
        ) from error
    if needs not in normalized:
        raise ToolError(
            "bad_axes", f"Axes {normalized} have no {needs} axis; this tool needs one."
        )
    return normalized


def _shift_table(shifts, index_name: str) -> dict:
    """The (dz, dy, dx) translation applied to each timepoint or channel, in px.

    Rounded to 0.0001 px: the shifts are float32, whose last digits are noise.
    """
    return {
        index_name: list(range(len(shifts))),
        "dz": [round(float(row[0]), DECIMALS) for row in shifts],
        "dy": [round(float(row[1]), DECIMALS) for row in shifts],
        "dx": [round(float(row[2]), DECIMALS) for row in shifts],
    }


@tool("Correct drift (time-lapse)")
def correct_drift(
    image: Annotated[Image, Description("The 2D or 3D time-lapse to correct.")],
    axes: Axes = "TZYX",
    correct_xy: Annotated[
        bool,
        Group("What to correct"),
        Label("Correct XY drift"),
        Description("Measure and correct the drift in X and Y."),
    ] = True,
    correct_z: Annotated[
        bool,
        Group("What to correct"),
        Label("Correct Z drift"),
        Description("Needs a Z axis."),
    ] = False,
    projection: Annotated[
        Literal["max", "mean"],
        Group("Drift estimation"),
        Description("The projection the drift is measured on."),
    ] = "max",
    reference: Annotated[
        Literal["first", "previous"],
        Group("Drift estimation"),
        Description(
            "first: compare every frame with the first. "
            "previous: with the frame before (slow drift)."
        ),
    ] = "first",
    time_averaging: Annotated[
        int,
        Min(1),
        Group("Drift estimation"),
        Description(
            "Average this many frames before measuring; 1 measures every frame."
        ),
    ] = 1,
    max_expected_drift: Annotated[
        int,
        Min(0),
        Group("Drift estimation"),
        Label("Max expected drift (px)"),
        Description("Search radius in pixels; 0 searches the whole correlation map."),
    ] = 0,
    crop_output: Annotated[
        bool,
        Group("Output"),
        Description(
            "Crop to the region present in every frame, as Fiji's 'Crop output' "
            "(it also changes the Z estimate)."
        ),
    ] = False,
    extend_z: Annotated[
        bool,
        Group("Output"),
        Label("Extend Z"),
        Description("Pad Z so that Z translations keep every plane."),
    ] = False,
    reference_channel: Annotated[
        int,
        Min(0),
        Advanced(),
        Description(
            "The channel the drift is measured on, from 0; used when there is a C axis."
        ),
    ] = 0,
    axial_projection_axis: Annotated[
        Literal["Y", "X"], Advanced(), Description(AXIAL_HELP)
    ] = "Y",
    interpolation: Annotated[
        Literal["imagej", "scipy"], Advanced(), Description(INTERPOLATION_HELP)
    ] = "imagej",
    output_dtype: Annotated[
        Literal["float32", "input"], Advanced(), Description(OUTPUT_DTYPE_HELP)
    ] = "float32",
    workers: Annotated[int, Min(1), Advanced(), Description(WORKERS_HELP)] = 1,
) -> tuple[Annotated[ImageOut, Name("registered")], Annotated[TableOut, Name("drift")]]:
    """Measure the drift of a time-lapse and correct it, as Fiji's Fast4DReg does.

    The table gives, for each timepoint, the translation applied (dz, dy, dx) in pixels.
    """
    from fast4dreg import register_time

    normalized = _axes(image, axes, "T")
    if correct_z and "Z" not in normalized:
        raise ToolError(
            "bad_axes",
            f"Correct Z drift needs a Z axis; the axes {normalized} have none.",
        )
    progress(0.05, "measuring and correcting the drift")
    try:
        corrected, shifts = register_time(
            image,
            axes=normalized,
            reference_channel=reference_channel,
            projection=projection,
            reference=reference,
            correct_xy=correct_xy,
            correct_z=correct_z,
            axial_projection_axis=axial_projection_axis,
            time_averaging=time_averaging,
            max_expected_drift=max_expected_drift,
            interpolation=interpolation,
            crop_output=crop_output,
            extend_z=extend_z,
            output_dtype=output_dtype,
            workers=workers,
        )
    except ValueError as error:  # a setting the image does not allow, or a failed fit
        raise ToolError("invalid_settings", str(error)) from error
    return corrected, _shift_table(shifts, "timepoint")


@tool("Align channels")
def align_channels(
    image: Annotated[
        Image, Description("A 2D or 3D image with several channels, one timepoint.")
    ],
    axes: Annotated[
        str,
        Label("Axes"),
        Description(
            "One letter per dimension, in order: C channels, Z slices, Y and X. "
            "A Fiji composite is CYX, or ZCYX with slices."
        ),
    ] = "ZCYX",
    reference_channel: Annotated[
        int, Min(0), Description("The channel the others are aligned to, from 0.")
    ] = 0,
    correct_xy: Annotated[
        bool,
        Group("What to correct"),
        Label("Align in XY"),
        Description("Measure and correct the shifts in X and Y."),
    ] = True,
    correct_z: Annotated[
        bool,
        Group("What to correct"),
        Label("Align in Z"),
        Description("Needs a Z axis."),
    ] = False,
    projection: Annotated[
        Literal["max", "mean"],
        Group("Shift estimation"),
        Description("The projection the shifts are measured on."),
    ] = "max",
    max_expected_drift: Annotated[
        int,
        Min(0),
        Group("Shift estimation"),
        Label("Max expected shift (px)"),
        Description("Search radius in pixels; 0 searches the whole correlation map."),
    ] = 0,
    axial_projection_axis: Annotated[
        Literal["Y", "X"], Advanced(), Description(AXIAL_HELP)
    ] = "Y",
    interpolation: Annotated[
        Literal["imagej", "scipy"], Advanced(), Description(INTERPOLATION_HELP)
    ] = "imagej",
    output_dtype: Annotated[
        Literal["float32", "input"], Advanced(), Description(OUTPUT_DTYPE_HELP)
    ] = "float32",
    workers: Annotated[int, Min(1), Advanced(), Description(WORKERS_HELP)] = 1,
) -> tuple[
    Annotated[ImageOut, Name("aligned")], Annotated[TableOut, Name("channel_shifts")]
]:
    """Align the channels of a multichannel image on a reference channel.

    The table gives, for each channel, the translation applied (dz, dy, dx) in pixels.
    """
    from fast4dreg import register_channels

    normalized = _axes(image, axes, "C")
    if correct_z and "Z" not in normalized:
        raise ToolError(
            "bad_axes", f"Align in Z needs a Z axis; the axes {normalized} have none."
        )
    progress(0.05, "measuring and correcting the channel shifts")
    try:
        aligned, shifts = register_channels(
            image,
            axes=normalized,
            reference_channel=reference_channel,
            projection=projection,
            correct_xy=correct_xy,
            correct_z=correct_z,
            axial_projection_axis=axial_projection_axis,
            max_expected_drift=max_expected_drift,
            interpolation=interpolation,
            output_dtype=output_dtype,
            workers=workers,
        )
    except ValueError as error:
        raise ToolError("invalid_settings", str(error)) from error
    return aligned, _shift_table(shifts, "channel")
