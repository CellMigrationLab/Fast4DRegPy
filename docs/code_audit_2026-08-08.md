# Full code audit — 2026-08-08

> **Superseded (2026-09-25):** see [`audit_2026-09-25.md`](audit_2026-09-25.md).
> Several conclusions below (Z parity, ground-truth convention, bounded windows,
> time averaging, interpolation) were revised by that audit.

## Scope

This audit treated version 0.2.0 as untrusted. It reviewed every maintained
file in the repository: 1,788 lines of Python source and tests, the notebook,
packaging metadata, CI workflow, repository instructions, and user
documentation. Generated environments, caches, build output, and package
metadata were excluded.

The behaviour was compared with the Fast4DReg paper, the archived validation
notebook, and `CellMigrationLab/Fast4DReg` commit
`0483ace1ac5b8ee0e3938d00c303104109897803`, which was the latest upstream
commit at audit time. NanoPyx 2.1.4's public wrapper, LiquidEngine dispatch,
and low-level drift estimator were also inspected.

## Corrected findings

| Severity | Finding in 0.2.0 | Resolution in 0.3.0 |
| --- | --- | --- |
| Critical | Z drift was estimated from raw volumes instead of volumes after XY correction. | XY is estimated and applied first; the axial projection is built from the corrected float32 volumes. A regression test checks this ordering. |
| Critical | NanoPyx's LiquidEngine dispatcher could choose a backend implicitly and catch a backend error before retrying another implementation. | The caller selects `threaded` or `unthreaded`; that low-level NanoPyx method is called directly and its error propagates. |
| High | NanoPyx could silently clamp `time_averaging` or ignore an oversized maximum-drift window. | Strict integer and range checks reject those settings before NanoPyx runs. |
| High | NanoPyx centre-crops rectangular projections to a smaller even square. | Projection frames are symmetrically padded to the larger even square so all image content is retained. This is explicit but not yet Fiji-equivalent axial scaling. |
| High | Integer inputs produced integer corrected output, silently quantizing subpixel interpolation. | Corrected output defaults to float32. Input dtype preservation requires `output_dtype="input"`. |
| High | `np.allclose` treated very small non-zero shifts as zero. | Only an exactly zero translation uses the copy shortcut. |
| High | Invalid interpolation settings could pass when every shift was zero. | Interpolation order, fill value, and output dtype are validated before processing. |
| Medium | Lowercase axes were normalized internally but rejected by the time-axis check. | All later checks use the normalized axes string. |
| Medium | `correct_z=True` by default made ordinary `TYX` and `CYX` calls fail. | Z correction is explicitly opt-in and requires a real multi-slice Z axis. |
| Medium | `register_*` routed arbitrary `**kwargs`, hiding the supported API and delaying typo detection. | Both orchestration functions have complete explicit signatures. |
| Medium | Empty, non-numeric, complex, or non-finite images and constant projection frames reached numerical code. | Inputs and projection frames are checked with descriptive errors. |
| Medium | TIFF axes were not checked against array dimensions; drift CSV indices and finite values were not validated. | TIFF and CSV reads/writes now validate their complete schemas and values. |
| Medium | Saves overwrote existing files without confirmation. | All save functions default to `overwrite=False`; the notebook exposes the same explicit choice. |
| Medium | Constant color overlays, out-of-bounds profile endpoints, non-boolean or overlapping masks, and non-positive background means returned misleading results. | Validation helpers reject these conditions. |
| Low | Registration, axis conversion, transformation, and backend code were combined in one 387-line module. | They are separated into `axes`, `estimation`, `transform`, and a 98-line orchestration `core`; scalar and image validation are also separate. |
| Low | The source archive omitted the notebook and audit/task documentation. | `MANIFEST.in` includes the notebook and project documents. |

## Public API

The registration surface remains six functions:

- `estimate_time_drift` and `apply_drift`;
- `estimate_channel_shifts` and `apply_channel_shifts`;
- `register_time` and `register_channels` as the two convenience functions.

No configuration class, factory, registry, plugin layer, automatic axis
inference, or fallback backend was added. Registration shifts remain
`(dz, dy, dx)` translations to apply.

## Verification

- Ruff static checks: passed.
- Pytest: 37 tests passed.
- Real NanoPyx integration: known XYZ time and channel translations recovered;
  registration error decreased on the synthetic volume.
- Wheel test: the complete test suite passed against the installed 0.3.0
  wheel from outside the checkout.
- Notebook: valid notebook JSON and every code cell parsed as Python.
- Packaging: wheel and source archive built; source archive contents were
  checked for the notebook and audit documents.

NanoPyx emits warnings while importing unavailable optional OpenCL and Numba
components in this test environment. The warnings are not suppressed. The
requested low-level CPU backend is still called directly, so they do not cause
an implicit registration-backend change.

## Open scientific gaps

These are recorded rather than hidden behind approximations:

1. No redistribution-safe raw dataset plus Fiji drift tables and corrected
   output has been selected, so numerical Fiji parity remains unproven.
2. Fiji's calibrated bicubic axial-reslice scaling and Z-shift rescaling are
   not implemented. The current complete-projection padding is documented.
3. Exact Fiji interpolation, boundary, crop, extension, rounding, and bit-depth
   parity requires reference fixtures.
4. XY and Z still share projection/reference/drift settings.
5. OME metadata, crop-to-overlap, extend-Z, batch processing, and lazy
   Dask/Zarr arrays are not implemented.

The first three items remain P0 work in `CODEX_TASKS.md`. Lazy loading remains
deferred until the in-memory scientific-parity tests exist, so a second storage
engine cannot mask numerical discrepancies.
