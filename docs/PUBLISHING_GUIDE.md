# How to submit/publish this project: GitHub and Kaggle

**Guide checked against official documentation on 2026-11-10.**
Commands here are instructions for you; they have **not** been run to publish
anything. Replace `YOUR_GITHUB_USERNAME` / `YOUR_KAGGLE_USERNAME` with your actual
account names. Run local commands from the project root.

## 1. Which platform is best?

**Use GitHub as the primary platform for this project. Add Kaggle later if useful.**

| Need | GitHub | Kaggle |
|---|---|---|
| Entire backend, UI, tests, configuration, docs | **Best fit** | Not a source-code repository replacement |
| Change history, branches, issues, automated tests | **Best fit** | Notebook/data versioning, not the same Git workflow |
| EDA, training notebooks, ML results | Good | **Excellent showcase** |
| Sharing a redistributable dataset | Prefer external storage for large data | **Good**, subject to source license/privacy |
| Persistent FastAPI/Streamlit hosting | Needs a separate application host | Not a persistent production backend host |
| This project's original deliverables | **Explicitly requested** | Optional supplement |

The original brief lists **hosted application link + GitHub repository + demo
video** as final artifacts. A Kaggle notebook alone is not equivalent. Your newer
solo-project plan changes the implementation timeline, not the need to distinguish
code publishing from application hosting.

Recommended eventual submission bundle:

1. GitHub URL containing the complete, documented codebase.
2. Public working app URL on an appropriate host.
3. Short walkthrough video showing real validated outputs.
4. Model evaluation/data-source documentation.
5. Optional Kaggle notebook URL linked from the GitHub README.

**Right now this is a scaffold.** You can publish it as “planning / work in progress,”
but do not present it as a completed model or satisfy forecasting requirements
with the synthetic fixture data.

## 2. Before uploading anything

- [ ] Decide whether to keep the project private while planning.
- [ ] Confirm code ownership and choose a license for your own code.
- [ ] Review dataset/API terms: download permission does not imply redistribution permission.
- [ ] Keep required attribution; do not relicense someone else's data as CC0/MIT.
- [ ] Remove keys, passwords, sensitive site data, personal details, and credentials.
- [ ] Review notebooks **and saved outputs**, which can contain secrets or raw data.
- [ ] Keep large/raw data and generated artifacts out of normal Git commits.
- [ ] Label synthetic examples as synthetic; do not claim model performance from them.
- [ ] Run the checks in the README and confirm setup instructions work.
- [ ] Review the original PDF's rights before publishing it; it is ignored by default.

The `.gitignore` already excludes `.env`, credentials, `.venv`, generated data,
model artifacts, publishing staging directories, and the supplied PDF. It does
**not** remove secrets already tracked in Git history, and **Kaggle does not use
this file to protect uploads**.

If a credential is exposed, **revoke/rotate it immediately** and follow the
platform's history-removal guidance. Merely deleting the current file is not enough.

## 3. Push to GitHub — initial upload

### Step A: create a local Git repository

This folder was not a Git repository when the scaffold was created. If you have
already initialized it since then, skip `git init`.

```bash
git init -b main
```

If Git asks for your name/email, set them for this repository only:

```bash
git config user.name "Your Name"
git config user.email "YOUR_GITHUB_NOREPLY_EMAIL"
```

Use your actual GitHub email or the no-reply address shown in GitHub email settings.

Preview files, then stage and **review** them:

```bash
git add --dry-run .
git add .
git status --short
git diff --cached --stat
git diff --cached
```

If a file should not be included, unstage that specific path before committing:

```bash
git restore --staged path/to/unwanted-file
```

This unstages a file; it does not discard your working copy. Add the appropriate
ignore rule or remove confidential content before continuing. For an initial
repository with no commit yet, use `git rm --cached path/to/unwanted-file` to
untrack the file without deleting its local copy.

After the review:

```bash
git commit -m "Add configurable backend scaffold and project documentation"
```

### Step B, option 1: GitHub CLI — easiest terminal route

On macOS:

```bash
brew install gh
gh auth login
gh auth setup-git
```

Create a **private** repository during planning and push the current commit:

```bash
gh repo create solar-forecast --private --source=. --remote=origin --push
```

If you deliberately want a public repository and have completed the rights/secret
review, use `--public` **instead of** `--private`; do not run both creation commands.
You can change visibility later through repository Settings after reviewing policy.

If the remote repository already exists, do not create it again. Use option 2's
remote/push commands instead.

### Step B, option 2: GitHub website + Git

1. On GitHub, choose **New repository**.
2. Name it `solar-forecast`; choose the intended visibility.
3. Create it **empty**: do not initialize a remote README, license, or `.gitignore`
   when pushing an already prepared local project.
4. Authenticate with GitHub CLI, a credential manager, or configured SSH. Account
   passwords are not Git HTTPS credentials; do not paste a token into the remote URL.
5. Link and push:

```bash
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/solar-forecast.git
git remote -v
git push -u origin main
```

If `origin` already exists, inspect it with `git remote -v`. If it is genuinely the
wrong URL, update it instead of adding a second remote:

```bash
git remote set-url origin https://github.com/YOUR_GITHUB_USERNAME/solar-forecast.git
```

Do not use force-push to fix an initial upload error. If the remote contains
unexpected commits, inspect and reconcile them first, or use a new empty remote.

### No-terminal alternative: GitHub Desktop

After local Git initialization, use **File → Add Local Repository**, choose this
folder, review the changes, and choose **Publish repository**. Keep the private
checkbox enabled while planning. Later commits can be sent with **Push origin**.

### Verify the upload

- Open `https://github.com/YOUR_GITHUB_USERNAME/solar-forecast`.
- Confirm the README renders and its document links open.
- Confirm `.env`, credentials, raw private data, and `.venv` are absent.
- Check **Actions** for the lint/test workflow result; no workflow has run yet locally.
- Ask an authorized reviewer to follow the README in a clean environment.

## 4. Push later GitHub updates

Example after editing code/docs:

```bash
git status
git add README.md app.py src/ tests/ docs/ config/
git diff --cached --stat
git diff --cached
git commit -m "Describe the actual change made"
git push
```

Stage `pyproject.toml` and `uv.lock` together when dependencies change. Commit
scripts/manifests for reproducibility rather than silently uploading a model binary.
Use a release asset, DVC, or a licensed dataset/model host for larger artifacts as
needed; review that host's visibility and licensing too.

If `git push` is rejected because another computer/person changed the remote,
inspect `git fetch` and the history first. Do not discard local changes or force-push
as a routine fix.

## 5. Publish a Kaggle notebook — easiest website route

Use Kaggle for **analysis and ML experiments**, not for running the backend forever.

1. Sign in to Kaggle and open **Code → New Notebook**.
2. Use the editor's upload/import notebook option to upload
   `notebooks/00_project_starter.ipynb`.
3. Keep it private initially. The starter runs offline on explicitly synthetic data.
4. When a real source is chosen, attach an existing licensed Kaggle dataset using
   **Add Input/Add Data** if possible, instead of re-uploading someone else's data.
5. Set `DATA_PATH`, target/timestamp names, and source/license details in the notebook.
   Use the mounted path shown by Kaggle; do not assume your local `data/` folder exists.
6. Document cleaning, chronological splits, baselines, metrics, and limitations
   when real modeling is added.
7. Run all cells, inspect outputs, then **Save Version / Save & Run All**.
8. After a final rights/secret review, make the intended version public and share
   its `https://www.kaggle.com/code/USERNAME/NOTEBOOK-SLUG` URL.
9. Add the Kaggle link to GitHub, and the GitHub link to the notebook introduction.

Kaggle input mounts are normally read-only. Write generated outputs under
`/kaggle/working`. A GPU is unnecessary for this scaffold and basic regression
baselines. Notebook resources, internet access, quotas, and verification requirements
depend on Kaggle's current account/platform rules.

## 6. Push a Kaggle notebook from the terminal

### Install and authenticate

Keep publishing tools separate from runtime dependencies:

```bash
uv tool install --python 3.11 kaggle
kaggle auth login
kaggle kernels list --mine
```

The current CLI supports browser-based OAuth. If your installed version lacks
`auth login`, update it or follow the official authentication documentation. Kaggle
also supports an API token file at `~/.kaggle/access_token` and legacy credentials
at `~/.kaggle/kaggle.json`. Keep either outside the project and protect it:

```bash
chmod 600 "$HOME/.kaggle/access_token"
```

Use that command only if you chose and created the token file. For legacy
credentials, protect `~/.kaggle/kaggle.json` instead. Never put token values in
notebooks, metadata JSON, Git commits, screenshots, or a public chat.

### Prepare a dedicated notebook upload folder

```bash
mkdir -p publishing/kaggle/notebook_upload
cp notebooks/00_project_starter.ipynb publishing/kaggle/notebook_upload/
cp publishing/kaggle/kernel-metadata.example.json \
  publishing/kaggle/notebook_upload/kernel-metadata.json
```

Edit `kernel-metadata.json`:

- Replace `YOUR_KAGGLE_USERNAME` in `id`.
- Keep the title and slug consistent.
- Keep `code_file` matching the copied notebook filename.
- Keep `is_private` set to `"true"` during review.
- Add `dataset_sources: ["OWNER/DATASET-SLUG"]` only for real attached sources.
- Keep internet/GPU disabled unless your actual notebook requires them.

Then upload and run:

```bash
kaggle kernels push -p publishing/kaggle/notebook_upload
kaggle kernels status YOUR_KAGGLE_USERNAME/solar-forecast-project-starter
```

Inspect the saved run on Kaggle. To update later, copy the edited notebook into
the same folder again and repeat `kernels push`. This is a **Kaggle notebook
version upload**, not a Git push of the entire repository.

Some current CLI versions support `--no-run` for a quick save without execution;
use a fully executed version when presenting results. If initial creation reports
“Notebook not found,” create the private notebook in the web UI first, then
download its exact metadata using `kaggle kernels pull ... -m` into a separate
folder and use its actual ID for updates.

## 7. Publish a Kaggle dataset — optional, only if permitted

**Prefer attaching an existing source dataset.** Create your own Kaggle dataset
only for files you own or are legally allowed to redistribute. Private upload
does not waive source privacy or license obligations.

After the review, prepare a folder containing only approved files:

```bash
mkdir -p publishing/kaggle/dataset_upload
cp publishing/kaggle/dataset-metadata.example.json \
  publishing/kaggle/dataset_upload/dataset-metadata.json
```

Copy the approved CSV/Parquet and its data dictionary/source/license notes into
that folder. Do **not** copy the entire repository or `data/raw/` blindly. If you
choose to publish the starter's own synthetic examples, preserve their synthetic
labeling and choose an applicable license first; they are not a measured dataset.

Edit the metadata:

- Set `id` to `YOUR_KAGGLE_USERNAME/solar-forecast-reviewed-sample`.
- Set the title/description to describe the **actual data**.
- Replace `REPLACE_AFTER_LICENSE_REVIEW` with the supported, applicable license
  identifier. The template is intentionally not upload-ready without this decision.
- Include original URLs, attribution, units, timestamp policy, and known limitations.

Create it privately first (the CLI's default):

```bash
kaggle datasets create -p publishing/kaggle/dataset_upload --keep-tabular
kaggle datasets status YOUR_KAGGLE_USERNAME/solar-forecast-reviewed-sample
```

`--keep-tabular` preserves formats such as Parquet instead of requesting conversion
to CSV. If you deliberately choose public visibility **at creation**, add `--public`
to that creation command; otherwise review privately and change visibility in the
website's dataset settings when ready.

To upload a new version of the same dataset:

```bash
kaggle datasets version -p publishing/kaggle/dataset_upload \
  --message "Describe the data corrections or additions" --keep-tabular
```

Keep old versions for reproducibility. Attach the resulting dataset to your
notebook through `dataset_sources` or Kaggle's editor. Review the actual mounted
path and record the version used for evaluation.

## 8. Competition submission is different

Publishing a solar project/notebook does **not** automatically enter a Kaggle
competition or produce a leaderboard score. Competition submission only applies
after joining a particular competition, accepting its rules, using its required
data and file format, and following its allowed workflow.

For a file-based competition that permits CLI submission, the command pattern is:

```bash
kaggle competitions submit -c COMPETITION-SLUG -f submission.csv \
  -m "Description of this competition submission"
```

This scaffold does not create `submission.csv`. Code competitions may require
submitting an executed notebook rather than a file. Follow the selected
competition's rules; do not run this command for an unrelated project.

## 9. Hosting and final hand-in

GitHub stores code; GitHub Pages cannot run a Python FastAPI backend. Kaggle runs
notebooks; it is not the production service host for this application.

Choose a host after the architecture is finalized: for example, a reviewed
Streamlit hosting setup or container-capable application platform. Check current
free-tier availability, Python support, memory, persistence, outbound API access,
quotas, and secret handling. Do not assume free-tier terms stay unchanged.

If using this two-process layout, the hosted Streamlit client needs a reachable
hosted API via `BACKEND_URL`. Hosting only `app.py` with its default localhost URL
will **not** make the backend available. Decide whether to host them separately
or deliberately simplify to a single-process Streamlit application later.

Final README should include:

- Confirmed problem statement and intended user.
- Working app and optional Kaggle links.
- Dataset/API source, license, schema, units, version, and reproduction commands.
- Honest chronological baseline/model results and limitations.
- Architecture, setup, training/inference/agent instructions, and test commands.
- Short demo video, responsible-AI disclaimer, and current project status.

## Official references

- [GitHub: add locally hosted code](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)
- [GitHub CLI: `gh repo create`](https://cli.github.com/manual/gh_repo_create)
- [GitHub: authentication](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)
- [Kaggle API overview](https://www.kaggle.com/docs/api)
- [Kaggle CLI installation/authentication](https://github.com/Kaggle/kaggle-cli/blob/main/docs/README.md)
- [Kaggle notebook commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md)
- [Kaggle notebook metadata](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md)
- [Kaggle dataset commands](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets.md)
- [Kaggle dataset metadata/licenses](https://github.com/Kaggle/kaggle-cli/blob/main/docs/datasets_metadata.md)
