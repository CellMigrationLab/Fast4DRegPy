# Troubleshooting and known issues

[⬅️ Documentation index](index.md)

Fast4DRegPy stops with a message rather than return a result it cannot
trust. Most messages say what to change.

## Messages

**`axes='...' has N entries, but image has M dimensions`** (napari / Fiji:
*The image has shape (...)*): the axes do not match the image. Give one letter
per dimension, in the order of the file: see
[the axes table](workflow.md#before-you-start). A Fiji hyperstack is saved as
T, Z, C, Y, X without the dimensions of size 1.

**`... needs a Z axis` / `have no T axis` / `have no C axis`:** Z correction
needs a 3D image; drift correction needs a T axis; channel alignment needs a
C axis.

**`time_averaging=N leaves fewer than two averaged blocks`:** the movie has
too few frames for that averaging. Use a smaller value (1 measures every
frame). Fiji silently reports zero drift in this case.

**`the correlation peak ... lies at the edge of the max_expected_drift=N
search window`:** the drift is larger than the maximum expected drift (for Z,
in stretched axial pixels). Raise it, or set it to 0 to search the whole
correlation map. Fiji writes NaN or a clipped value in this case.

**`reference_channel=N is outside the available range`:** channels are
counted from 0. In Fiji, channel 1 is 0 here.

**`backend='unthreaded' is not available with time_averaging > 1 or
max_expected_drift > 0`:** keep the default `threaded` backend for these
settings.

## Results that look wrong

**The drift has sudden jumps.** A frame was matched to the wrong structure.
Try the `mean` projection (better for noisy images), time averaging, or a
maximum expected drift a little above the real drift.

**The Z drift is too small, or stays near 0, although the sample moves in Z.**
The stack may have too few slices: on about 10 slices or fewer, Z drift is
underestimated, down to almost zero for smooth images (Fiji Fast4DReg does the
same; see [Before you start](workflow.md#before-you-start)). With about 20
slices it is measured correctly. Also check that Z correction is ticked and
that the axes put Z where it is in the file.

**The corrected movie still drifts slowly (live samples).** Compare with the
previous frame (`reference: previous`) instead of the first.

**Black borders.** Moving the frames brings in empty pixels. Tick **Crop
output** to keep only the region present in every frame (this also changes
the Z estimate, as in Fiji).

**Planes missing at the top or bottom after Z correction.** Tick **Extend Z**
(*Extend stack to fit*).

**Numbers differ slightly between runs** (about 0.001 pixel). NanoPyx sums in
parallel; set the environment variable `OMP_NUM_THREADS=1` for identical
numbers every time.

**Out of memory.** The corrected movie is 32-bit, twice the size of a 16-bit
input. Choose the output type `input`, use fewer workers, or crop the movie
first.

## napari and Fiji

**Fast4DRegPy is not in the list of apps.** Install the
[Fast4DRegPy app](installation.md#desktop-app) first, then click *Rescan apps*
(napari) or restart Fiji. The plugin's own help:
[napari](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/napari/),
[Fiji](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/fiji/).

**The corrected movie opens in Fiji as one long stack.** Use *Image >
Hyperstacks > Stack to Hyperstack*. See [napari and Fiji](napari_fiji.md#good-to-know).

**The desktop app does not start or install.** See
[If the app does not start](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/troubleshooting-installed-app/)
on the LabConstrictor website.

## Known differences from the Fiji macro

- One set of projection, reference, averaging and search settings for both XY
  and Z (Fiji can use different values).
- Errors instead of NaN, clipped or zero drift (above).
- *Save RAM* is close to `output_dtype="input"` but not bit-identical.

Details: [Fiji compatibility](fiji_compatibility.md).

Still stuck? [Open an issue](https://github.com/CellMigrationLab/Fast4DRegPy/issues)
with the message, the axes and the shape of your image, and the settings.
