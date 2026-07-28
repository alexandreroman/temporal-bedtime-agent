"""Temporal extension layer for the bedtime-story agent.

This module is the *only* place where the pure Pydantic AI agent meets
Temporal. It builds the untouched agent definition (from the standalone
``agent`` package) with the ``TemporalDurability`` capability attached, so its
LLM calls become replayable Temporal activities — adding retries, timeouts, and
crash/restart durability *without changing the agent's own behaviour*.

The dependency is intentionally one-directional — ``worker`` depends on
``agent``, never the reverse:

    agent (package)          →  build_story_agent()  (pure Pydantic AI, non-durable)
    worker/durable_agent.py  →  temporal_agent       (this file: durable build)
    worker/workflow_*.py     →  orchestration        (consumes temporal_agent)

The ``agent`` package has no knowledge of Temporal and stays runnable
standalone (``uv run agent``); this module only adds resilience around it.
"""

from __future__ import annotations

from datetime import timedelta

from agent import build_story_agent
from pydantic_ai.durable_exec.temporal import TemporalDurability
from temporalio.common import RetryPolicy

# Build the pydantic-ai agent with Temporal durability attached: each LLM call
# is executed as a durable, retryable activity instead of a plain in-process
# coroutine.
#
# The activity names derive from the agent's own name ("story_agent", fixed in
# `build_story_agent`) — they must stay stable so that workflows started by an
# earlier deployment still replay.
temporal_agent = build_story_agent(
    capabilities=[
        TemporalDurability(
            activity_config={
                "start_to_close_timeout": timedelta(seconds=60),
                "retry_policy": RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    backoff_coefficient=1.5,
                    maximum_interval=timedelta(seconds=5),
                ),
            },
        )
    ],
)
