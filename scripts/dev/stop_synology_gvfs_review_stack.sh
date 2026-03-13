#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
STATE_DIR="${REPO_ROOT}/var/run/synology-gvfs-review"

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
      printf '[review-stack] stopped pid %s from %s\n' "${pid}" "${pid_file}"
    fi
    wait "${pid}" 2>/dev/null || true
    rm -f "${pid_file}"
  fi
}

stop_pid_file "${STATE_DIR}/backend.pid"
stop_pid_file "${STATE_DIR}/frontend.pid"
