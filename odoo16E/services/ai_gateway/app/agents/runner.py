# -*- coding: utf-8 -*-

import time

from langchain.agents import create_agent

from app.providers.factory import create_chat_model
from app.tools.callback import build_callback_tools


def run_langchain_agent(payload):
    started = time.time()
    tool_results = []
    tools = build_callback_tools(payload.tools, payload.tool_callback, tool_results)
    model = create_chat_model(payload.config)
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=payload.system_prompt or "",
    )
    result = agent.invoke({
        "messages": _build_messages(payload),
    })
    return {
        "status": "success",
        "answer": _extract_answer(result),
        "available_tools": [tool.name for tool in tools],
        "called_tools": _called_tool_names(tool_results),
        "tool_results": tool_results,
        "duration_ms": int((time.time() - started) * 1000),
    }


def _build_messages(payload):
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in payload.messages
        if msg.role in ("user", "assistant") and msg.content
    ]
    if payload.message and (
        not messages or messages[-1]["role"] != "user" or messages[-1]["content"] != payload.message
    ):
        messages.append({"role": "user", "content": payload.message})
    if not messages:
        messages.append({"role": "user", "content": payload.message or ""})
    return messages


def _extract_answer(result):
    messages = result.get("messages") if isinstance(result, dict) else None
    if messages:
        last = messages[-1]
        return getattr(last, "content", "") or str(last)
    return str(result)


def _called_tool_names(tool_results):
    names = []
    for item in tool_results or []:
        name = item.get("tool") if isinstance(item, dict) else ""
        if name and name not in names:
            names.append(name)
    return names

