# -*- coding: utf-8 -*-

import json
import re

import requests
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model


def build_callback_tools(tool_defs, callback, tool_results):
    if not callback:
        return []
    tools = [
        build_callback_tool(tool_def, callback, tool_results)
        for tool_def in tool_defs
    ]
    return [tool for tool in tools if tool is not None]


def build_callback_tool(tool_def, callback, tool_results):
    args_schema = _build_args_schema(tool_def)

    def callback_tool(**kwargs):
        response = requests.post(
            callback.url,
            headers={"X-DTSC-AI-Gateway-Token": callback.token},
            json={
                "tool_name": tool_def.name,
                "arguments": kwargs,
                "context": callback.context,
            },
            timeout=callback.timeout or 30.0,
        )
        response.raise_for_status()
        data = response.json()
        if not data.get("success"):
            result = {"error": data.get("message") or "tool call failed"}
        else:
            result = data.get("result") or {}
        tool_results.append({
            "tool": tool_def.name,
            "arguments": kwargs,
            "result": result,
        })
        return json.dumps(result, ensure_ascii=False)

    callback_tool.__name__ = _safe_identifier(tool_def.name)
    callback_tool.__doc__ = tool_def.description or tool_def.name
    return StructuredTool.from_function(
        func=callback_tool,
        name=tool_def.name,
        description=tool_def.description or tool_def.name,
        args_schema=args_schema,
    )


def _build_args_schema(tool_def):
    schema = tool_def.parameters or {}
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields = {}
    for field_name, meta in properties.items():
        field_type = _json_type_to_python(meta.get("type"))
        default = ... if field_name in required else None
        fields[field_name] = (field_type, Field(default, description=meta.get("description") or ""))
    if not fields:
        fields["keyword"] = (str, Field("", description="查詢關鍵字"))
    return create_model("%sArgs" % _safe_identifier(tool_def.name).title(), **fields)


def _json_type_to_python(json_type):
    if json_type == "integer":
        return int
    if json_type == "number":
        return float
    if json_type == "boolean":
        return bool
    return str


def _safe_identifier(value):
    cleaned = re.sub(r"\W+", "_", value or "tool").strip("_")
    return cleaned or "tool"

