from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

WEBUI_HOST: str = os.environ.get("WEBUI_HOST", "0.0.0.0")
WEBUI_PORT: int = int(os.environ.get("WEBUI_PORT", "8000"))
