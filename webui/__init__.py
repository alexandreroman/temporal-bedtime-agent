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
# The worker and webui have separate SessionState models: the worker's model
# is what Temporal stores (no illustration URL), while the webui's model adds
# presentation fields (illustration_url, illustration_loading, session_id).
from worker.models import SessionState as WorkerSessionState

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

STATIC_DIR = "static"

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


# ---------------------------------------------------------------------------
# Illustration — poll the child workflow started by StorySessionWorkflow
# ---------------------------------------------------------------------------

async def _poll_illustration(client: Client, workflow_id: str) -> str:
    """Poll an illustration workflow and return its URL when complete.

    The illustration workflow is started by the story workflow as a child,
    so this function only checks status — it never starts a workflow.
    Returns the illustration URL if the workflow completed, empty string otherwise.
    """
    handle = client.get_workflow_handle(workflow_id)

    try:
        desc = await handle.describe()
    except RPCError as e:
        if e.status == RPCStatusCode.NOT_FOUND:
            return ""
        raise

    if desc.status == WorkflowExecutionStatus.COMPLETED:
        return await handle.result()

    return ""


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class CreateSessionResponse(BaseModel):
    session_id: str


class SendMessageRequest(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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
            worker_state = WorkerSessionState.model_validate(
                await handle.result()
            )
        else:
            # Workflow still running — query for current state
            worker_state = await handle.query(
                "get_state", result_type=WorkerSessionState
            )
    except Exception as e:
        logger.error("Failed to get session state", session_id=session_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))

    # The story workflow starts the illustration as a child workflow
    # once the story is approved.  The webui only polls its status.
    illustration_wf_id = worker_state.illustration_workflow_id
    illustration_url = ""
    if illustration_wf_id:
        try:
            illustration_url = await _poll_illustration(client, illustration_wf_id)
        except Exception as e:
            logger.error("Illustration poll failed", session_id=session_id, error=str(e))

    # True while the illustration workflow is running but hasn't completed yet.
    illustration_loading = bool(illustration_wf_id) and not illustration_url

    return SessionState(
        session_id=session_id,
        messages=worker_state.messages,
        story=Story(
            title=worker_state.story.title,
            illustration_url=illustration_url,
            illustration_loading=illustration_loading,
            text=worker_state.story.text,
        ),
        finished=worker_state.finished,
    )


@app.get("/api/sessions/{session_id}/processing")
async def get_processing(session_id: str) -> dict[str, bool]:
    client = await get_client()
    try:
        handle = client.get_workflow_handle(session_id)
        desc = await handle.describe()
        if desc.status == WorkflowExecutionStatus.COMPLETED:
            return {"processing": False}
        processing = await handle.query("is_processing", result_type=bool)
        return {"processing": processing}
    except Exception:
        # Workflow completed or not found — not processing
        return {"processing": False}


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
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(f"{STATIC_DIR}/index.html")


# Catch-all for deep-linked story URLs — the SPA handles routing client-side.
@app.get("/stories/{story_id}")
async def session_page(story_id: str) -> FileResponse:
    return FileResponse(f"{STATIC_DIR}/index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run() -> None:
    import uvicorn

    from webui.config import WEBUI_HOST, WEBUI_PORT

    logger.info("Starting webui", host=WEBUI_HOST, port=WEBUI_PORT)
    uvicorn.run("webui:app", host=WEBUI_HOST, port=WEBUI_PORT, reload=True, log_level="warning")
