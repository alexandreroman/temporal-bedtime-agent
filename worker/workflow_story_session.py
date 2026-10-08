from __future__ import annotations

from temporalio import workflow
from temporalio.exceptions import ChildWorkflowError

# Temporal's workflow sandbox re-imports modules for every run. Pass these
# through instead: they are deterministic and side-effect free at import time,
# and re-importing pydantic-ai and openai on each run would be costly.
with workflow.unsafe.imports_passed_through():
    # The conversation flow (turns, hints, history) is an agent concern owned by
    # the agent package. This workflow only runs the agent and persists state;
    # it shares the exact same Conversation object as the standalone CLI.
    from agent.conversation import AgentInput, Conversation

    from worker.activities import GenerateIllustrationInput
    # The Temporal extension layer: the pure agent rebuilt with the
    # `TemporalDurability` capability. Defined in its own module so this
    # workflow only orchestrates the conversation.
    from worker.durable_agent import temporal_agent
    from worker.models import ChatMessage, SessionState, Story
    from worker.workflow_illustration_generation import GenerateIllustrationWorkflow


@workflow.defn
class StorySessionWorkflow:
    # Declares the durable agents this workflow uses, so their activities are
    # automatically registered on the worker.
    __pydantic_ai_agents__ = [temporal_agent]

    def __init__(self) -> None:
        # The Conversation owns the transcript and builds each turn's agent
        # input (hint + prompt + history). Plain Python state, so it replays
        # deterministically with the workflow.
        self._conversation = Conversation()
        self._story = Story()
        self._finished = False
        # Signal-driven message passing: the signal handler queues messages,
        # and the main loop picks them up via wait_condition().
        self._pending_messages: list[str] = []
        self._processing = False

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

        # Main loop: wait for user messages until the story is written.
        while not self._finished:
            await workflow.wait_condition(lambda: bool(self._pending_messages))
            # Join messages sent before the previous turn finished, so none
            # is dropped.
            user_message = "\n".join(self._pending_messages)
            self._pending_messages.clear()
            await self._run_turn(self._conversation.reply(user_message))

        # The story is approved: all elements are final, so is the prompt.
        if self._story.illustration_prompt:
            await self._generate_illustration()

        return self._build_state()

    async def _generate_illustration(self) -> None:
        """Illustrate the story in a child workflow; on failure the story stands."""
        # Force any visible text inside the illustration to match the story's
        # language — the agent never embeds this directive itself.
        prompt = (
            f"{self._story.illustration_prompt}\n\n"
            f"Any visible text inside the image must be written in {self._story.language}."
        )
        story_id = workflow.info().workflow_id
        self._story.illustration_loading = True
        try:
            self._story.illustration_url = await workflow.execute_child_workflow(
                GenerateIllustrationWorkflow.run,
                GenerateIllustrationInput(prompt=prompt, story_id=story_id),
                id=f"{story_id}-illustration",
            )
        except ChildWorkflowError:
            self._story.illustration_failed = True
        finally:
            self._story.illustration_loading = False

    @workflow.signal
    def send_message(self, message: str) -> None:
        self._pending_messages.append(message)

    @workflow.query
    def get_state(self) -> SessionState:
        return self._build_state()

    def _build_state(self) -> SessionState:
        return SessionState(
            messages=[
                ChatMessage(role=m.role, content=m.content)
                for m in self._conversation.messages
            ],
            story=self._story,
            finished=self._finished,
            processing=self._processing,
        )
