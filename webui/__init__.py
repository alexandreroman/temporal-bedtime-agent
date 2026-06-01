from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from webui.config import TASK_QUEUE, TEMPORAL_ADDRESS
from webui.models import SessionState, Story
# The worker persists its own SessionState in workflow history; the webui
# wraps it with presentation fields (session_id, processing, illustration_*).
from worker.models import SessionState as WorkerSessionState

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

app = FastAPI(title="Temporal Bedtime Agent")
logger = structlog.get_logger("webui")

# Lazy singleton — the webui does not need the PydanticAIPlugin since it only
# starts workflows by string name; the worker handles actual execution.
_client: Client | None = None


async def get_client() -> Client:
    global _client
    if _client is None:
        logger.info("Connecting to Temporal", address=TEMPORAL_ADDRESS)
        _client = await Client.connect(TEMPORAL_ADDRESS)
    return _client


async def _fill_illustration(client: Client, workflow_id: str, story: Story) -> None:
    """Populate the story's illustration fields from the child workflow status."""
    handle = client.get_workflow_handle(workflow_id)
    try:
        desc = await handle.describe()
    except RPCError as e:
        if e.status == RPCStatusCode.NOT_FOUND:
            return
        raise

    if desc.status == WorkflowExecutionStatus.COMPLETED:
        story.illustration_url = await handle.result()
    elif desc.status == WorkflowExecutionStatus.RUNNING:
        story.illustration_loading = True
    else:
        story.illustration_failed = True


class CreateSessionResponse(BaseModel):
    session_id: str


class SendMessageRequest(BaseModel):
    message: str


@app.post("/api/sessions", response_model=CreateSessionResponse)
async def create_session() -> CreateSessionResponse:
    client = await get_client()
    session_id = f"story-{uuid.uuid4().hex[:8]}"

    logger.info("Creating session", session_id=session_id, task_queue=TASK_QUEUE)
    await client.start_workflow(
        "StorySessionWorkflow",
        id=session_id,
        task_queue=TASK_QUEUE,
    )

    return CreateSessionResponse(session_id=session_id)


@app.get("/api/sessions/{session_id}/state", response_model=SessionState)
async def get_session_state(session_id: str) -> SessionState:
    client = await get_client()
    try:
        handle = client.get_workflow_handle(session_id)
        desc = await handle.describe()
        if desc.status == WorkflowExecutionStatus.COMPLETED:
            # Workflow finished — get the result directly, no query needed
            worker_state = WorkerSessionState.model_validate(await handle.result())
            processing = False
        else:
            # Workflow still running — query for current state
            worker_state = await handle.query(
                "get_state", result_type=WorkerSessionState
            )
            processing = await handle.query("is_processing", result_type=bool)
    except Exception as e:
        logger.error("Failed to get session state", session_id=session_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e)) from e

    # The story workflow starts the illustration as a child workflow
    # once the story is approved. The webui only polls its status.
    story = Story(title=worker_state.story.title, text=worker_state.story.text)
    if worker_state.illustration_workflow_id:
        try:
            await _fill_illustration(client, worker_state.illustration_workflow_id, story)
        except Exception as e:
            logger.error("Illustration poll failed", session_id=session_id, error=str(e))

    return SessionState(
        session_id=session_id,
        messages=worker_state.messages,
        story=story,
        finished=worker_state.finished,
        processing=processing,
    )


@app.post("/api/sessions/{session_id}/messages")
async def send_message(session_id: str, req: SendMessageRequest) -> dict[str, str]:
    client = await get_client()
    try:
        handle = client.get_workflow_handle(session_id)
        await handle.signal("send_message", req.message)
        logger.info("Message sent", session_id=session_id)
        return {"status": "sent"}
    except Exception as e:
        logger.error("Failed to send message", session_id=session_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


# Catch-all for deep-linked story URLs — the SPA handles routing client-side.
@app.get("/stories/{story_id}")
async def session_page(story_id: str) -> FileResponse:
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


def run(reload: bool = True) -> None:
    import uvicorn

    from webui.config import WEBUI_HOST, WEBUI_PORT

    logger.info("Starting webui", host=WEBUI_HOST, port=WEBUI_PORT)
    uvicorn.run(
        "webui:app",
        host=WEBUI_HOST,
        port=WEBUI_PORT,
        reload=reload,
        log_level="warning",
    )
