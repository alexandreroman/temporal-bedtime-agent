from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    import annotated_types  # noqa: F401 — pre-load to avoid sandbox warning

    from pydantic_ai.durable_exec.temporal import TemporalAgent
    from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart

    from worker.agent import StoryResponse, story_agent
    from worker.models import (
        ChatMessage,
        Role,
        SessionState,
        Story,
    )

# Wrap the pydantic-ai agent for Temporal: LLM calls become activities.
temporal_agent = TemporalAgent(
    wrapped=story_agent,
    name="story_agent",
    activity_config={
        "start_to_close_timeout": timedelta(seconds=120),
        "retry_policy": RetryPolicy(
            initial_interval=timedelta(seconds=1),
            backoff_coefficient=2.0,
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=3,
        ),
    },
)


@workflow.defn
class StorySessionWorkflow:
    __pydantic_ai_agents__ = [temporal_agent]

    def __init__(self) -> None:
        self._messages: list[ChatMessage] = []
        self._story: Story = Story()
        self._finished: bool = False
        self._pending_user_message: str | None = None
        self._processing: bool = False

    def _apply_result(self, response: StoryResponse) -> None:
        """Extract story fields from the structured response and update state."""
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
        self._processing = True
        result = await temporal_agent.run("Hello!")
        self._apply_result(result.output)
        self._processing = False

        # Main loop: wait for user messages, process them
        while not self._finished:
            await workflow.wait_condition(
                lambda: self._pending_user_message is not None or self._finished
            )

            if self._finished:
                break

            user_msg = self._pending_user_message
            self._pending_user_message = None
            self._messages.append(ChatMessage(role=Role.USER, content=user_msg))
            self._processing = True

            # Build pydantic-ai message history from prior turns
            message_history: list[ModelMessage] = []
            for msg in self._messages[:-1]:
                if msg.role == Role.USER:
                    message_history.append(
                        ModelRequest(parts=[UserPromptPart(content=msg.content)])
                    )
                else:
                    message_history.append(
                        ModelResponse(parts=[TextPart(content=msg.content)])
                    )

            result = await temporal_agent.run(
                user_msg,
                message_history=message_history,
            )

            self._apply_result(result.output)
            self._processing = False

        # Return the final state as the workflow result
        return self._build_state()

    @workflow.signal
    async def send_message(self, message: str) -> None:
        self._pending_user_message = message

    def _build_state(self) -> SessionState:
        return SessionState(
            messages=list(self._messages),
            story=Story(
                title=self._story.title,
                illustration_prompt=self._story.illustration_prompt,
                text=self._story.text,
            ),
            finished=self._finished,
        )

    @workflow.query
    def get_state(self) -> SessionState:
        return self._build_state()

    @workflow.query
    def is_processing(self) -> bool:
        return self._processing
