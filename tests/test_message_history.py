from __future__ import annotations

import os

# Importing `agent` constructs the agent at import time and its provider wants
# an API key, even though these tests never make a network call — they only
# inspect how the Conversation rebuilds history. Provide a dummy key so the
# import succeeds in any environment (CI included).
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from pydantic_ai.messages import (  # noqa: E402
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)

from agent import SYSTEM_PROMPT  # noqa: E402
from agent.conversation import Conversation, Message  # noqa: E402


def _sample_conversation() -> Conversation:
    conv = Conversation()
    conv.messages.extend(
        [
            Message("assistant", "Welcome! Who is the hero?"),
            Message("user", "A little dragon named Ember"),
            Message("assistant", "Great choice! What is the quest?"),
        ]
    )
    return conv


def test_history_carries_system_prompt() -> None:
    """Regression for mid-conversation language drift.

    pydantic-ai only auto-injects the agent's system prompt on the first
    (history-less) run. Every later turn passes a reconstructed history, so the
    system prompt — which holds all the language-lock and flow rules — must be
    prepended here, otherwise the agent runs on the per-turn hint alone and a
    single-language chat can drift (e.g. English wandering into Spanish).
    """
    history = _sample_conversation().message_history()

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
    history = _sample_conversation().message_history()
    conversation = history[1:]  # drop the leading system-prompt request

    assert isinstance(conversation[0], ModelResponse)
    assert isinstance(conversation[0].parts[0], TextPart)
    assert conversation[0].parts[0].content == "Welcome! Who is the hero?"

    assert isinstance(conversation[1], ModelRequest)
    assert isinstance(conversation[1].parts[0], UserPromptPart)
    assert conversation[1].parts[0].content == "A little dragon named Ember"

    assert isinstance(conversation[2], ModelResponse)
    assert isinstance(conversation[2].parts[0], TextPart)
    assert conversation[2].parts[0].content == "Great choice! What is the quest?"


def test_empty_history_still_carries_system_prompt() -> None:
    history = Conversation().message_history()
    assert len(history) == 1
    assert isinstance(history[0].parts[0], SystemPromptPart)


def test_turn_numbering_and_recording() -> None:
    conv = Conversation()

    # Turn 1: the opening greeting carries no history (the agent injects the
    # system prompt itself) and records no user message.
    assert conv.turn == 1
    opening = conv.opening()
    assert opening.message_history is None
    assert opening.prompt.startswith("[Turn 1]")
    assert conv.messages == []

    conv.record_response("greeting")
    assert conv.turn == 2

    # A reply records the user message and rebuilds history from prior turns.
    second = conv.reply("Max the dog")
    assert second.message_history is not None
    assert [m.role for m in conv.messages] == ["assistant", "user"]
