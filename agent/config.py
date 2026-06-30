from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# pydantic-ai reads the API key from the standard provider env var
# (e.g. OPENAI_API_KEY) and infers the provider from the model string.
PYDANTIC_AI_MODEL: str = os.environ.get("PYDANTIC_AI_MODEL", "openai:gpt-5.4-mini")
