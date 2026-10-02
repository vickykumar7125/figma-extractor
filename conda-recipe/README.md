# conda-recipe

Noarch conda recipe for [figma-extractor](https://github.com/vickykumar7125/figma-extractor).

```bash
conda build conda-recipe -c conda-forge --output-folder ./conda-bld
anaconda --site anaconda.org upload -u vickykumar7125 ./conda-bld/noarch/figma-extractor-*.conda
```

Install:

```bash
conda install -c vickykumar7125 figma-extractor
```

Keep `ANACONDA_API_TOKEN` in GitHub Actions secrets (or a local password store). Never commit the token.
