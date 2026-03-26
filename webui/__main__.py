import uvicorn

from webui.config import WEBUI_HOST, WEBUI_PORT

uvicorn.run("webui:app", host=WEBUI_HOST, port=WEBUI_PORT, log_level="warning")
