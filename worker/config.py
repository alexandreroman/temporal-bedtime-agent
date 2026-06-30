from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# The LLM model (PYDANTIC_AI_MODEL) lives with the pure agent in the `agent`
# package; the worker only owns Temporal and illustration settings.
OPENAI_IMAGE_MODEL: str = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2")

TEMPORAL_ADDRESS: str = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TASK_QUEUE: str = os.environ.get("TEMPORAL_TASK_QUEUE", "bedtime-story")
