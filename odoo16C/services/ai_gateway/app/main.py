# -*- coding: utf-8 -*-

from app.agents.runner import run_langchain_agent
from app.observability.logging import get_logger
from app.schemas import AgentRunRequest
from fastapi import FastAPI, Header, HTTPException, Response
from app.progress import progress_store


_logger = get_logger(__name__)

app = FastAPI(title="DTS-C AI Gateway", version="1.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/agent/run")
async def run_agent(payload: AgentRunRequest):
    tracked = progress_store.begin(payload.progress_id, payload.progress_token)
    def emit(state):
        if tracked:
            progress_store.update(payload.progress_id, state)
    finished = False
    try:
        result = await run_langchain_agent(payload, progress=emit)
        emit('done' if result.get('status') == 'success' else 'failed')
        finished = True
        return result
    except Exception as exc:  # pragma: no cover - service guardrail
        emit('failed')
        _logger.exception("AI gateway execution failed")
        return {
            "status": "error",
            "answer": "AI gateway 執行失敗。",
            "available_tools": [tool.name for tool in payload.tools],
            "called_tools": [],
            "tool_results": [],
            "duration_ms": 0,
            "error_message": str(exc),
        }

    finally:
        if not finished:
            emit('failed')


@app.get('/v1/agent/progress/{run_id}')
def read_progress(run_id: str, response: Response, x_dtsc_ai_progress_token: str = Header(default='')):
    response.headers['Cache-Control'] = 'no-store'
    result = progress_store.read(run_id, x_dtsc_ai_progress_token)
    if result is None:
        raise HTTPException(404, 'Unavailable', headers={'Cache-Control': 'no-store'})
    return result
