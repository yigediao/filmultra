#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
ENV_NAME="${ENV_NAME:-sam2-photo}"
REPO_DIR="${REPO_DIR:-$ROOT_DIR/third_party/sam2}"
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cu124}"
SAM2_BUILD_CUDA="${SAM2_BUILD_CUDA:-0}"

if [[ ! -f "$CONDA_SH" ]]; then
  echo "conda.sh not found at $CONDA_SH" >&2
  exit 1
fi

if [[ ! -d "$REPO_DIR" ]]; then
  echo "SAM2 repo not found at $REPO_DIR" >&2
  exit 1
fi

source "$CONDA_SH"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -y -n "$ENV_NAME" "python=$PYTHON_VERSION"
fi

ENV_PYTHON="$HOME/miniconda3/envs/$ENV_NAME/bin/python"

if [[ ! -x "$ENV_PYTHON" ]]; then
  echo "Environment python not found at $ENV_PYTHON" >&2
  exit 1
fi

PYTHONNOUSERSITE=1 "$ENV_PYTHON" -s -m pip install --upgrade pip setuptools wheel
PYTHONNOUSERSITE=1 "$ENV_PYTHON" -s -m pip install --progress-bar off --no-user torch==2.5.1 torchvision==0.20.1 --index-url "$TORCH_INDEX_URL"

pushd "$REPO_DIR" >/dev/null
PYTHONNOUSERSITE=1 SAM2_BUILD_CUDA="$SAM2_BUILD_CUDA" "$ENV_PYTHON" -s -m pip install --progress-bar off --no-user --no-build-isolation -e .
popd >/dev/null

echo "SAM2 environment ready: $ENV_NAME"
