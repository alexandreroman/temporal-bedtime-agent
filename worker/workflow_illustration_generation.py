from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from worker.activities import GenerateIllustrationInput, generate_illustration


@workflow.defn
class GenerateIllustrationWorkflow:
    """Workflow that generates a story illustration via OpenAI."""

    @workflow.run
    async def run(self, input: GenerateIllustrationInput) -> str:
        return await workflow.execute_activity(
            generate_illustration,
            input,
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=1.5,
                maximum_interval=timedelta(seconds=5),
            ),
        )
