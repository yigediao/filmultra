#!/usr/bin/env bash
set -Eeuo pipefail

HOST="${1:-${SYNOLOGY_HOST:-}}"
SHARE="${2:-}"
MOUNT_POINT="${3:-/mnt/photo_library}"

log() {
  printf '[mount-synology] %s\n' "$*"
}

die() {
  printf '[mount-synology] ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  if [[ -n "${CRED_FILE:-}" && -f "${CRED_FILE:-}" ]]; then
    rm -f "${CRED_FILE}"
  fi
}

trap cleanup EXIT

command -v bash >/dev/null 2>&1 || die "bash is required"
command -v smbclient >/dev/null 2>&1 || die "smbclient is required"
[[ -n "${HOST}" ]] || die "host is required as the first argument or via SYNOLOGY_HOST"

if ! ping -c 1 -W 1 "${HOST}" >/dev/null 2>&1; then
  die "host ${HOST} is unreachable"
fi

if ! timeout 3 bash -lc "cat < /dev/null > /dev/tcp/${HOST}/445" 2>/dev/null; then
  die "host ${HOST} is reachable but TCP 445 is closed"
fi

read -r -p "Synology username: " SMB_USERNAME
[[ -n "${SMB_USERNAME}" ]] || die "username is required"

read -r -s -p "Synology password: " SMB_PASSWORD
printf '\n'
[[ -n "${SMB_PASSWORD}" ]] || die "password is required"

log "Verifying sudo access"
sudo -v

if ! command -v mount.cifs >/dev/null 2>&1; then
  log "Installing cifs-utils"
  sudo apt-get update
  sudo apt-get install -y cifs-utils
fi

sudo mkdir -p "${MOUNT_POINT}"

if mountpoint -q "${MOUNT_POINT}"; then
  log "Unmounting existing mount at ${MOUNT_POINT}"
  sudo umount "${MOUNT_POINT}"
fi

CRED_FILE="$(mktemp)"
chmod 600 "${CRED_FILE}"
cat > "${CRED_FILE}" <<EOF
username=${SMB_USERNAME}
password=${SMB_PASSWORD}
EOF

if [[ -z "${SHARE}" ]]; then
  log "Available shares on ${HOST}:"
  smbclient -g -A "${CRED_FILE}" -L "${HOST}" -m SMB3 2>/dev/null \
    | awk -F'|' '$1 == "Disk" { print "  - " $2 }'
  read -r -p "Synology share name: " SHARE
fi
[[ -n "${SHARE}" ]] || die "share name is required"

log "Checking share access with smbclient"
if ! smbclient -A "${CRED_FILE}" "//${HOST}/${SHARE}" -m SMB3 -c 'ls' >/dev/null; then
  die "authentication failed or share //${HOST}/${SHARE} does not exist"
fi

UID_VALUE="$(id -u)"
GID_VALUE="$(id -g)"
MOUNTED=0

for vers in 3.1.1 3.0 2.1 2.0; do
  log "Trying SMB version ${vers}"
  if sudo mount -t cifs "//${HOST}/${SHARE}" "${MOUNT_POINT}" \
    -o "credentials=${CRED_FILE},vers=${vers},uid=${UID_VALUE},gid=${GID_VALUE},iocharset=utf8,ro,noserverino,file_mode=0444,dir_mode=0555"; then
    MOUNTED=1
    break
  fi
done

[[ "${MOUNTED}" -eq 1 ]] || die "mount failed for all SMB protocol versions"

log "Mounted //${HOST}/${SHARE} at ${MOUNT_POINT}"
log "Top-level entries:"
find "${MOUNT_POINT}" -maxdepth 1 -mindepth 1 | sed -n '1,20p'
