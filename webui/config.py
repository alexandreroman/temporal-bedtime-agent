from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

TEMPORAL_ADDRESS: str = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
TASK_QUEUE: str = os.environ.get("TEMPORAL_TASK_QUEUE", "bedtime-story")

WEBUI_HOST: str = os.environ.get("WEBUI_HOST", "0.0.0.0")
WEBUI_PORT: int = int(os.environ.get("WEBUI_PORT", "8000"))
