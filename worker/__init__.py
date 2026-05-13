from __future__ import annotations

import asyncio
import socket

import structlog
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import (
    SandboxedWorkflowRunner,
    SandboxRestrictions,
)

from worker.activities import generate_illustration
from worker.config import TASK_QUEUE, TEMPORAL_ADDRESS
from worker.workflow_illustration_generation import GenerateIllustrationWorkflow
from worker.workflow_story_session import StorySessionWorkflow

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger("worker")


async def main() -> None:
    identity = socket.gethostname()
    logger.info("Connecting to Temporal", address=TEMPORAL_ADDRESS, identity=identity)

    # PydanticAIPlugin integrates pydantic-ai with Temporal by converting
    # LLM calls into replayable activities for durable execution.
    client = await Client.connect(TEMPORAL_ADDRESS, plugins=[PydanticAIPlugin()])

    # FIXME: pydantic-ai >=1.95 grabs the current OTEL traceparent at the end
    # of each agent run, which triggers a lazy `opentelemetry` import inside
    # the workflow sandbox and hits an `os.environ.get` restriction. Declare
    # the whole `opentelemetry` namespace as pass-through so the sandbox uses
    # the already-loaded host modules instead of re-executing them. Remove
    # once pydantic-ai's TemporalAgent handles this internally.
    restrictions = SandboxRestrictions.default.with_passthrough_modules("opentelemetry")

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[StorySessionWorkflow, GenerateIllustrationWorkflow],
        activities=[generate_illustration],
        identity=identity,
        workflow_runner=SandboxedWorkflowRunner(restrictions=restrictions),
    )

    logger.info("Worker started", task_queue=TASK_QUEUE, identity=identity)
    await worker.run()


def _entrypoint() -> None:
    asyncio.run(main())


def run() -> None:
    """Start the worker with hot-reload: restarts on any file change in worker/ or webui/."""
    from watchfiles import run_process

    run_process("worker", "webui", target=_entrypoint)
