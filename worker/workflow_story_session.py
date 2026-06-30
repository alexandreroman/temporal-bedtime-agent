from __future__ import annotations

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

# Temporal's workflow sandbox restricts imports to enforce determinism.
# `imports_passed_through()` lets these non-deterministic libraries bypass
# the sandbox since they are only used inside activities, not workflow logic.
with workflow.unsafe.imports_passed_through():
    import annotated_types  # noqa: F401 — pre-load to avoid sandbox warning

    # The conversation flow (turns, hints, history) is an agent concern owned by
    # the agent package. This workflow only runs the agent and persists state;
    # it shares the exact same Conversation object as the standalone CLI.
    from agent.conversation import AgentInput, Conversation

    from worker.activities import GenerateIllustrationInput
    # The Temporal extension layer: a TemporalAgent wrapping the pure
    # `story_agent`. Defined in its own module so this workflow only orchestrates
    # the conversation and never touches the agent's durability wiring.
    from worker.durable_agent import temporal_agent
    from worker.models import (
        ChatMessage,
        Role,
        SessionState,
        Story,
    )
    from worker.workflow_illustration_generation import GenerateIllustrationWorkflow


@workflow.defn
class StorySessionWorkflow:
    # Declares which TemporalAgents this workflow uses, so their activities
    # are automatically registered on the worker.
    __pydantic_ai_agents__ = [temporal_agent]

    def __init__(self) -> None:
        # The Conversation owns the transcript and builds each turn's agent
        # input (hint + prompt + history). Plain Python state, so it replays
        # deterministically with the workflow.
        self._conversation = Conversation()
        self._story: Story = Story()
        self._finished: bool = False
        # Signal-driven message passing: the signal handler sets this value,
        # and the main loop picks it up via wait_condition().
        self._pending_user_message: str | None = None
        self._processing: bool = False
        # Illustration child workflow — started once the story is approved.
        self._illustration_workflow_id: str = ""

    async def _run_turn(self, agent_input: AgentInput) -> None:
        """Run one agent turn (as a durable activity) and apply its response."""
        self._processing = True
        try:
            result = await temporal_agent.run(
                agent_input.prompt, message_history=agent_input.message_history
            )
        finally:
            self._processing = False

        response = result.output
        self._conversation.record_response(response.message)
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
        await self._run_turn(self._conversation.opening())

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

            await self._run_turn(self._conversation.reply(user_msg))

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
            messages=[
                ChatMessage(role=Role(m.role), content=m.content)
                for m in self._conversation.messages
            ],
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
