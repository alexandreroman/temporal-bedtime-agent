from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    role: Role
    content: str


class Story(BaseModel):
    title: str = ""
    illustration_prompt: str = ""
    text: str = ""
    language: str = ""


class SessionState(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    story: Story = Field(default_factory=Story)
    finished: bool = False
    illustration_workflow_id: str = ""
