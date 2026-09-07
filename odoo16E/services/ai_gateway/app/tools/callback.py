# -*- coding: utf-8 -*-

import json
import re
from typing import Any, Dict, List, Literal

import requests
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, create_model


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
        arguments = _to_json_data(kwargs)
        response = requests.post(
            callback.url,
            headers={"X-DTSC-AI-Gateway-Token": callback.token},
            json={
                "tool_name": tool_def.name,
                "arguments": arguments,
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
            "arguments": arguments,
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
    if not properties:
        properties = {
            "keyword": {
                "type": "string",
                "description": "查詢關鍵字",
                "default": "",
            },
        }
        schema = {"type": "object", "properties": properties}
    model_name = "%sArgs" % _safe_identifier(tool_def.name).title()
    return _build_object_model(schema, model_name)


def _json_schema_to_python(schema, model_name):
    schema = schema if isinstance(schema, dict) else {}
    json_type = schema.get("type")

    if json_type == "array" or (not json_type and "items" in schema):
        item_type = _json_schema_to_python(
            schema.get("items") or {},
            "%sItem" % model_name,
        )
        return List[item_type]
    if json_type == "object" or (not json_type and "properties" in schema):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            return _build_object_model(schema, model_name)
        additional = schema.get("additionalProperties")
        value_type = (
            _json_schema_to_python(additional, "%sValue" % model_name)
            if isinstance(additional, dict)
            else Any
        )
        return Dict[str, value_type]

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return Literal.__getitem__(tuple(enum_values))
    if json_type == "integer":
        return int
    if json_type == "number":
        return float
    if json_type == "boolean":
        return bool
    if json_type == "string":
        return str
    return Any


def _build_object_model(schema, model_name):
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields = {}
    for field_name, meta in properties.items():
        meta = meta if isinstance(meta, dict) else {}
        field_type = _json_schema_to_python(
            meta,
            "%s%s" % (model_name, _safe_identifier(field_name).title()),
        )
        if field_name in required:
            default = ...
        else:
            default = meta.get("default") if "default" in meta else None
        fields[field_name] = (
            field_type,
            Field(default, description=meta.get("description") or ""),
        )

    extra = "forbid" if schema.get("additionalProperties") is False else "allow"
    return create_model(
        model_name,
        __config__=ConfigDict(extra=extra),
        **fields,
    )


def _to_json_data(value):
    if isinstance(value, BaseModel):
        return _to_json_data(value.model_dump(exclude_unset=True))
    if isinstance(value, dict):
        return {key: _to_json_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_data(item) for item in value]
    return value


def _safe_identifier(value):
    cleaned = re.sub(r"\W+", "_", value or "tool").strip("_")
    return cleaned or "tool"
