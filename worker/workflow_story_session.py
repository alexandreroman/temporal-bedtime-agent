from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.workflow import ParentClosePolicy

# Temporal's workflow sandbox restricts imports to enforce determinism.
# `imports_passed_through()` lets these non-deterministic libraries bypass
# the sandbox since they are only used inside activities, not workflow logic.
with workflow.unsafe.imports_passed_through():
    import annotated_types  # noqa: F401 — pre-load to avoid sandbox warning

    from pydantic_ai.durable_exec.temporal import TemporalAgent
    from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart

    from worker.activities import GenerateIllustrationInput
    from worker.agent import story_agent
    from worker.models import (
        ChatMessage,
        Role,
        SessionState,
        Story,
    )
    from worker.workflow_illustration_generation import GenerateIllustrationWorkflow

# Wrap the pydantic-ai agent for Temporal: LLM calls become activities.
temporal_agent = TemporalAgent(
    wrapped=story_agent,
    name="story_agent",
    activity_config={
        "start_to_close_timeout": timedelta(seconds=60),
        "retry_policy": RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=1.5,
            maximum_interval=timedelta(seconds=5),
        ),
    },
)

# Per-turn scaffolding injected into the user prompt to keep the 5-turn flow
# on track. Hints are only attached to the current call; they are never
# persisted into self._messages or the conversation history.
#
# IMPORTANT: hints are written in English as internal scaffolding. The
# `message` field MUST be written in the user's language (matching their
# MOST RECENT substantive reply), NOT in the language of the hint. If the
# user switches language mid-conversation, follow them.
_LANGUAGE_REMINDER = (
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

_TURN_HINTS: dict[int, str] = {
    1: "[Turn 1] Greet warmly and ask who the main CHARACTER will be. Offer 3–4 story-level bullets. No user input yet → reply in English.",
    2: f"{_LANGUAGE_REMINDER}\n\n[STEP 2 — Turn 2] Ask the QUEST — what the character DOES (searches, helps, faces, explores). Offer 3–4 story-level bullets.",
    3: f"{_LANGUAGE_REMINDER}\n\n[STEP 2 — Turn 3] Ask for ONE last ingredient: companion, magical object, or ending. Offer 3–4 story-level bullets.",
    4: f"{_LANGUAGE_REMINDER}\n\n[STEP 2 — Turn 4] RECAP all ingredients as a bullet list and end with a single yes/no question. The recap headers and yes/no question MUST be in the language you locked at STEP 1, even if your previous reply was in a different language. No other questions. Keep story_text EMPTY.",
}

# Used for every turn after the recap (turn 5, 6, 7...). The conversation
# stays open until the user actually approves.
_POST_RECAP_HINT = (
    f"{_LANGUAGE_REMINDER}\n"
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
    "Action: fill `story_text` with a COMPLETE 3-paragraph story in the user's "
    "language RIGHT NOW; `message` = ONE warm sentence (no question, no story "
    "content, no recap, no bullet list). Saying 'I'll write it' without "
    "filling `story_text` is a bug. Re-showing the recap on Branch A is a bug.\n"
    "\n"
    "BRANCH B — CHANGE REQUEST. The user wants to swap an element ('plutôt un "
    "cristal', 'rather…', 'instead'). Replace the old element with the new "
    "one, then follow the REQUIRED OUTPUT below. Keep `story_text` EMPTY.\n"
    "\n"
    "BRANCH C — EXTRA DETAIL. The user adds a name, place, mood, twist, scene, "
    "or event ('à la fin il X', 'il fait nuit', 'Tim le chat l'accompagne', "
    "'au sommet ils trouvent…', 'ajoute…'). Absorb the detail INTO the "
    "existing ingredients — do NOT generate the story. Then follow the "
    "REQUIRED OUTPUT below. Keep `story_text` EMPTY.\n"
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


@workflow.defn
class StorySessionWorkflow:
    # Declares which TemporalAgents this workflow uses, so their activities
    # are automatically registered on the worker.
    __pydantic_ai_agents__ = [temporal_agent]

    def __init__(self) -> None:
        self._messages: list[ChatMessage] = []
        self._story: Story = Story()
        self._finished: bool = False
        # Signal-driven message passing: the signal handler sets this value,
        # and the main loop picks it up via wait_condition().
        self._pending_user_message: str | None = None
        self._processing: bool = False
        # Illustration child workflow — started once the story is approved.
        self._illustration_workflow_id: str = ""

    async def _run_agent(
        self, prompt: str, message_history: list[ModelMessage] | None = None
    ) -> None:
        """Invoke the agent and apply its response to workflow state."""
        # Turns 1–4 follow a fixed script; turn 5+ is adaptive (approve /
        # change / add detail) until the user explicitly greenlights.
        turn = sum(1 for m in self._messages if m.role == Role.ASSISTANT) + 1
        hint = _TURN_HINTS.get(turn, _POST_RECAP_HINT)
        prompt_with_hint = f"{hint}\n\n{prompt}"

        self._processing = True
        try:
            result = await temporal_agent.run(
                prompt_with_hint, message_history=message_history
            )
        finally:
            self._processing = False

        response = result.output
        self._messages.append(
            ChatMessage(role=Role.ASSISTANT, content=response.message)
        )
        if response.story_title:
            self._story.title = response.story_title
        if response.illustration_prompt:
            self._story.illustration_prompt = response.illustration_prompt
        if response.language:
            self._story.language = response.language
        if response.story_text:
            self._story.text = response.story_text
            self._finished = True

    @workflow.run
    async def run(self) -> SessionState:
        # Initial greeting
        await self._run_agent("Hello!")

        # Main loop: wait for user messages, process them
        while not self._finished:
            await workflow.wait_condition(
                lambda: self._pending_user_message is not None or self._finished
            )

            if self._finished:
                break

            # wait_condition above guarantees this is non-None.
            assert self._pending_user_message is not None
            user_msg: str = self._pending_user_message
            self._pending_user_message = None

            # Rebuild pydantic-ai message history from prior turns so the LLM
            # has full conversational context; the new user_msg is the prompt.
            message_history: list[ModelMessage] = [
                ModelRequest(parts=[UserPromptPart(content=msg.content)])
                if msg.role == Role.USER
                else ModelResponse(parts=[TextPart(content=msg.content)])
                for msg in self._messages
            ]
            self._messages.append(ChatMessage(role=Role.USER, content=user_msg))

            await self._run_agent(user_msg, message_history)

            # Start illustration as soon as the story is approved — all
            # elements are finalized and the prompt is definitive.
            if self._finished and self._story.illustration_prompt:
                await self._start_illustration()

        return self._build_state()

    async def _start_illustration(self) -> None:
        """Start the illustration child workflow."""
        info = workflow.info()
        self._illustration_workflow_id = f"{info.workflow_id}-illustration"
        # Force any visible text inside the illustration to match the story's
        # language — the agent never embeds this directive itself.
        language = self._story.language or "English"
        prompt = (
            f"{self._story.illustration_prompt}\n\n"
            f"Any visible text inside the image must be written in {language}."
        )
        await workflow.start_child_workflow(
            GenerateIllustrationWorkflow.run,
            GenerateIllustrationInput(
                prompt=prompt,
                story_id=info.workflow_id,
            ),
            id=self._illustration_workflow_id,
            task_queue=info.task_queue,
            parent_close_policy=ParentClosePolicy.ABANDON,
        )

    @workflow.signal
    async def send_message(self, message: str) -> None:
        # Concatenate concurrent messages so none is dropped if the user
        # sends multiple before the previous one is processed.
        if self._pending_user_message is None:
            self._pending_user_message = message
        else:
            self._pending_user_message += "\n" + message

    def _build_state(self) -> SessionState:
        return SessionState(
            messages=self._messages,
            story=self._story,
            finished=self._finished,
            illustration_workflow_id=self._illustration_workflow_id,
        )

    @workflow.query
    def get_state(self) -> SessionState:
        return self._build_state()

    @workflow.query
    def is_processing(self) -> bool:
        return self._processing
