# -*- coding: utf-8 -*-

from app.agents.runner import run_langchain_agent
from app.observability.logging import get_logger
from app.schemas import AgentRunRequest
from fastapi import FastAPI


_logger = get_logger(__name__)

app = FastAPI(title="DTS-C AI Gateway", version="1.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/agent/run")
def run_agent(payload: AgentRunRequest):
    try:
        return run_langchain_agent(payload)
    except Exception as exc:  # pragma: no cover - service guardrail
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
