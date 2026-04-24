# Temporal Bedtime Agent

An interactive bedtime story creation agent powered by [Temporal](https://temporal.io/) durable execution and [Anthropic](https://www.anthropic.com/) LLM.

The agent guides you through a conversation to collaboratively create a personalized bedtime story, complete with AI-generated illustrations.

![Story creation](story.png)

![Temporal dashboard](temporal.png)

## Features

- Conversational story creation (character, theme, special elements)
- AI-generated bedtime stories (3 paragraphs)
- Automatic illustration generation from story descriptions
- Durable execution via Temporal (workflows survive failures and restarts)
- Multi-language support (the agent detects the user's language)

## Architecture

```mermaid
graph LR
    A[Browser UI<br/>SPA] <-->|REST| B[FastAPI<br/>webui]
    B <--> C[Temporal Server]
    C <--> D[Temporal Worker<br/>workflows + activities]
    D -->|Story text| E[LLM<br/>OpenAI gpt-5.4-nano]
    D -->|Illustration| F[OpenAI Images API<br/>gpt-image-2]
```

- **Web UI (webui)** — FastAPI backend that serves the single-page app and exposes a REST API. It receives user messages and forwards them to Temporal as signals.
- **Temporal Server** — Orchestrates the story creation workflow with durable execution. It guarantees that workflows survive failures and restarts, and coordinates communication between the web UI and the worker.
- **Worker** — Executes the workflows and activities. It drives the conversational flow, calls the configured LLM to generate story text, and calls OpenAI to generate illustrations.

## Why Temporal?

Temporal brings [durable execution](https://temporal.io/how-temporal-works) to this project: the workflow state is automatically persisted, so the story creation process is resilient to failures without any custom recovery logic.

Here are a few scenarios where Temporal makes a difference:

- **Worker crashes mid-story** — The user is chatting with the agent and the worker process crashes (OOM, deployment, bug). Without Temporal, the entire conversation and story progress would be lost. With Temporal, the workflow state is preserved: when the worker restarts, the conversation resumes exactly where it left off.
- **LLM API timeout** — A call to Claude or OpenAI times out or returns a transient error. Temporal automatically retries the failed activity with configurable backoff, without duplicating work that already succeeded (e.g., the story text is not regenerated if only the illustration call failed).
- **Long-running interaction** — A user starts a story, closes the browser, and comes back hours later. The workflow keeps waiting for the next user message; there is no session timeout to manage and no state to serialize to a database.
- **Multiple workers** — In production, several worker instances can run in parallel. Temporal dispatches activities across workers and guarantees exactly-once execution, making the system horizontally scalable with no extra coordination code.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager
- **Temporal Server** running locally (see below)
- **OpenAI API key** — for story generation (gpt-5.4-nano) and illustration generation
- **Anthropic API key** — only if using an Anthropic model for story generation

## Getting Started

### 1. Configure Environment Variables

```bash
cp .env-sample .env
```

Edit `.env` and fill in your API keys:

| Variable              | Description                                                                                                                       | Default               |
|-----------------------|-----------------------------------------------------------------------------------------------------------------------------------|-----------------------|
| `OPENAI_API_KEY`      | OpenAI API key for LLM and image generation (required)                                                                            | —                     |
| `ANTHROPIC_API_KEY`   | Anthropic API key (required only if using an Anthropic model)                                                                     | —                     |
| `PYDANTIC_AI_MODEL`   | LLM model identifier. Examples: `openai:gpt-5.4-nano` (OpenAI GPT Nano), `anthropic:claude-sonnet-4-6` (Claude Sonnet)            | `openai:gpt-5.4-nano` |
| `OPENAI_IMAGE_MODEL`  | OpenAI image generation model (see [note below](#image-model-and-organization-verification))                                      | `gpt-image-2`         |
| `TEMPORAL_ADDRESS`    | Temporal server address                                                                                                           | `localhost:7233`      |
| `TEMPORAL_TASK_QUEUE` | Temporal task queue name                                                                                                          | `bedtime-story`       |
| `WEBUI_HOST`          | Web UI bind address                                                                                                               | `0.0.0.0`             |
| `WEBUI_PORT`          | Web UI port                                                                                                                       | `8000`                |

#### Image model and organization verification

The default image model `gpt-image-2` (ChatGPT Images 2.0) **requires a verified OpenAI organization**. If your organization is not verified, illustration generation will fail with:

> Your organization must be verified to use the model `gpt-image-2`.

You have two options:

1. **Verify your organization** on [platform.openai.com/settings/organization/general](https://platform.openai.com/settings/organization/general). Access propagates within ~15 minutes.
2. **Use `gpt-image-1.5` instead**, which works without verification. Set this in your `.env`:

   ```env
   OPENAI_IMAGE_MODEL=gpt-image-1.5
   ```

### 2. Run with Docker Compose

```bash
docker-compose up --build
```

This starts the Temporal server, the worker, and the web UI. Open [http://localhost:8000](http://localhost:8000) to start creating a story, and [http://localhost:8233](http://localhost:8233) for the Temporal dashboard.

> **After changing `.env`**, recreate the worker containers so they pick up the new values.
> For example, to switch the LLM provider from Anthropic to OpenAI, edit `.env`:
>
> ```env
> PYDANTIC_AI_MODEL=openai:gpt-5.4-nano
> ```
>
> Then recreate the workers:
>
> ```bash
> docker-compose up --build -d worker-1 worker-2
> ```
>
> Docker Compose only reads `.env` at container creation time, so a simple `docker-compose restart` is **not** enough — you need to recreate the containers.

### 3. Run without Docker

#### Install Dependencies

```bash
uv sync
```

#### Run the Application

Start each command in a separate terminal:

```bash
# Terminal 1 — Temporal Server
temporal server start-dev

# Terminal 2 — Temporal Worker
uv run worker

# Terminal 3 — Web UI
uv run webui
```

Then open [http://localhost:8000](http://localhost:8000) in your browser and start creating a bedtime story!

> You need the [Temporal CLI](https://docs.temporal.io/cli) to run `temporal server start-dev`.

## Development

### Dev Workflow

The recommended way to develop is to run each component separately so you get hot-reload and direct log output.

```bash
# 1. Install dependencies (including dev extras)
uv sync

# 2. Start the Temporal dev server (requires the Temporal CLI)
temporal server start-dev

# 3. Start the worker (auto-reloads on file changes via watchfiles)
uv run worker

# 4. Start the web UI (auto-reloads on file changes via uvicorn)
uv run webui
```

Each command runs in its own terminal. The worker watches `worker/` and `webui/` directories; any saved change restarts it automatically. The web UI reloads on changes to `webui/` and `static/`.

Open [http://localhost:8000](http://localhost:8000) for the app and [http://localhost:8233](http://localhost:8233) for the Temporal dashboard.

### Debugging

#### Temporal Dashboard

The Temporal dev server exposes a web dashboard at [http://localhost:8233](http://localhost:8233) where you can:

- List and inspect running/completed workflows
- View workflow execution history (events, signals, queries)
- Send signals or queries to a running workflow manually

#### Logs

Both the worker and the web UI use `structlog` with JSON output. Filter logs by component:

```bash
# Worker logs include events like "Connecting to Temporal", "Worker started"
uv run worker 2>&1 | jq .

# Web UI logs include events like "Creating session", "Message sent"
uv run webui 2>&1 | jq .
```

#### Common Issues

| Symptom                                                             | Cause                                        | Fix                                                                                                                                      |
|---------------------------------------------------------------------|----------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| `Connection refused` on port 7233                                   | Temporal server not running                  | Start it with `temporal server start-dev`                                                                                                |
| Worker starts but no workflows execute                              | Task queue mismatch                          | Check `TEMPORAL_TASK_QUEUE` matches in `.env`                                                                                            |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` errors                       | Missing or invalid API keys                  | Verify keys in `.env`                                                                                                                    |
| Illustration not generated                                          | OpenAI API key missing or model unavailable  | Check `OPENAI_API_KEY` and `OPENAI_IMAGE_MODEL` in `.env`                                                                                |
| `Your organization must be verified to use the model 'gpt-image-2'` | Default model requires a verified OpenAI org | Either [verify your org](https://platform.openai.com/settings/organization/general), or set `OPENAI_IMAGE_MODEL=gpt-image-1.5` in `.env` |

## Project Structure

```
├── worker/          # Temporal worker: workflows, activities, AI agents
├── webui/           # FastAPI REST API serving the frontend
├── static/          # Single-page app (HTML, JS, CSS)
├── pyproject.toml   # Project metadata and dependencies
└── .env-sample      # Environment variable template
```

## License

[Apache License 2.0](LICENSE)
