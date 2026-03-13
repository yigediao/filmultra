SHELL := /usr/bin/env bash
ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

API_PORT ?= 8000
FRONTEND_PORT ?= 3000
TEST_API_PORT ?= 8013
TEST_FRONTEND_PORT ?= 3001
REVIEW_API_PORT ?= 8012
REVIEW_FRONTEND_PORT ?= $(TEST_FRONTEND_PORT)
SYNOLOGY_GVFS_ROOT ?= $(ROOT_DIR)/.gvfs_mounts/photo_byyear_2026_2_28
SAM3D_IMAGE ?= $(ROOT_DIR)/2026-3-7/389A5094.JPG
RUN_DIR ?=

.PHONY: help backend-dev frontend-dev smoke-sam3d-body smoke-synology-gvfs latest-synology-run review-synology-gvfs stop-review-synology-gvfs migrate-workspace project-status

help:
	@printf '%s\n' \
	  'backend-dev                 Start the FastAPI dev server on API_PORT (default: 8000)' \
	  'frontend-dev                Start the Next.js dev server on FRONTEND_PORT (default: 3000)' \
	  'smoke-sam3d-body            Run the body pipeline smoke test into var/test-runs/' \
	  'smoke-synology-gvfs         Run the Synology GVFS smoke test on TEST_API_PORT (default: 8013)' \
	  'latest-synology-run         Print the latest Synology GVFS smoke test directory' \
	  'review-synology-gvfs        Start a stable review stack on REVIEW_API_PORT/REVIEW_FRONTEND_PORT' \
	  'stop-review-synology-gvfs   Stop the review stack started by review-synology-gvfs' \
	  'migrate-workspace          Move legacy backend runtime outputs into var/' \
	  'project-status             Print the current managed workspace status'

backend-dev:
	cd "$(ROOT_DIR)/backend" && uvicorn app.main:app --reload --host 127.0.0.1 --port "$(API_PORT)"

frontend-dev:
	cd "$(ROOT_DIR)/frontend" && NEXT_PUBLIC_API_BASE="http://127.0.0.1:$(API_PORT)" npm run dev -- --hostname 127.0.0.1 --port "$(FRONTEND_PORT)"

smoke-sam3d-body:
	bash "$(ROOT_DIR)/scripts/smoke/run_body_pipeline_smoke_test.sh" "$(SAM3D_IMAGE)"

smoke-synology-gvfs:
	WAIT_FOR_FULL_PIPELINE="$${WAIT_FOR_FULL_PIPELINE:-1}" PORT="$(TEST_API_PORT)" bash "$(ROOT_DIR)/scripts/smoke/run_synology_gvfs_folder_smoke_test.sh" "$(SYNOLOGY_GVFS_ROOT)"

latest-synology-run:
	@latest="$$(find "$(ROOT_DIR)/var/test-runs/synology-gvfs" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort | tail -n 1)"; \
	if [[ -z "$$latest" ]]; then \
	  echo 'no Synology GVFS smoke test runs found under var/test-runs/synology-gvfs' >&2; \
	  exit 1; \
	fi; \
	echo "$$latest"

review-synology-gvfs:
	API_PORT="$(REVIEW_API_PORT)" WEB_PORT="$(REVIEW_FRONTEND_PORT)" bash "$(ROOT_DIR)/scripts/dev/start_synology_gvfs_review_stack.sh" "$(RUN_DIR)"

stop-review-synology-gvfs:
	bash "$(ROOT_DIR)/scripts/dev/stop_synology_gvfs_review_stack.sh"

migrate-workspace:
	bash "$(ROOT_DIR)/scripts/dev/migrate_workspace_layout.sh"

project-status:
	bash "$(ROOT_DIR)/scripts/dev/project_status.sh"
