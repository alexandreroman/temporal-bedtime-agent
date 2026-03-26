from __future__ import annotations

import asyncio
import socket

import structlog
from pydantic_ai.durable_exec.temporal import PydanticAIPlugin
from temporalio.client import Client
from temporalio.worker import Worker

from worker.activities import generate_illustration
from worker.config import TASK_QUEUE, TEMPORAL_ADDRESS
from worker.illustration_generation_workflow import GenerateIllustrationWorkflow
from worker.story_session_workflow import StorySessionWorkflow

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

    client = await Client.connect(
        TEMPORAL_ADDRESS,
        plugins=[PydanticAIPlugin()],
    )

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[StorySessionWorkflow, GenerateIllustrationWorkflow],
        activities=[generate_illustration],
        identity=identity,
    )

    logger.info("Worker started", task_queue=TASK_QUEUE, identity=identity)
    await worker.run()


def _run_worker() -> None:
    asyncio.run(main())


def run() -> None:
    from watchfiles import run_process

    run_process("worker", "webui", target=_run_worker)
