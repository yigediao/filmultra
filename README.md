# FilmUltra

FilmUltra is a local-first photo asset manager for photographers and image-heavy teams.
It focuses on fast browsing, RAW + JPG pairing, metadata-aware workflows, face clustering,
and experimental 3D reconstruction pipelines on top of a mounted photo library.

## What it does

- Scans a mounted photo library and merges RAW + JPG into a single logical asset
- Generates fast previews for browsing and review
- Supports ratings and metadata sync back to files or XMP sidecars
- Groups detected faces into unnamed clusters and promotes them into named people
- Provides review workflows for person assignment corrections
- Includes experimental SAM2 / SAM 3D body and object reconstruction tooling
- Keeps runtime outputs isolated under `var/` instead of polluting source directories

## Stack

- Backend: FastAPI, SQLAlchemy, Pillow, rawpy, OpenCV
- Frontend: Next.js 15, React 19, TypeScript
- Storage: SQLite by default, PostgreSQL-ready compose setup
- Optional ML tooling: SAM2, SAM 3D Body, SAM 3D Objects via `third_party/` submodules

## Project status

FilmUltra is currently an alpha-stage working project.
The core library, detail view, people workflow, and development smoke tests are usable.
The 3D pipeline is still experimental and depends on locally installed model weights.

## Quick start

### 1. Clone with submodules

```bash
git clone --recurse-submodules https://github.com/yigediao/filmultra.git
cd filmultra
```

If you already cloned without submodules:

```bash
git submodule update --init --recursive
```

### 2. Install backend dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### 4. Configure local paths

```bash
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
```

Edit `backend/.env` and point it at your mounted library and local runtime directories.

### 5. Start local development

```bash
make backend-dev
make frontend-dev
```

Backend defaults to `http://127.0.0.1:8000` and frontend defaults to `http://127.0.0.1:3000`.

## Common commands

```bash
make help
make smoke-synology-gvfs
make latest-synology-run
make review-synology-gvfs
make stop-review-synology-gvfs
make migrate-workspace
make project-status
```

## Repository layout

- `backend/`: FastAPI application and services
- `frontend/`: Next.js app and UI components
- `docs/`: architecture notes, environment setup, and development governance
- `scripts/`: developer and smoke-test entry points
- `third_party/`: external model and research repositories as git submodules
- `var/`: runtime state, logs, caches, and isolated test outputs

See also:

- `docs/architecture.md`
- `docs/development/README.md`
- `docs/development/REPO_LAYOUT.md`
- `docs/development/WORKLOG.md`
- `docs/sam3d_environment_setup.md`

## What is intentionally not versioned

The public repository does **not** include:

- local photo libraries or NAS mirror directories
- SQLite databases and generated previews
- smoke-test logs and temporary run outputs
- large checkpoints and model weights
- local mount session state and machine-specific helper outputs

These are ignored through `.gitignore` and expected to live outside source control.

## Synology / NAS workflow

FilmUltra works with any locally mounted photo directory.
If you are using Synology, SMB/NFS mounting is still a supported workflow, but the repository
is now generic: provide your own host, share, and local mount point via environment variables or script arguments.

## 3D tooling

The 3D pipeline requires extra setup and local checkpoints.
Use `docs/sam3d_environment_setup.md` for the current environment model, expected paths,
and the smoke-test entry points.

## Current caveats

- People clustering is still an MVP pipeline and benefits from manual review
- Job execution is still in-process rather than using a dedicated worker queue
- 3D reconstruction features depend on locally installed research dependencies and checkpoints
- UI copy is currently Chinese-first even though the codebase is intended for broader reuse
