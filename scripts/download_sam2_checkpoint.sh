#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-$ROOT_DIR/third_party/sam2/checkpoints}"
MODEL_NAME="${MODEL_NAME:-sam2.1_hiera_large.pt}"
BASE_URL="${BASE_URL:-https://dl.fbaipublicfiles.com/segment_anything_2/092824}"

mkdir -p "$CHECKPOINT_DIR"

TARGET_PATH="$CHECKPOINT_DIR/$MODEL_NAME"
if [[ -f "$TARGET_PATH" ]]; then
  echo "Checkpoint already exists: $TARGET_PATH"
  exit 0
fi

curl -L "$BASE_URL/$MODEL_NAME" -o "$TARGET_PATH"
echo "Downloaded: $TARGET_PATH"
