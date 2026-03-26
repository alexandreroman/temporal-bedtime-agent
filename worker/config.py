from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# pydantic-ai reads the API key from the standard provider env var
# (e.g. ANTHROPIC_API_KEY) and infers the provider from the model string.
PYDANTIC_AI_MODEL: str = os.environ.get(
    "PYDANTIC_AI_MODEL", "anthropic:claude-sonnet-4-6"
)

PYDANTIC_AI_IMAGE_MODEL: str = os.environ.get(
    "PYDANTIC_AI_IMAGE_MODEL", "openai-responses:gpt-5.4-nano"
)

TEMPORAL_ADDRESS: str = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TASK_QUEUE: str = os.environ.get("TEMPORAL_TASK_QUEUE", "bedtime-story")
