"""Temporal extension layer for the bedtime-story agent.

This module is the *only* place where the pure Pydantic AI agent meets
Temporal. It wraps the untouched ``story_agent`` (from the standalone ``agent``
package) in a ``TemporalAgent`` so its LLM calls become replayable Temporal
activities — adding retries, timeouts, and crash/restart durability *without
changing a single line of the original agent*.

The dependency is intentionally one-directional — ``worker`` depends on
``agent``, never the reverse:

    agent (package)          →  story_agent      (pure Pydantic AI, non-durable)
    worker/durable_agent.py  →  temporal_agent   (this file: durability wrapper)
    worker/workflow_*.py     →  orchestration    (consumes temporal_agent)

``story_agent`` has no knowledge of Temporal and stays runnable standalone
(``python -m agent``); ``temporal_agent`` only adds resilience around it.
"""

from __future__ import annotations

from datetime import timedelta

from agent import story_agent
from pydantic_ai.durable_exec.temporal import TemporalAgent
from temporalio.common import RetryPolicy

# Wrap the pure pydantic-ai agent for Temporal: each LLM call is executed as a
# durable, retryable activity instead of a plain in-process coroutine.
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
