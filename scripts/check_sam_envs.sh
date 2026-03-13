#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONDA_SH="${CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"

if [[ -f "$CONDA_SH" ]]; then
  source "$CONDA_SH"
  echo "[host conda envs]"
  conda env list
else
  echo "[host conda envs] conda.sh not found at $CONDA_SH"
fi

echo
echo "[host repos]"
for repo in "$ROOT_DIR/third_party/sam2" "$ROOT_DIR/third_party/sam-3d-body"; do
  if [[ -d "$repo/.git" ]]; then
    printf '%s: ' "$repo"
    git -C "$repo" rev-parse --short HEAD
  else
    printf '%s: missing\n' "$repo"
  fi
done

echo
echo "[container zed_noetic envs]"
docker exec zed_noetic bash -lc 'ls -d /opt/conda/envs/* 2>/dev/null || true'
