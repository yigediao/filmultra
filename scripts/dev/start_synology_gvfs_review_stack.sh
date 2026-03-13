#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
FRONTEND_DIR="${REPO_ROOT}/frontend"
RUNS_DIR="${REPO_ROOT}/var/test-runs/synology-gvfs"
STATE_DIR="${REPO_ROOT}/var/run/synology-gvfs-review"
LOG_DIR="${REPO_ROOT}/var/logs/synology-gvfs-review"
API_PORT="${API_PORT:-8012}"
WEB_PORT="${WEB_PORT:-3001}"
RUN_DIR="${1:-}"
FACE_MODELS_DIR="${REPO_ROOT}/var/cache/backend/synology-smoke-face-models"
BACKEND_PID_FILE="${STATE_DIR}/backend.pid"
FRONTEND_PID_FILE="${STATE_DIR}/frontend.pid"
BACKEND_LOG="${LOG_DIR}/backend.log"
FRONTEND_LOG="${LOG_DIR}/frontend.log"
FRONTEND_BUILD_LOG="${LOG_DIR}/frontend-build.log"

log() {
  printf '[review-stack] %s\n' "$*"
}

start_process() {
  local pid_file="$1"
  shift
  local pid

  pid="$(python3 - <<'PY' "$@"
import json
import os
import subprocess
import sys

cwd = sys.argv[1]
log_file = sys.argv[2]
command = sys.argv[3:]

env = os.environ.copy()
overrides = json.loads(env.pop("PROCESS_ENV_OVERRIDES"))
env.update(overrides)

with open(log_file, "ab", buffering=0) as handle:
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

print(process.pid)
PY
)"
  printf '%s\n' "${pid}" > "${pid_file}"
}

stop_pid_file() {
  local pid_file="$1"
  local pid
  local attempt

  if [[ -f "${pid_file}" ]]; then
    pid="$(cat "${pid_file}")"
    if [[ -n "${pid}" ]] && kill -0 -- "-${pid}" 2>/dev/null; then
      kill -TERM -- "-${pid}" 2>/dev/null || true
      for attempt in $(seq 1 20); do
        if ! kill -0 -- "-${pid}" 2>/dev/null; then
          break
        fi
        sleep 0.25
      done
      if kill -0 -- "-${pid}" 2>/dev/null; then
        kill -KILL -- "-${pid}" 2>/dev/null || true
      fi
    fi
    wait "${pid}" 2>/dev/null || true
    rm -f "${pid_file}"
  fi
}

mkdir -p "${STATE_DIR}" "${LOG_DIR}"
mkdir -p "${FACE_MODELS_DIR}"

if [[ -z "${RUN_DIR}" ]]; then
  RUN_DIR="$(find "${RUNS_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1 || true)"
fi

[[ -n "${RUN_DIR}" ]] || {
  printf '[review-stack] ERROR: no Synology GVFS run directory found under %s\n' "${RUNS_DIR}" >&2
  exit 1
}

SUMMARY_FILE="${RUN_DIR}/summary.json"
DB_FILE="${RUN_DIR}/photo_dam.db"
PREVIEW_DIR="${RUN_DIR}/preview_cache"

[[ -f "${SUMMARY_FILE}" ]] || {
  printf '[review-stack] ERROR: missing summary file: %s\n' "${SUMMARY_FILE}" >&2
  exit 1
}
[[ -f "${DB_FILE}" ]] || {
  printf '[review-stack] ERROR: missing database file: %s\n' "${DB_FILE}" >&2
  exit 1
}
[[ -d "${PREVIEW_DIR}" ]] || {
  printf '[review-stack] ERROR: missing preview cache dir: %s\n' "${PREVIEW_DIR}" >&2
  exit 1
}

ROOT_PATH="$(python3 - <<'PY' "${SUMMARY_FILE}"
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(payload["root_path"])
PY
)"

stop_pid_file "${BACKEND_PID_FILE}"
stop_pid_file "${FRONTEND_PID_FILE}"

: > "${BACKEND_LOG}"
: > "${FRONTEND_LOG}"
: > "${FRONTEND_BUILD_LOG}"

log "Starting backend from ${RUN_DIR}"
PROCESS_ENV_OVERRIDES="$(python3 - <<'PY' "${DB_FILE}" "${ROOT_PATH}" "${PREVIEW_DIR}" "${FACE_MODELS_DIR}"
import json
import sys

payload = {
    "DATABASE_URL": f"sqlite:///{sys.argv[1]}",
    "PHOTO_LIBRARY_ROOT": sys.argv[2],
    "PREVIEW_CACHE_DIR": sys.argv[3],
    "FACE_MODELS_DIR": sys.argv[4],
    "AUTO_SCAN_ENABLED": "false",
}
print(json.dumps(payload))
PY
)" start_process "${BACKEND_PID_FILE}" "${BACKEND_DIR}" "${BACKEND_LOG}" uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT}"

python3 - <<'PY' "${API_PORT}"
import sys
import time
from urllib.request import urlopen

port = sys.argv[1]
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as response:
            if response.status == 200:
                sys.exit(0)
    except Exception:
        time.sleep(1)
print("backend did not become healthy in time", file=sys.stderr)
sys.exit(1)
PY

log "Building frontend for stable review"
rm -rf "${FRONTEND_DIR}/.next"
if ! (
  cd "${FRONTEND_DIR}"
  NEXT_PUBLIC_API_BASE="http://127.0.0.1:${API_PORT}" \
  NEXT_TELEMETRY_DISABLED=1 \
  ./node_modules/.bin/next build >"${FRONTEND_BUILD_LOG}" 2>&1
); then
  printf '[review-stack] ERROR: frontend build failed, see %s\n' "${FRONTEND_BUILD_LOG}" >&2
  tail -n 80 "${FRONTEND_BUILD_LOG}" >&2 || true
  exit 1
fi

log "Starting frontend on port ${WEB_PORT}"
PROCESS_ENV_OVERRIDES="$(python3 - <<'PY' "${API_PORT}"
import json
import sys

print(
    json.dumps(
        {
            "NEXT_PUBLIC_API_BASE": f"http://127.0.0.1:{sys.argv[1]}",
            "NEXT_TELEMETRY_DISABLED": "1",
        }
    )
)
PY
)" start_process "${FRONTEND_PID_FILE}" "${FRONTEND_DIR}" "${FRONTEND_LOG}" ./node_modules/.bin/next start --hostname 127.0.0.1 --port "${WEB_PORT}"

python3 - <<'PY' "${WEB_PORT}"
import sys
import time
from urllib.request import urlopen

port = sys.argv[1]
deadline = time.time() + 90
while time.time() < deadline:
    try:
        with urlopen(f"http://127.0.0.1:{port}", timeout=2) as response:
            if response.status == 200:
                sys.exit(0)
    except Exception:
        time.sleep(1)
print("frontend did not become ready in time", file=sys.stderr)
sys.exit(1)
PY

log "Review stack ready"
log "Frontend: http://127.0.0.1:${WEB_PORT}"
log "Backend:  http://127.0.0.1:${API_PORT}"
log "Run dir:  ${RUN_DIR}"
log "Logs:     ${BACKEND_LOG} ${FRONTEND_LOG} ${FRONTEND_BUILD_LOG}"
