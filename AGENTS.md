# Repository instructions

## Purpose

This repository is the Python implementation of Fast4DReg. It preserves the
projection-based Fast4DReg workflow while using the real NanoPyx drift estimator
in the same architectural role that NanoJ serves in the Fiji implementation.

## Setup and validation

Install with:

    python -m pip install -e ".[test,notebook]"

Run all tests with:

    python -m pytest -q

NanoPyx is a required dependency. Do not mock it, vendor it, or silently skip
integration tests when it cannot be imported.

Run both checks before considering a change complete:

    python -m ruff check src tests benchmarks
    python -m pytest -q

## Scientific rules

- Read `docs/fiji_compatibility.md` before changing registration behaviour,
  and re-run the full-movie validation (`validation/README.md`) afterwards.
- Take work from `CODEX_TASKS.md` in priority
  order; do not mark parity tasks complete without their acceptance tests.
- Preserve explicit axis semantics; never guess stack dimensions.
- Reject invalid inputs and unsupported settings with descriptive exceptions.
- Never silently change a setting, select a backend, retry another backend,
  overwrite a file, or disable an unavailable correction.
- Store and document translations in `(dz,dy,dx)` order.
- Estimate and apply XY before constructing the projection used for Z drift.
- Apply each timepoint translation identically to every channel.
- Keep transform concurrency explicit through `workers`; never infer a worker
  count or silently retry failed work.
- Use asymmetric synthetic images to detect axis swaps and sign errors.
- Compare numerical behaviour with original Fiji Fast4DReg outputs.
- Preserve `paper_nrmse` exactly for published-result reproduction and keep it
  visibly distinct from conventional `standard_nrmse`.
- Keep algorithm code in `src/fast4dreg`; notebooks only call the public API.
- Keep the public API direct and explicit. Do not route parameters through
  `**kwargs`, configuration objects, registries, or plugin factories.

## Scope

Do not add true 3D correlation, rotations, Dask, Zarr, GPU selection, plugin
systems, factories, or elaborate notebook styling unless separately approved.
Prefer small functions and direct NumPy arrays over configurable frameworks.
