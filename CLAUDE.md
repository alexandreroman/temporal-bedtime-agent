# CLAUDE.md

## Project overview

See [README.md](README.md) for the project architecture and instructions to run the app.

You MUST follow the instructions in [README.md](README.md) to build, run, and debug the application. This includes the Development section for local workflow and debugging guidance.

Always use `docker-compose` (hyphenated) instead of `docker compose` (space-separated).

The worker and webui logs are in JSON format (via structlog). Use `jq` or similar tools to filter and analyze log output.

## Bash usage

Do not use compound commands (`&&`) in Bash tool calls. Run each command separately instead.

## Temporal workflows

Use the `temporal` CLI to analyze or debug Temporal workflows (e.g. `temporal workflow list`, `temporal workflow describe`, `temporal workflow show`).

## Language

All generated text (code comments, commit messages, documentation, PR descriptions, etc.) must be written in English.
