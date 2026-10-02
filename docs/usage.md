# Usage

## Extract a file

```bash
# local .fig, offline
figma-extractor extract --file ./design.fig --output ./out

# remote file key or URL
figma-extractor extract --remote https://www.figma.com/design/ABC123/My-Kit \
  --output ./out --api-key figd_xxx
```

`FIGMA_API_KEY` is used when `--api-key` is omitted. `--no-clean` keeps previous deliverables. `--keep-intermediates` keeps `source/` and `extracted/`.

## Inspect an extract

```bash
figma-extractor info --dir ./out
figma-extractor info --dir ./out --json
```

Without `--dir`, `info` reads the current directory and prints JSON.
