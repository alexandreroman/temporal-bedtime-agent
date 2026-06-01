from __future__ import annotations

import os

# The agent is constructed at import time and its provider wants an API key,
# even though these tests never make a network call — they only inspect how the
# conversation history is rebuilt. Provide a dummy key so the import succeeds in
# any environment (CI included).
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from pydantic_ai.messages import (  # noqa: E402
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    UserPromptPart,
)

from worker.agent import SYSTEM_PROMPT  # noqa: E402
from worker.models import ChatMessage, Role  # noqa: E402
from worker.workflow_story_session import _build_message_history  # noqa: E402


def _sample_messages() -> list[ChatMessage]:
    return [
        ChatMessage(role=Role.ASSISTANT, content="Welcome! Who is the hero?"),
        ChatMessage(role=Role.USER, content="A little dragon named Ember"),
        ChatMessage(role=Role.ASSISTANT, content="Great choice! What is the quest?"),
    ]


def test_history_carries_system_prompt() -> None:
    """Regression for mid-conversation language drift.

    pydantic-ai only auto-injects the agent's system prompt on the first
    (history-less) run. Every later turn passes a reconstructed history, so the
    system prompt — which holds all the language-lock and flow rules — must be
    prepended here, otherwise the agent runs on the per-turn hint alone and a
    single-language chat can drift (e.g. English wandering into Spanish).
    """
    history = _build_message_history(_sample_messages())

    system_parts = [
        part
        for message in history
        for part in message.parts
        if isinstance(part, SystemPromptPart)
    ]
    assert len(system_parts) == 1, "exactly one system prompt must be present"
    assert system_parts[0].content == SYSTEM_PROMPT

    # It must lead the history, ahead of any conversation turn.
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[0].parts[0], SystemPromptPart)


def test_history_preserves_turns_in_order() -> None:
    history = _build_message_history(_sample_messages())
    conversation = history[1:]  # drop the leading system-prompt request

    assert isinstance(conversation[0], ModelResponse)
    assert conversation[0].parts[0].content == "Welcome! Who is the hero?"

    assert isinstance(conversation[1], ModelRequest)
    assert isinstance(conversation[1].parts[0], UserPromptPart)
    assert conversation[1].parts[0].content == "A little dragon named Ember"

    assert isinstance(conversation[2], ModelResponse)
    assert conversation[2].parts[0].content == "Great choice! What is the quest?"


def test_empty_history_still_carries_system_prompt() -> None:
    history = _build_message_history([])
    assert len(history) == 1
    assert isinstance(history[0].parts[0], SystemPromptPart)
