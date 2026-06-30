"""The bedtime-story agent's conversation flow, as a reusable object.

A :class:`Conversation` owns the dialogue transcript and turns it into the
inputs the agent needs each turn: the per-turn hint, the prompt, and the
message history rebuilt with the system prompt prepended. It deliberately does
NOT call the agent — the caller runs the agent and feeds the reply back via
:meth:`Conversation.record_response`. Keeping invocation out means the same
object drives the agent whether the caller runs it in-process (a CLI) or hands
each run to some other executor; the flow logic lives here, once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)

from agent.prompt import SYSTEM_PROMPT

# Per-turn scaffolding prepended to the user prompt to keep the 5-turn flow on
# track. Hints are only attached to the current call; they are never recorded
# in the transcript.
#
# IMPORTANT: hints are written in English as internal scaffolding. The
# `message` field MUST be written in the user's language (matching their MOST
# RECENT substantive reply), NOT in the language of the hint. If the user
# switches language mid-conversation, follow them.
LANGUAGE_REMINDER = (
    "[STEP 1 — LANGUAGE LOCK, run this BEFORE writing anything else] "
    "Find the language to lock by scanning user messages from the most "
    "recent backwards until you hit a SUBSTANTIVE reply — a phrase or "
    "sentence with real lexical content (function words, verbs, "
    "adjectives), e.g. 'Max le chien', 'Il cherche son jouet'. SKIP "
    "non-substantive replies that carry no reliable language signal: "
    "bare affirmatives ('ok', 'OK', 'oui', 'yes', 'sí', 'ja', 'vas-y', "
    "'go', \"d'accord\", 'parfait', 'allons-y'), emojis ('👍', '🙂', "
    "'❤️'), isolated proper nouns ('Max'), or any combination of these. "
    "If the latest user message IS non-substantive, the lock comes from "
    "the previous substantive message, NOT from this one and NOT from "
    "your own previous reply and NOT from the default 'English'. Set "
    "`language` to the English name of the locked language (e.g. "
    "'French', 'Spanish', 'English', 'German', 'Italian'). Ignore the "
    "language of your own previous replies and the language of this "
    "hint. Write `message`, `story_title`, recap headers, and "
    "`story_text` ENTIRELY in that language — translate any options, "
    "headers, and questions you would otherwise have written in another "
    "language. Keep proper nouns the user gave you as-is. If the locked "
    "language differs from your previous reply, switch on this turn — "
    "this applies at the recap (turn 4), at story delivery (turn 5+), "
    "and every other turn. Never mix languages within a single message. "
    "`illustration_prompt` stays in English regardless."
)

TURN_HINTS: dict[int, str] = {
    1: "[Turn 1] Greet warmly and ask who the main CHARACTER will be. Offer 3–4 story-level bullets. No user input yet → reply in English.",
    2: f"{LANGUAGE_REMINDER}\n\n[STEP 2 — Turn 2] Ask the QUEST — what the character DOES (searches, helps, faces, explores). Offer 3–4 story-level bullets.",
    3: f"{LANGUAGE_REMINDER}\n\n[STEP 2 — Turn 3] Ask for ONE last ingredient: companion, magical object, or ending. Offer 3–4 story-level bullets.",
    4: f"{LANGUAGE_REMINDER}\n\n[STEP 2 — Turn 4] RECAP all ingredients as a bullet list and end with EXACTLY the write-confirmation question: 'Shall I write the story now?' (FR 'Dois-je écrire l'histoire maintenant ?', ES '¿Escribo la historia ahora?', DE 'Soll ich die Geschichte jetzt schreiben?', IT 'Scrivo la storia adesso?'). Do NOT ask 'Is this everything?', 'Is it correct?', 'Tout est-il correct ?', '¿Está todo bien?' or any variant — that phrasing makes the user's 'ok' ambiguous. The question MUST ask whether to WRITE the story now. The ENTIRE recap — the lead-in sentence, the headers, AND the question — MUST be in the language you locked at STEP 1, even if your previous reply was in a different language. In particular, do NOT keep the lead-in ('Here is what we will weave into your story:') in English when the locked language is not English; translate it too. No other questions. Set writing_story=false and keep story_text EMPTY.",
}

# Used for every turn after the recap (turn 5, 6, 7...). The conversation
# stays open until the user actually approves.
POST_RECAP_HINT = (
    f"{LANGUAGE_REMINDER}\n"
    "\n"
    "[Turn 5+] The recap has been shown; the user just replied. Pick ONE branch.\n"
    "\n"
    "STEP 2 — AFFIRMATIVE GATE (after locking the language above).\n"
    "Read ONLY the latest user reply (ignore the prior conversation pattern). "
    "If the entire reply is a short affirmative with no other words — exactly "
    "one of: 'ok', 'OK', 'oui', 'yes', 'd'accord', 'parfait', 'vas-y', "
    "'allons-y', 'go', 'sí', 'ja', '👍', or a combination of these only "
    "('ok vas-y', 'oui parfait', 'ok parfait') — IMMEDIATELY pick Branch A. "
    "Do not run Step 3. Do not invent content. Adding a sentence like "
    "'j'ajoute X' when X was not in the user's reply is a CRITICAL "
    "HALLUCINATION BUG — the user will be stuck in a loop.\n"
    "\n"
    "STEP 3 — CONTENT SCAN (only if Step 2 did NOT match).\n"
    "Scan the user's reply for ANY story content: a name, place, time of day, "
    "weather, mood, character, action, item, twist, scene, ending, OR the "
    "words 'plutôt', 'rather', 'instead', 'actually', 'ajoute', 'add', "
    "'change'. If ANY is present → Branch B or C. A reply that mixes a "
    "short affirmative WITH new content (e.g. 'ok mais ajoute X') is "
    "Branch C, not A.\n"
    "\n"
    "BRANCH A — APPROVAL (generate now). Triggered by Step 2. "
    "Action: set `writing_story`=true and fill `story_text` with a COMPLETE "
    "3-paragraph story in the user's language RIGHT NOW; `message` = ONE warm "
    "sentence (no question, no story content, no recap, no bullet list). "
    "`writing_story`=true with an empty `story_text`, or saying 'I'll write it' "
    "without filling `story_text`, is a CRITICAL bug that strands the user. "
    "Re-showing the recap on Branch A is a bug.\n"
    "\n"
    "BRANCH B — CHANGE REQUEST. The user wants to swap an element ('plutôt un "
    "cristal', 'rather…', 'instead'). Replace the old element with the new "
    "one, then follow the REQUIRED OUTPUT below. Set `writing_story`=false and "
    "keep `story_text` EMPTY.\n"
    "\n"
    "BRANCH C — EXTRA DETAIL. The user adds a name, place, mood, twist, scene, "
    "or event ('à la fin il X', 'il fait nuit', 'Tim le chat l'accompagne', "
    "'au sommet ils trouvent…', 'ajoute…'). Absorb the detail INTO the "
    "existing ingredients — do NOT generate the story. Then follow the "
    "REQUIRED OUTPUT below. Set `writing_story`=false and keep `story_text` EMPTY.\n"
    "\n"
    "REQUIRED OUTPUT for Branches B and C — `message` MUST contain ALL THREE "
    "parts, in this order, in the language locked at the top of this hint:\n"
    "  1. ONE short acknowledgement sentence ('Parfait, on remplace…' / "
    "'Très bien, j'ajoute…').\n"
    "  2. A FRESH FULL RECAP as a Markdown bullet list of the 3 ingredients "
    "with the update applied. Use the localized headers (FR: Héros / Quête "
    "/ Compagnon · Fin, ES: Héroe / Misión / Compañero · Final, etc.).\n"
    "  3. The yes/no question (FR: 'Dois-je écrire l'histoire maintenant ?').\n"
    "Skipping the recap or the question is a bug — the user must always be "
    "able to confirm."
)

# The opening turn has no real user input yet — this kicks off the greeting.
_OPENING_PROMPT = "Hello!"


def _hint_for_turn(turn: int) -> str:
    """Scaffolding for ``turn``: the fixed script for 1–4, adaptive for 5+."""
    return TURN_HINTS.get(turn, POST_RECAP_HINT)


@dataclass(frozen=True)
class Message:
    """One recorded turn of the visible conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True)
class AgentInput:
    """Everything the agent needs for one run: the prompt and prior history.

    ``message_history`` is ``None`` on the very first turn so the agent injects
    its own system prompt; on later turns it is the rebuilt transcript.
    """

    prompt: str
    message_history: list[ModelMessage] | None


@dataclass
class Conversation:
    """Drives the bedtime-story flow over a growing transcript.

    Usage from any caller::

        conv = Conversation()                 # defaults to the agent's prompt
        agent_input = conv.opening()          # turn 1
        reply = run_the_agent(agent_input)    # caller's job (sync, async, ...)
        conv.record_response(reply.message)
        # then, per user message:
        agent_input = conv.reply(user_text)
        ...

    The transcript holds only the visible ``message`` text (not the agent's
    structured fields), exactly what the model needs to re-derive its state.
    ``system_prompt`` defaults to this agent's prompt; pass a different one only
    to reuse the conversation machinery for another agent.
    """

    system_prompt: str = SYSTEM_PROMPT
    messages: list[Message] = field(default_factory=list)

    @property
    def turn(self) -> int:
        """1-based number of the turn about to be produced."""
        return sum(1 for m in self.messages if m.role == "assistant") + 1

    def opening(self) -> AgentInput:
        """Input for the first turn — a warm greeting, no user input yet."""
        return self._agent_input(_OPENING_PROMPT, record_user=False)

    def reply(self, user_message: str) -> AgentInput:
        """Record a user message and build the input for the next turn."""
        return self._agent_input(user_message, record_user=True)

    def record_response(self, assistant_message: str) -> None:
        """Record the agent's reply so it is part of the next turn's history."""
        self.messages.append(Message("assistant", assistant_message))

    def message_history(self) -> list[ModelMessage]:
        """The transcript so far as pydantic-ai messages, system prompt first.

        The system prompt is prepended explicitly: pydantic-ai only auto-injects
        the agent's ``system_prompt`` on the very first run (the one with no
        history). On every later turn it takes the supplied history verbatim, so
        without prepending it here the system prompt — and with it all the
        language-lock and flow rules — is silently dropped, which is what let
        conversations drift languages mid-stream.
        """
        history: list[ModelMessage] = [
            ModelRequest(parts=[SystemPromptPart(content=self.system_prompt)])
        ]
        for message in self.messages:
            if message.role == "user":
                history.append(
                    ModelRequest(parts=[UserPromptPart(content=message.content)])
                )
            else:
                history.append(
                    ModelResponse(parts=[TextPart(content=message.content)])
                )
        return history

    def _agent_input(self, user_message: str, *, record_user: bool) -> AgentInput:
        # History and turn are derived from the messages gathered SO FAR, before
        # this turn's user message is recorded.
        history = self.message_history() if self.messages else None
        prompt = f"{_hint_for_turn(self.turn)}\n\n{user_message}"
        if record_user:
            self.messages.append(Message("user", user_message))
        return AgentInput(prompt=prompt, message_history=history)
