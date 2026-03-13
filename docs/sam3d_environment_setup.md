# SAM / 3D Environment Setup

This document describes the optional local setup for FilmUltra's experimental 3D workflows.
These features are not required for the core library, rating, or people workflows.

## Scope

The current experimental chain is split into two steps:

1. `SAM2` generates a person or object mask from an input image and prompt box
2. `SAM 3D Body` or `SAM 3D Objects` consumes the generated bundle for downstream 3D processing

## Third-party repositories

FilmUltra expects these repositories under `third_party/`:

- `third_party/sam2`
- `third_party/sam-3d-body`
- `third_party/sam-3d-objects`

If you cloned the project without submodules:

```bash
git submodule update --init --recursive
```

## Recommended local environments

The helper scripts assume conda-style environments under `$HOME/miniconda3/envs/` by default:

- `sam2-photo`
- `sam3d-body-photo`

You can override the default conda location with `CONDA_SH=/path/to/conda.sh`.

## Bootstrap commands

From the repository root:

```bash
bash scripts/setup_sam2_env.sh
bash scripts/setup_sam3d_body_env.sh
```

To inspect what is available locally:

```bash
bash scripts/check_sam_envs.sh
```

## Expected checkpoints

Checkpoints are intentionally not committed to this repository.

### SAM2

Expected location:

- `third_party/sam2/checkpoints/sam2.1_hiera_large.pt`

### SAM 3D Body

Expected locations:

- `checkpoints/sam-3d-body/model.ckpt`
- `checkpoints/sam-3d-body/assets/mhr_model.pt`

## Runtime checks

### SAM2

```bash
$HOME/miniconda3/envs/sam2-photo/bin/python scripts/check_sam2_runtime.py
```

### SAM 3D Body

```bash
PYTHONPATH="$PWD/third_party/sam-3d-body" \
  $HOME/miniconda3/envs/sam3d-body-photo/bin/python scripts/check_sam3d_body_runtime.py
```

## Smoke test

The body smoke script now requires an explicit image path.
No sample image is committed to the public repository.

```bash
FACE_BBOX="343.17,249.18,547.94,460.67" \
bash scripts/smoke/run_body_pipeline_smoke_test.sh /absolute/path/to/image.jpg
```

Outputs are written under:

- `var/test-runs/sam3d-body-smoke/<run-name>/sam2/`
- `var/test-runs/sam3d-body-smoke/<run-name>/sam3d/`

## Manual step-by-step flow

Run SAM2 directly:

```bash
$HOME/miniconda3/envs/sam2-photo/bin/python scripts/run_sam2_person_mask.py \
  --image /absolute/path/to/image.jpg \
  --output-dir "$PWD/var/test-runs/manual-sam2" \
  --face-bbox 343.17,249.18,547.94,460.67 \
  --max-edge 1600
```

Then hand the bundle to SAM 3D Body:

```bash
PYTHONPATH="$PWD/third_party/sam-3d-body" \
  $HOME/miniconda3/envs/sam3d-body-photo/bin/python scripts/run_sam3d_body_from_bundle.py \
  --bundle "$PWD/var/test-runs/manual-sam2/sam2_bundle.npz" \
  --output-dir "$PWD/var/test-runs/manual-sam3d"
```

If weights are missing, the current scripts will still produce a dry-run summary so the
input handoff can be validated independently of the final 3D model inference.

## Notes

- `SAM 3D Body` is not installed as a normal pip package; run it with `PYTHONPATH` pointed at the repo root
- The first public version does not bundle large checkpoints or sample images
- `sam-3d-objects` support is experimental and follows the same local-checkpoint model
