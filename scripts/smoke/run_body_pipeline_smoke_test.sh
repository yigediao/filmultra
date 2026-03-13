#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SAM2_PYTHON="${SAM2_PYTHON:-$HOME/miniconda3/envs/sam2-photo/bin/python}"
SAM3D_PYTHON="${SAM3D_PYTHON:-$HOME/miniconda3/envs/sam3d-body-photo/bin/python}"

IMAGE_PATH="${1:-}"
FACE_BBOX="${FACE_BBOX:-343.17,249.18,547.94,460.67}"
[[ -n "$IMAGE_PATH" ]] || {
  echo "usage: $0 /path/to/image.jpg" >&2
  echo "set FACE_BBOX=x1,y1,x2,y2 to override the default bbox" >&2
  exit 1
}
RUN_NAME="${RUN_NAME:-$(basename "${IMAGE_PATH%.*}")}"
BASE_OUTPUT_DIR="${BASE_OUTPUT_DIR:-$REPO_ROOT/var/test-runs/sam3d-body-smoke/$RUN_NAME}"
SAM2_OUTPUT_DIR="$BASE_OUTPUT_DIR/sam2"
SAM3D_OUTPUT_DIR="$BASE_OUTPUT_DIR/sam3d"

mkdir -p "$SAM2_OUTPUT_DIR" "$SAM3D_OUTPUT_DIR"

echo "[1/2] running SAM2 person mask smoke test"
"$SAM2_PYTHON" "$REPO_ROOT/scripts/run_sam2_person_mask.py" \
  --image "$IMAGE_PATH" \
  --output-dir "$SAM2_OUTPUT_DIR" \
  --face-bbox "$FACE_BBOX" \
  --max-edge 1600

echo
echo "[2/2] preparing SAM 3D Body handoff"
PYTHONPATH="$REPO_ROOT/third_party/sam-3d-body" \
"$SAM3D_PYTHON" "$REPO_ROOT/scripts/run_sam3d_body_from_bundle.py" \
  --bundle "$SAM2_OUTPUT_DIR/sam2_bundle.npz" \
  --output-dir "$SAM3D_OUTPUT_DIR"

echo
echo "smoke test outputs:"
echo "  $BASE_OUTPUT_DIR"
