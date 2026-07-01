.DEFAULT_GOAL := dev

# Canonical environment. Required for app targets, baseline for dev.
# Optional: missing .env is not an error.
ifneq (,$(wildcard .env))
include .env
export
endif

# compose.override.yaml (auto-merged by docker compose) may remap the published
# host ports so parallel workspaces don't collide. It is the source of truth: when
# present, read the actual published ports straight from it so the banner and the
# host-side `make dev` flow can never diverge from what docker binds. Otherwise
# fall back to the conventional defaults.
ifneq (,$(wildcard compose.override.yaml))
WEBUI_URL_PORT     := $(shell sed -nE 's/.*"([0-9]+):8000".*/\1/p' compose.override.yaml | head -n1)
TEMPORAL_UI_PORT   := $(shell sed -nE 's/.*"([0-9]+):8233".*/\1/p' compose.override.yaml | head -n1)
TEMPORAL_GRPC_PORT := $(shell sed -nE 's/.*"([0-9]+):7233".*/\1/p' compose.override.yaml | head -n1)
# Point the host-side dev flow (uv run worker/webui) at the remapped ports.
TEMPORAL_ADDRESS   ?= localhost:$(TEMPORAL_GRPC_PORT)
WEBUI_PORT         ?= $(WEBUI_URL_PORT)
export TEMPORAL_ADDRESS WEBUI_PORT
else
WEBUI_URL_PORT     := 8000
TEMPORAL_UI_PORT   := 8233
endif

# Banner listing where to reach the running components.
define show_urls
	@echo ""
	@echo "The stack is up. Open:"
	@echo "  Web UI             http://localhost:$(WEBUI_URL_PORT)"
	@echo "  Temporal dashboard http://localhost:$(TEMPORAL_UI_PORT)"
endef

##@ Infra

.PHONY: infra-up
infra-up: ## Bring up the Temporal dev server
	docker compose up -d temporal

.PHONY: infra-down
infra-down: ## Stop the Temporal dev server (keeps container around)
	docker compose stop temporal

.PHONY: infra-logs
infra-logs: ## Follow logs from the Temporal dev server
	docker compose logs -f temporal

##@ App

.PHONY: worker
worker: ## Run the Temporal worker on the host with hot reload
	uv run worker

.PHONY: webui
webui: ## Run the FastAPI web UI on :8000 with hot reload
	uv run webui

.PHONY: dev
dev: .venv infra-up ## Start Temporal, then run worker + webui on the host with hot reload
	$(show_urls)
	@$(MAKE) -j worker webui

.venv: pyproject.toml uv.lock
	uv sync
	@touch .venv

##@ Stack

.PHONY: app-up
app-up: ## Bring up the full stack in Docker (temporal + worker + webui)
	docker compose up -d
	$(show_urls)

.PHONY: app-down
app-down: ## Tear down the full stack (removes containers and network)
	docker compose down

.PHONY: app-logs
app-logs: ## Follow logs from every stack container
	docker compose logs -f

##@ Helpers

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(firstword $(MAKEFILE_LIST))
