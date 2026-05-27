.DEFAULT_GOAL := dev

# Canonical environment. Required for app targets, baseline for dev.
# Optional: missing .env is not an error.
ifneq (,$(wildcard .env))
include .env
export
endif

##@ Infra

.PHONY: infra-up
infra-up: ## Bring up the Temporal dev server
	docker-compose up -d temporal

.PHONY: infra-down
infra-down: ## Stop the Temporal dev server (keeps container around)
	docker-compose stop temporal

.PHONY: infra-logs
infra-logs: ## Follow logs from the Temporal dev server
	docker-compose logs -f temporal

##@ App

.PHONY: worker
worker: ## Run the Temporal worker on the host with hot reload
	uv run worker

.PHONY: webui
webui: ## Run the FastAPI web UI on :8000 with hot reload
	uv run webui

.PHONY: dev
dev: .venv infra-up ## Start Temporal, then run worker + webui on the host with hot reload
	@$(MAKE) -j worker webui

.venv: pyproject.toml uv.lock
	uv sync
	@touch .venv

##@ Stack

.PHONY: app-up
app-up: ## Bring up the full stack in Docker (temporal + worker + webui)
	docker-compose up -d --build

.PHONY: app-down
app-down: ## Tear down the full stack (removes containers and network)
	docker-compose down

.PHONY: app-logs
app-logs: ## Follow logs from every stack container
	docker-compose logs -f

##@ Helpers

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(firstword $(MAKEFILE_LIST))
