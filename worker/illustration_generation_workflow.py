from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from worker.activities import GenerateIllustrationInput, generate_illustration


@workflow.defn
class GenerateIllustrationWorkflow:
    """Child workflow that generates a story illustration via OpenAI."""

    @workflow.run
    async def run(self, input: GenerateIllustrationInput) -> str:
        return await workflow.execute_activity(
            generate_illustration,
            input,
            start_to_close_timeout=timedelta(seconds=120),
        )
