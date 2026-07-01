# CLAUDE.md

## Project overview

See [README.md](README.md) for the project architecture and instructions to run the app.

You MUST follow the instructions in [README.md](README.md) to build, run, and debug the application. This includes the Development section for local workflow and debugging guidance.

Always use `docker compose` (space-separated) instead of `docker-compose` (hyphenated).

The worker and webui logs are in JSON format (via structlog). Use `jq` or similar tools to filter and analyze log output.

### Code layout

- **`agent/`** — the pure Pydantic AI agent. It MUST stay free of any Temporal dependency or concept (no `temporal`, `workflow`, `activity`, `durable`, even in comments). Holds the system prompt (`prompt.py`), the `StoryResponse` schema and `story_agent` (`__init__.py`), the multi-turn flow as a `Conversation` (`conversation.py`), and a standalone CLI (`uv run agent`).
- **`worker/`** — the Temporal/durability layer. `durable_agent.py` wraps `story_agent` in a `TemporalAgent`; the workflow reuses the agent's `Conversation`. Dependency is one-directional: `worker` → `agent`, never the reverse.

## Bash usage

Do not use compound commands (`&&`) in Bash tool calls. Run each command separately instead.

## Temporal workflows

Use the `temporal` CLI to analyze or debug Temporal workflows (e.g. `temporal workflow list`, `temporal workflow describe`, `temporal workflow show`).

## Language

All generated text (code comments, commit messages, documentation, PR descriptions, etc.) must be written in English.

## LLM agent behavior changes

When asked to change agent behavior driven by an LLM (language switching, tone, decision logic, output structure, etc.), constrain solutions to:

1. **Prompt-only or schema-only.** Do not add Python heuristics that pre-process or inspect user input to make decisions the LLM should make (e.g. stop-word language detectors, regex-based intent classifiers). The LLM must do the work; shape it via the system prompt (`agent/prompt.py`), the per-turn hints (`agent/conversation.py`), and the Pydantic field descriptions (`StoryResponse` in `agent/__init__.py`).
2. **Vendor-agnostic.** The solution must work on both OpenAI and Anthropic via pydantic-ai (`PYDANTIC_AI_MODEL` is swappable). No provider-specific knobs. Reordering Pydantic schema fields IS acceptable — both vendors emit JSON in declaration order in practice, so placing a field like `language` first forces the model to commit to it before generating dependent prose.

If a behavior cannot be achieved by prompt alone, surface that as a tradeoff rather than silently adding heuristic code.
