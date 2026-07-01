from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from openai import APIStatusError, AsyncOpenAI
from temporalio import activity
from temporalio.exceptions import ApplicationError

from worker.config import OPENAI_IMAGE_MODEL

ILLUSTRATIONS_DIR = Path("static/illustrations")


@dataclass
class GenerateIllustrationInput:
    prompt: str
    story_id: str


@activity.defn
async def generate_illustration(input: GenerateIllustrationInput) -> str:
    """Call OpenAI Images API directly and return a local file path."""
    ILLUSTRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    client = AsyncOpenAI()
    try:
        response = await client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=input.prompt,
            size="1024x1024",
            quality="low",
            n=1,
        )
    except APIStatusError as e:
        # 4xx (except 429) are client/config errors that retries won't fix:
        # invalid model, missing auth, unverified org, bad request, etc.
        if 400 <= e.status_code < 500 and e.status_code != 429:
            raise ApplicationError(
                str(e), type="ImageAPIError", non_retryable=True
            ) from e
        raise

    assert response.data is not None
    b64 = response.data[0].b64_json
    assert b64 is not None
    image_bytes = base64.b64decode(b64)

    filename = f"{input.story_id}.png"
    filepath = ILLUSTRATIONS_DIR / filename
    filepath.write_bytes(image_bytes)

    return f"/static/illustrations/{filename}"
