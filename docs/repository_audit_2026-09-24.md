# Repository readiness audit — 2026-09-24

## Scope

This pass reviewed the complete `fast4dreg-python-0.4.0` archive as a candidate
for a new public repository. The audit covered source code, tests, packaging,
GitHub Actions, documentation, notebook structure, the original Fast4DReg Fiji
repository, NanoPyx 2.1.4, and the Fast4DReg Zenodo archive.

## Project identity

This repository should be presented as **Fast4DReg Python**, the Python
implementation of Fast4DReg. NanoPyx supplies the cross-correlation drift
estimator in the same architectural role that NanoJ supplies it in the Fiji
implementation.

`napari-fast4dreg` is a separate Python interpretation that wraps a broader
registration workflow in a napari plugin and adds features beyond the original
Fast4DReg method. It is related work, not the canonical identity of this
repository.

## Findings corrected in this pass

### Documentation and provenance

- Replaced wording that described this package merely as a "port" or
  "prototype" with the intended Fast4DReg Python identity.
- Documented the architectural mapping **NanoJ (Fiji) -> NanoPyx (Python)**.
- Documented the separate status of `napari-fast4dreg` without treating it as
  the canonical Python implementation.
- Added the requested Zenodo dataset record, `6534570`, and its DOI.
- Recorded that Zenodo currently links record `6534570` to expanded version
  `7514913`, while retaining `6534570` as the requested archival reference.
- Added `docs/data.md` with a concrete plan for turning the archive into small,
  checksummed parity fixtures rather than vendoring multi-gigabyte data.
- Added the dataset links to package metadata.

### Continuous integration

The package metadata declares Python 3.10 through 3.13 support, but the workflow
previously tested only Python 3.12. CI now runs the complete pytest suite on
3.10, 3.11, 3.12, and 3.13. Ruff and package building remain on 3.12 to avoid
unnecessary duplicated work.

### Repository instructions

- Updated the initial commit wording from "Python port" to "Fast4DReg Python
  implementation".
- Updated agent/developer instructions to preserve the NanoJ/NanoPyx
  architectural relationship.

## Source-code assessment

The core source remains well structured. In particular:

- axis semantics are explicit and never guessed;
- time and channel registration are separate entry points;
- translations have one documented `(dz, dy, dx)` convention;
- NanoPyx backend selection is explicit;
- XY correction is applied before the axial projection used for Z estimation;
- subpixel corrections default to float32 rather than silently quantizing back
  to integer input types;
- transformation concurrency is explicit and deterministic;
- existing files are not overwritten unless requested;
- validation functions preserve the historical paper metric separately from a
  conventional NRMSE.

No additional source-code defect was found in this pass that could be safely
changed without reference-output validation.

## Important scientific limitation

The major unresolved issue is **Z-registration parity**.

The Fiji macro reslices the volume, derives a scale factor from the resliced
geometry, bicubically rescales the axial projection before drift estimation,
and then divides the measured Z drift by that scale factor. Version 0.4.0 of
the Python implementation instead retains the complete axial projection and
pads it to an even square before passing it to NanoPyx.

The current Python behavior is explicit and tested, but it is not yet proven
numerically equivalent to Fiji. It should therefore remain documented as the
highest-priority parity task rather than being silently presented as exact
Fiji numerical reproduction.

## Tests run in this environment

The non-NanoPyx suite was run directly from the source tree with `PYTHONPATH=src`:

- **42 tests passed**
- **3 NanoPyx integration tests deselected**

The integration tests could not be rerun in this execution environment because
NanoPyx is not installed and outbound package installation is unavailable.
This is an environment limitation, not a skipped repository test: CI installs
NanoPyx 2.1.4 and is configured to run those tests normally.

The integration tests already present in the repository are scientifically
useful: they check known XYZ translations, sign/order, improvement after
correction, and reference-channel behavior using the real NanoPyx estimator.

## Recommended repository name

**`Fast4DReg-Python`**

This is the clearest choice because it preserves the Fast4DReg identity,
distinguishes the repository from the Fiji implementation, and avoids implying
that the project is the napari plugin.

Recommended naming:

- GitHub repository: `CellMigrationLab/Fast4DReg-Python`
- Python import: `fast4dreg` (current; keep it)
- Distribution name: `fast4dreg-python` (current; acceptable for now)
- Display name: **Fast4DReg Python**

## Before the first public release

The repository is suitable to create now. Before making a strong claim of full
numerical equivalence with Fiji, the next scientific step should be to extract
small XYT and XYZT cases from the Zenodo archive, generate reference outputs
with the current Fiji Fast4DReg, and add them as regression fixtures. That work
should then drive the axial-rescaling implementation and any interpolation or
boundary-condition compatibility changes.
