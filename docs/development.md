# Development and releases

[⬅️ Documentation index](index.md)

## Set up and test

```bash
git clone https://github.com/CellMigrationLab/Fast4DRegPy
cd Fast4DRegPy
python -m pip install -e ".[dev]"
python -m ruff check src tests benchmarks validation lc_tests
python -m pytest -q
```

The test suite runs on Python 3.10–3.13 in about 10 seconds. NanoPyx (pinned
to 2.1.4) is a real dependency of the tests: it is never mocked. Rules for
changes to the registration code are in [AGENTS.md](../AGENTS.md).

The full comparison on the published movie is separate because it downloads a
1.5 GB archive: [validation/README.md](../validation/README.md) and
[Validation](validation.md).

## The napari and Fiji tools

`src/fast4dreg_lc_tools/` declares the tools with
[LabConstrictor Tools](https://cellmigrationlab.github.io/LabConstrictor-Tools/):
typed functions whose forms napari and Fiji generate. They only call the
public API of `fast4dreg`. To test them, install `labconstrictor-tools` (the
version the installer pins, `LC_TOOLS_PIN` in
`app/bash_bat_scripts/post_install.sh`) and `pandas`:

```bash
pin=$(sed -n 's/^ *LC_TOOLS_PIN="\(.*\)"$/\1/p' app/bash_bat_scripts/post_install.sh)
python -m pip install pandas "https://github.com/CellMigrationLab/LabConstrictor-Tools/archive/refs/tags/${pin}.zip"
python -m pytest -q tests/test_lc_tools.py
cd lc_tests && python make_fixtures.py fixtures && labconstrictor-tools test --module fast4dreg_lc_tools --cases cases.json
```

The tests workflow runs both. What the cases check:
[lc_tests/README.md](../lc_tests/README.md). How to write tools:
[the authoring guide](https://cellmigrationlab.github.io/LabConstrictor-Tools/AUTHORING/).

## The desktop app

The files that build the app come from the
[LabConstrictor template](https://github.com/CellMigrationLab/LabConstrictor):
`app/`, `.tools/`, `.template_sync/`, `construct.yaml`, `environment.yaml`,
`setup.py`, `requirements*.txt` and the workflows `release_constructor.yml`,
`publish_pypi.yml`, `update_on_*`, `sync_template.yml` and
`check_app_manifest.yml`. The weekly template-sync pull request keeps them up
to date; do not edit them by hand. Two files are this repository's own:

- `setup.py` is what the installer uses (it ships only `setup.py` and `src/`).
  It has no `python_requires` or `install_requires`, which would override
  `pyproject.toml` in the package on PyPI.
- `labconstrictor-app.yaml` describes the app for the
  [App Centre](https://cellmigrationlab.github.io/LabConstrictor-Site/apps/):
  summary, hosts (`notebook`, `napari`, `fiji`), icon, `distribution.pip`.
  Guide: [Describe your app](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/app-manifest/).

The app's Python environment is pinned in
`notebooks/Fast4DRegApp/requirements.yaml`. When it changes on `main`, a
workflow regenerates `requirements.txt` and the lock files. The installer
images and the icon are in `app/logo/` (from the Fast4DReg logo).

The template's own guides are in [.tools/docs](../.tools/docs/README.md) and
on the [LabConstrictor website](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/).

## Releases

A release builds the installers for Windows, macOS and Linux and, once
publishing is switched on, uploads the package to PyPI, with the version of
the release tag.

1. Set `version = "X.Y.Z"` in `pyproject.toml` and add the release notes to
   `CHANGELOG.md`. Commit to `main`.
2. Publish a GitHub release with the tag `vX.Y.Z`.
3. The **Build Release Installers** workflow writes the version into
   `setup.py` and `construct.yaml` and attaches the installers to the
   release. The **Publish the Python package to PyPI** workflow uploads
   `fast4dregpy` X.Y.Z. It stops, without uploading anything, if the version
   in `pyproject.toml` differs from the tag.

Details: [Create executable installers](https://cellmigrationlab.github.io/LabConstrictor-Site/guides/executable-creation/).

### Switch on PyPI publishing (once)

1. On [pypi.org](https://pypi.org/manage/account/publishing/), add a pending
   trusted publisher: owner `CellMigrationLab`, repository `Fast4DRegPy`,
   workflow `publish_pypi.yml`, environment `pypi`.
2. In the repository settings, *Secrets and variables > Actions > Variables*,
   add `PYPI_PUBLISH` with the value `true` (`testpypi` for a trial on
   TestPyPI).

No token is stored. Step by step:
[.tools/docs/external_code_upload.md](../.tools/docs/external_code_upload.md#4-publish-the-code-on-pypi-optional).

### List the app in the App Centre (once)

After the first release with installers,
[submit the repository](https://cellmigrationlab.github.io/LabConstrictor-Site/submit/)
to the LabConstrictor App Centre. Later releases appear there by themselves.
