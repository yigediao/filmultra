#!/usr/bin/env bash
set -Eeuo pipefail

STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/filmultra"
LOG_FILE="${STATE_DIR}/gio-mount.log"

mkdir -p "${STATE_DIR}"
exec >>"${LOG_FILE}" 2>&1

if [[ "$#" -gt 0 ]]; then
  TARGET_URIS=("$@")
elif [[ -n "${SYNOLOGY_AUTO_MOUNT_URIS:-}" ]]; then
  mapfile -t TARGET_URIS < <(printf '%s\n' "${SYNOLOGY_AUTO_MOUNT_URIS}" | tr ',' '\n' | sed '/^$/d')
else
  echo "usage: $0 smb://user@host/share [smb://user@host/share ...]"
  echo "or set SYNOLOGY_AUTO_MOUNT_URIS=smb://user@host/share,smb://user@host/share"
  exit 1
fi

mount_uri() {
  local uri="$1"
  local attempt

  echo "[$(date -Is)] starting auto-mount for ${uri}"
  for attempt in $(seq 1 5); do
    echo "[$(date -Is)] attempt ${attempt} for ${uri}"
    if gio mount "${uri}"; then
      echo "[$(date -Is)] mount succeeded for ${uri}"
      return 0
    fi
    sleep 4
  done

  echo "[$(date -Is)] mount failed after retries for ${uri}"
  return 1
}

# Give GNOME session, keyring, and network a moment to come up.
sleep 8

FAILURES=0
for uri in "${TARGET_URIS[@]}"; do
  if ! mount_uri "${uri}"; then
    FAILURES=$((FAILURES + 1))
  fi
done

if [[ "${FAILURES}" -gt 0 ]]; then
  echo "[$(date -Is)] auto-mount completed with ${FAILURES} failure(s)"
  exit 1
fi

echo "[$(date -Is)] auto-mount completed successfully"
exit 0
