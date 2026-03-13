#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
VAR_DIR="${REPO_ROOT}/var"
RUNTIME_DIR="${VAR_DIR}/runtime/backend"
CACHE_DIR="${VAR_DIR}/cache/backend"
ARTIFACTS_DIR="${VAR_DIR}/artifacts"
LEGACY_DIR="${VAR_DIR}/legacy/backend-runtime/$(date +%Y%m%d%H%M%S)"

log() {
  printf '[workspace-migrate] %s\n' "$*"
}

move_if_exists() {
  local src="$1"
  local dst="$2"
  local child
  local base

  [[ -e "${src}" ]] || return 0
  if [[ -e "${dst}" ]]; then
    if [[ -d "${src}" && -d "${dst}" ]]; then
      while IFS= read -r -d '' child; do
        base="$(basename "${child}")"
        move_if_exists "${child}" "${dst}/${base}"
      done < <(find "${src}" -mindepth 1 -maxdepth 1 -print0)
      rmdir "${src}" 2>/dev/null || true
      log "merged ${src} into ${dst}"
      return 0
    fi

    log "skip existing target: ${dst}"
    return 0
  fi

  mkdir -p "$(dirname "${dst}")"
  mv "${src}" "${dst}"
  log "moved ${src} -> ${dst}"
}

archive_if_exists() {
  local src="$1"
  local dst="$2"

  [[ -e "${src}" ]] || return 0
  mkdir -p "$(dirname "${dst}")"
  mv "${src}" "${dst}"
  log "archived ${src} -> ${dst}"
}

mkdir -p \
  "${RUNTIME_DIR}" \
  "${CACHE_DIR}" \
  "${CACHE_DIR}/synology-smoke-face-models" \
  "${ARTIFACTS_DIR}" \
  "${VAR_DIR}/runtime" \
  "${VAR_DIR}/cache" \
  "${VAR_DIR}/legacy/backend-runtime"

move_if_exists "${BACKEND_DIR}/photo_dam.db" "${RUNTIME_DIR}/photo_dam.db"
move_if_exists "${BACKEND_DIR}/preview_cache" "${RUNTIME_DIR}/preview_cache"
move_if_exists "${BACKEND_DIR}/model_cache" "${CACHE_DIR}/face-models"
move_if_exists "${BACKEND_DIR}/model_cache_synology_smb_test" "${CACHE_DIR}/synology-smoke-face-models"

if [[ -d "${BACKEND_DIR}/artifacts" ]]; then
  mkdir -p "${ARTIFACTS_DIR}"
  while IFS= read -r -d '' child; do
    base="$(basename "${child}")"
    move_if_exists "${child}" "${ARTIFACTS_DIR}/${base}"
  done < <(find "${BACKEND_DIR}/artifacts" -mindepth 1 -maxdepth 1 -print0)
  rmdir "${BACKEND_DIR}/artifacts" 2>/dev/null || true
fi

for path in \
  "${BACKEND_DIR}"/photo_dam_synology_gvfs_*.db \
  "${BACKEND_DIR}"/photo_dam_synology_smb_test.db \
  "${BACKEND_DIR}"/*.log \
  "${BACKEND_DIR}"/preview_cache_synology_* \
  "${BACKEND_DIR}"/preview_cache_*; do
  [[ -e "${path}" ]] || continue
  archive_if_exists "${path}" "${LEGACY_DIR}/$(basename "${path}")"
done

log "workspace migration complete"
log "runtime dir: ${RUNTIME_DIR}"
log "cache dir:   ${CACHE_DIR}"
log "artifacts:   ${ARTIFACTS_DIR}"
if [[ -d "${LEGACY_DIR}" ]]; then
  log "legacy archive: ${LEGACY_DIR}"
fi
