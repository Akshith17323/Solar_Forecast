# Kaggle publishing templates

Use `docs/PUBLISHING_GUIDE.md` for complete instructions.

- `kernel-metadata.example.json`: copy beside the notebook as `kernel-metadata.json`;
  replace the account placeholder before pushing. It starts private, with no GPU,
  internet, or external input dependencies.
- `dataset-metadata.example.json`: copy beside **approved data only** as
  `dataset-metadata.json`; fill account/source/license details. The license
  placeholder intentionally prevents treating it as a ready-to-publish dataset.

Do not point a Kaggle dataset upload at the repository root. `.gitignore` does not
filter Kaggle uploads. The ignored `notebook_upload/` and `dataset_upload/` folders
are local staging areas, not published content until you explicitly use the CLI.

No API keys belong in these files, and no uploads are performed automatically.
