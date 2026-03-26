from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

from worker.agent import illustration_agent

ILLUSTRATIONS_DIR = Path("static/illustrations")


@dataclass
class GenerateIllustrationInput:
    prompt: str
    story_id: str


@activity.defn
async def generate_illustration(input: GenerateIllustrationInput) -> str:
    """Use pydantic-ai to generate an illustration and return a local file path."""
    ILLUSTRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    result = await illustration_agent.run(input.prompt)
    image = result.output

    filename = f"{input.story_id}.png"
    filepath = ILLUSTRATIONS_DIR / filename
    filepath.write_bytes(image.data)

    return f"/static/illustrations/{filename}"
