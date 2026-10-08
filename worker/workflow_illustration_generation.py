from __future__ import annotations

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from worker.activities import GenerateIllustrationInput, generate_illustration
    from worker.durable_agent import ACTIVITY_CONFIG


@workflow.defn
class GenerateIllustrationWorkflow:
    """Child workflow that generates a story illustration via OpenAI."""

    @workflow.run
    async def run(self, input: GenerateIllustrationInput) -> str:
        return await workflow.execute_activity(
            generate_illustration, input, **ACTIVITY_CONFIG
        )
