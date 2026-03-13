#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
ROOT_PATH="${1:-${REPO_ROOT}/.gvfs_mounts/photo_byyear_2026_2_28}"
PORT="${PORT:-8013}"
WAIT_FOR_FULL_PIPELINE="${WAIT_FOR_FULL_PIPELINE:-0}"
RUN_ID="$(date +%Y%m%d%H%M%S)"
ROOT_LABEL="$(basename "${ROOT_PATH}" | tr -cs 'A-Za-z0-9._-' '_')"
RUN_DIR="${REPO_ROOT}/var/test-runs/synology-gvfs/${RUN_ID}_${ROOT_LABEL}"
DB_FILE="${RUN_DIR}/photo_dam.db"
PREVIEW_DIR="${RUN_DIR}/preview_cache"
LOG_FILE="${RUN_DIR}/backend.log"
SUMMARY_FILE="${RUN_DIR}/summary.json"
API_BASE="http://127.0.0.1:${PORT}"
FACE_MODELS_DIR="${REPO_ROOT}/var/cache/backend/synology-smoke-face-models"
SERVER_PID=""

log() {
  printf '[synology-gvfs-test] %s\n' "$*"
}

ensure_port_available() {
  python3 - <<'PY' "$1"
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind(("127.0.0.1", port))
except OSError:
    print(f"port {port} is already in use", file=sys.stderr)
    sys.exit(1)
finally:
    sock.close()
PY
}

stop_pid() {
  local pid="$1"
  local attempt

  [[ -n "${pid}" ]] || return 0
  if ! kill -0 "${pid}" 2>/dev/null; then
    wait "${pid}" 2>/dev/null || true
    return 0
  fi

  kill "${pid}" 2>/dev/null || true
  for attempt in $(seq 1 20); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      wait "${pid}" 2>/dev/null || true
      return 0
    fi
    sleep 0.25
  done

  kill -9 "${pid}" 2>/dev/null || true
  wait "${pid}" 2>/dev/null || true
}

cleanup() {
  stop_pid "${SERVER_PID}"
}

trap cleanup EXIT

[[ -d "${ROOT_PATH}" ]] || {
  printf '[synology-gvfs-test] ERROR: root path not found: %s\n' "${ROOT_PATH}" >&2
  exit 1
}
ensure_port_available "${PORT}"

mkdir -p "${RUN_DIR}" "${PREVIEW_DIR}"
mkdir -p "${FACE_MODELS_DIR}"

cd "${BACKEND_DIR}"

log "Starting backend for ${ROOT_PATH}"
AUTO_CREATE_TABLES=true \
AUTO_SCAN_ENABLED=false \
DATABASE_URL="sqlite:///${DB_FILE}" \
PHOTO_LIBRARY_ROOT="${ROOT_PATH}" \
PREVIEW_CACHE_DIR="${PREVIEW_DIR}" \
FACE_MODELS_DIR="${FACE_MODELS_DIR}" \
uvicorn app.main:app --host 127.0.0.1 --port "${PORT}" >"${LOG_FILE}" 2>&1 &
SERVER_PID=$!

python3 - <<'PY' "${API_BASE}"
import sys
import time
from urllib.request import urlopen

api_base = sys.argv[1]
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with urlopen(f"{api_base}/healthz", timeout=2) as response:
            if response.status == 200:
                sys.exit(0)
    except Exception:
        time.sleep(1)
print("backend did not become healthy in time", file=sys.stderr)
sys.exit(1)
PY

JOB_ID="$(python3 - <<'PY' "${API_BASE}" "${ROOT_PATH}"
import json
import sys
from urllib.request import Request, urlopen

api_base, root_path = sys.argv[1], sys.argv[2]
payload = json.dumps({"root_path": root_path}).encode("utf-8")
request = Request(
    f"{api_base}/api/jobs/scan",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urlopen(request, timeout=30) as response:
    data = json.load(response)
print(data["id"])
PY
)"

log "Created scan job ${JOB_ID}"

if [[ "${WAIT_FOR_FULL_PIPELINE}" == "1" ]]; then
python3 - <<'PY' "${API_BASE}" "${JOB_ID}"
import json
import sys
import time
from urllib.request import urlopen

api_base, job_id = sys.argv[1], sys.argv[2]
deadline = time.time() + 1800
last_status = None
face_job_id = None
while time.time() < deadline:
    with urlopen(f"{api_base}/api/jobs/{job_id}", timeout=30) as response:
        payload = json.load(response)
    status = payload["status"]
    if status != last_status:
        print(f"[synology-gvfs-test] job {job_id} status={status}")
        last_status = status
    if status == "failed":
        print(json.dumps(payload))
        sys.exit(2)
    if status == "completed":
        result = payload.get("result_json") or {}
        face_job_id = result.get("auto_face_detect_job_id")
        break
    time.sleep(5)
else:
    print(f"job {job_id} timed out", file=sys.stderr)
    sys.exit(1)

if not face_job_id:
    print(json.dumps(payload))
    sys.exit(0)

last_face_status = None
while time.time() < deadline:
    with urlopen(f"{api_base}/api/jobs/{face_job_id}", timeout=30) as response:
        face_payload = json.load(response)
    face_status = face_payload["status"]
    if face_status != last_face_status:
        print(f"[synology-gvfs-test] face job {face_job_id} status={face_status}")
        last_face_status = face_status
    if face_status in {"completed", "failed"}:
        print(json.dumps({"scan_job": payload, "face_job": face_payload}))
        sys.exit(0 if face_status == "completed" else 2)
    time.sleep(5)

print(f"face job {face_job_id} timed out", file=sys.stderr)
sys.exit(1)
PY
else
python3 - <<'PY' "${API_BASE}" "${DB_FILE}" "${JOB_ID}"
import json
import sqlite3
import sys
import time
from urllib.request import urlopen

api_base, db_path, job_id = sys.argv[1:4]
deadline = time.time() + 600
while time.time() < deadline:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    logical_assets = cur.execute("select count(*) from logical_assets").fetchone()[0]
    physical_files = cur.execute("select count(*) from physical_files").fetchone()[0]
    job_rows = cur.execute(
        "select id, job_type, status from jobs order by id"
    ).fetchall()
    conn.close()
    with urlopen(f"{api_base}/api/jobs/{job_id}", timeout=30) as response:
        scan_job = json.load(response)
    if logical_assets > 0 and physical_files > 0 and scan_job["status"] == "completed":
        print(
            f"[synology-gvfs-test] scan completed with visible assets: "
            f"logical_assets={logical_assets}, physical_files={physical_files}, jobs={job_rows}"
        )
        sys.exit(0)
    if scan_job["status"] == "failed":
        print(f"scan job {job_id} failed: {scan_job.get('error_message')}", file=sys.stderr)
        sys.exit(2)
    time.sleep(2)
print("timed out waiting for completed scan and visible assets", file=sys.stderr)
sys.exit(1)
PY
fi

python3 - <<'PY' "${API_BASE}" "${ROOT_PATH}" "${DB_FILE}" "${PREVIEW_DIR}" "${LOG_FILE}" "${SUMMARY_FILE}"
import json
import sys
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

from PIL import Image
import sqlite3

api_base, root_path, db_file, preview_dir, log_file, summary_file = sys.argv[1:7]

with urlopen(f"{api_base}/api/jobs") as response:
    jobs = json.load(response)
scan_job = next(job for job in jobs if job["job_type"] == "scan")
face_job = next((job for job in jobs if job["job_type"] == "face_detect"), None)
result = scan_job["result_json"] or {}

with urlopen(f"{api_base}/api/assets?limit=3") as response:
    assets = json.load(response)
if not assets:
    raise SystemExit("no assets returned from /api/assets")

first_asset_id = assets[0]["id"]
with urlopen(f"{api_base}/api/assets/{first_asset_id}") as response:
    asset_detail = json.load(response)

hero_file_id = asset_detail["hero_file_id"]
with urlopen(f"{api_base}/api/files/{hero_file_id}/preview") as response:
    preview_bytes = response.read()

image = Image.open(BytesIO(preview_bytes))
conn = sqlite3.connect(db_file)
cur = conn.cursor()
logical_assets = cur.execute("select count(*) from logical_assets").fetchone()[0]
physical_files = cur.execute("select count(*) from physical_files").fetchone()[0]
faces = cur.execute("select count(*) from faces").fetchone()[0]
conn.close()
summary = {
    "root_path": root_path,
    "db_file": db_file,
    "preview_dir": preview_dir,
    "log_file": log_file,
    "scan_job_id": scan_job["id"],
    "scan_status": scan_job["status"],
    "face_job_id": face_job["id"] if face_job else None,
    "face_job_status": face_job["status"] if face_job else None,
    "scanned_files": result.get("scanned_files"),
    "created_assets": result.get("created_assets"),
    "created_files": result.get("created_files"),
    "pending_face_detection_assets": result.get("pending_face_detection_assets"),
    "logical_assets_in_db": logical_assets,
    "physical_files_in_db": physical_files,
    "faces_in_db": faces,
    "first_asset_id": first_asset_id,
    "first_asset_display_name": asset_detail["display_name"],
    "first_asset_file_count": len(asset_detail["physical_files"]),
    "preview_format": image.format,
    "preview_size": list(image.size),
    "preview_bytes": len(preview_bytes),
}
Path(summary_file).write_text(json.dumps(summary, ensure_ascii=True, indent=2) + "\n")
print(json.dumps(summary, ensure_ascii=True, indent=2))
PY

log "Run directory: ${RUN_DIR}"
log "Summary file: ${SUMMARY_FILE}"
