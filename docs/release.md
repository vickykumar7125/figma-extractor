# Release

Version lives in `figma_extractor.__version__`. `pyproject.toml` reads that attribute. A Git tag `v2.1.0` must match version `2.1.0`.

The package is pure Python, so the release contains:

- `figma_extractor-<version>-py3-none-any.whl`
- `figma_extractor-<version>.tar.gz`
- `SHA256SUMS`
- `release-manifest.json`

There is no CUDA wheel, CPU wheel, or XPU wheel. Those accelerators are requirements files for PyTorch.

## Pipeline

Pushing a tag `v*` runs `.github/workflows/release.yml`:

1. Tests on Linux, Windows, and macOS, Python 3.11 and 3.12.
2. `python -m build` and `twine check`.
3. Confirms the wheel tag is `py3-none-any` and matches the Git tag.
4. Writes checksums and `release-manifest.json`.
5. Installs the wheel in a clean virtualenv and runs `figma-extractor --help`.
6. Creates a GitHub Release with those files.
7. Publishes the wheel and sdist to PyPI with Trusted Publishing.

No API token is stored in the repository or the workflow. Publishing uses GitHub OIDC (`id-token: write`) and the environment named `pypi`.

## Trusted publisher

On PyPI, add a trusted publisher for this repository:

| Field | Value |
| --- | --- |
| Owner | `vickykumar7125` |
| Repository | `figma-extractor` |
| Workflow | `release.yml` |
| Environment | `pypi` |

Create the GitHub environment `pypi` before the first tag. For a rehearsal, run the Release workflow manually and choose `testpypi`. That uses the environment `testpypi` and `https://test.pypi.org/legacy/`. Add a matching trusted publisher on TestPyPI.

If a PyPI token was pasted into a chat, issue tracker, or commit, revoke it on PyPI and create a new one only in a local password store. Do not put it in a workflow file.

## Local check

```bash
python -m pip install build twine
python -m build
twine check dist/*
python scripts/release_manifest.py dist
```

`python setup.py` installs a machine profile. It is not the build backend and it does not upload to PyPI.
