# Data storage policy

Git is used for reproducibility metadata, not as the dataset store.

## Commit to Git

- `data/README.md`
- `data/sample/` — small synthetic test fixtures
- `.gitkeep` placeholders
- `data/raw/elia_generation/source_manifest.json`
- `data/raw/belgium_weather_archive/download_manifest.json`
- `data/processed/model_training/dataset_manifest.json`

These manifests contain source URLs, schemas, row counts, units, retrieval details,
and SHA-256 hashes without duplicating the larger datasets.

## Do not commit

- Raw Elia CSV payloads
- Raw Open-Meteo JSON payloads
- Generated train, validation, and test CSV files
- Future trained model binaries, caches, or vector databases

The repository `.gitignore` excludes these files. Do not bypass it with
`git add -f`.

## Reproduce locally

Download the frozen Elia target and reviewed Belgian weather archive:

```bash
uv run python -m scripts.download_elia_training_data
uv run python -m scripts.download_belgium_weather
```

The Elia downloader rejects upstream revisions that do not match the reviewed
checksum. After the raw source files are present, generate the model-ready splits:

```bash
uv run python -m scripts.prepare_training_data
```

Generated files are written under `data/processed/model_training/` and verified
against `dataset_manifest.json`.

## Sharing large files

For collaboration, publish versioned datasets in object storage, a release asset,
or a dedicated dataset service and keep their URL and checksum in a tracked
manifest. Use Git LFS only when a host specifically requires repository-coupled
large files; it is unnecessary for the current reproducible API-sourced data.
