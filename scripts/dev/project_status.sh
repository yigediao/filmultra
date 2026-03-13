#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RUNS_DIR="${REPO_ROOT}/var/test-runs/synology-gvfs"

printf 'Repo: %s\n' "${REPO_ROOT}"
printf 'Backend env example: %s\n' "${REPO_ROOT}/backend/.env.example"
printf 'Frontend env example: %s\n' "${REPO_ROOT}/frontend/.env.local.example"
printf '\n'

printf 'Latest Synology GVFS run:\n'
latest_run="$(find "${RUNS_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1 || true)"
if [[ -n "${latest_run}" ]]; then
  printf '  %s\n' "${latest_run}"
else
  printf '  (none)\n'
fi
printf '\n'

printf 'Managed workspace roots:\n'
for path in \
  "${REPO_ROOT}/var/runtime/backend" \
  "${REPO_ROOT}/var/cache/backend" \
  "${REPO_ROOT}/var/artifacts" \
  "${REPO_ROOT}/var/legacy/backend-runtime"; do
  if [[ -e "${path}" ]]; then
    printf '  present  %s\n' "${path}"
  else
    printf '  missing  %s\n' "${path}"
  fi
done
printf '\n'

printf 'Backend legacy leftovers:\n'
leftovers="$(find "${REPO_ROOT}/backend" -maxdepth 1 \( -name '*.db' -o -name '*.log' -o -name 'preview_cache*' -o -name 'model_cache*' -o -name 'artifacts' \) | sort)"
if [[ -n "${leftovers}" ]]; then
  printf '%s\n' "${leftovers}" | sed 's/^/  /'
else
  printf '  (none)\n'
fi
printf '\n'

printf 'Known dev ports:\n'
ss -ltnp '( sport = :3000 or sport = :3001 or sport = :8000 or sport = :8012 )' 2>/dev/null || true
