from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Story(BaseModel):
    title: str = ""
    text: str = ""
    language: str = "English"
    illustration_prompt: str = ""
    illustration_url: str = ""
    illustration_loading: bool = False
    illustration_failed: bool = False


class SessionState(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    story: Story = Field(default_factory=Story)
    finished: bool = False
    processing: bool = False
