from __future__ import annotations

from pydantic import BaseModel, Field

from worker.models import ChatMessage  # noqa: F401 — used in SessionState annotation


class Story(BaseModel):
    title: str = ""
    illustration_url: str = ""
    illustration_loading: bool = False
    illustration_failed: bool = False
    text: str = ""


class SessionState(BaseModel):
    session_id: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    story: Story = Field(default_factory=Story)
    finished: bool = False
