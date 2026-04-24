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
    from worker.agent import StoryResponse, story_agent
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
        self._processing = True
        try:
            result = await temporal_agent.run(prompt, message_history=message_history)
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

            user_msg = self._pending_user_message
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
        await workflow.start_child_workflow(
            GenerateIllustrationWorkflow.run,
            GenerateIllustrationInput(
                prompt=self._story.illustration_prompt,
                story_id=info.workflow_id,
            ),
            id=self._illustration_workflow_id,
            task_queue=info.task_queue,
            parent_close_policy=ParentClosePolicy.ABANDON,
        )

    @workflow.signal
    async def send_message(self, message: str) -> None:
        self._pending_user_message = message

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
