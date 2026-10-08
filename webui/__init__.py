from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from temporalio.client import Client, WorkflowExecutionStatus
from temporalio.service import RPCError, RPCStatusCode

from worker.config import TASK_QUEUE, TEMPORAL_ADDRESS
from worker.models import SessionState

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


def _http_error(e: RPCError, event: str, session_id: str) -> HTTPException:
    """404 only for an unknown session; anything else is a transient outage."""
    logger.error(event, session_id=session_id, error=str(e))
    status_code = 404 if e.status == RPCStatusCode.NOT_FOUND else 503
    return HTTPException(status_code=status_code, detail=e.message)


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
    handle = client.get_workflow_handle(session_id, result_type=SessionState)
    try:
        desc = await handle.describe()
        if desc.status == WorkflowExecutionStatus.COMPLETED:
            # Workflow finished — get the result directly, no query needed
            return await handle.result()
        # Workflow still running — query for current state
        return await handle.query("get_state", result_type=SessionState)
    except RPCError as e:
        raise _http_error(e, "Failed to get session state", session_id) from e


@app.post("/api/sessions/{session_id}/messages")
async def send_message(session_id: str, req: SendMessageRequest) -> dict[str, str]:
    client = await get_client()
    try:
        await client.get_workflow_handle(session_id).signal("send_message", req.message)
    except RPCError as e:
        raise _http_error(e, "Failed to send message", session_id) from e
    logger.info("Message sent", session_id=session_id)
    return {"status": "sent"}


# `/stories/<id>` deep links are routed client-side by the SPA.
@app.get("/")
@app.get("/stories/{story_id}")
async def index() -> FileResponse:
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
