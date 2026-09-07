# -*- coding: utf-8 -*-

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.tools.callback import _build_args_schema, build_callback_tool


class CallbackSchemaTestCase(unittest.TestCase):
    def _tool_definition(self):
        return SimpleNamespace(
            name="universal_odoo_query",
            description="Query Odoo through a callback.",
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string"},
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "operator": {"type": "string"},
                                "value": {},
                                "date_range": {
                                    "type": "object",
                                    "properties": {
                                        "start": {"type": "string"},
                                        "end": {"type": "string"},
                                    },
                                    "required": ["start"],
                                    "additionalProperties": False,
                                },
                            },
                            "required": ["field", "operator"],
                            "additionalProperties": False,
                        },
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "group_by": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "measures": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "aggregate": {
                                    "type": "string",
                                    "enum": ["sum", "avg", "count"],
                                },
                            },
                            "required": ["field", "aggregate"],
                        },
                    },
                    "order": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "direction": {"type": "string"},
                            },
                            "required": ["field"],
                        },
                    },
                    "limit": {"type": "integer"},
                    "include_empty": {"type": "boolean"},
                },
                "required": ["operation"],
                "additionalProperties": False,
            },
        )

    def _arguments(self):
        return {
            "operation": "aggregate",
            "filters": [
                {
                    "field": "create_date",
                    "operator": "between",
                    "value": ["2026-08-01", "2026-08-31"],
                    "date_range": {"start": "2026-08-01"},
                }
            ],
            "fields": ["name", "customer_id"],
            "group_by": ["create_date:month"],
            "measures": [{"field": "amount_total", "aggregate": "sum"}],
            "order": [{"field": "amount_total", "direction": "desc"}],
            "limit": 20,
            "include_empty": False,
        }

    def test_recursively_validates_and_serializes_query_schema(self):
        args_schema = _build_args_schema(self._tool_definition())

        validated = args_schema.model_validate(self._arguments())

        self.assertEqual(validated.model_dump(exclude_unset=True), self._arguments())
        generated = args_schema.model_json_schema()
        self.assertEqual(generated["properties"]["filters"]["type"], "array")
        self.assertEqual(generated["properties"]["fields"]["items"]["type"], "string")
        self.assertEqual(generated["properties"]["group_by"]["type"], "array")
        self.assertEqual(generated["properties"]["measures"]["type"], "array")
        self.assertEqual(generated["properties"]["order"]["type"], "array")
        self.assertEqual(generated["required"], ["operation"])
        filter_item_ref = generated["properties"]["filters"]["items"]["$ref"]
        filter_item = generated["$defs"][filter_item_ref.rsplit("/", 1)[-1]]
        self.assertEqual(filter_item["type"], "object")
        self.assertEqual(filter_item["required"], ["field", "operator"])
        date_range_ref = filter_item["properties"]["date_range"]["$ref"]
        date_range = generated["$defs"][date_range_ref.rsplit("/", 1)[-1]]
        self.assertEqual(date_range["required"], ["start"])

    def test_nested_required_fields_and_array_types_are_enforced(self):
        args_schema = _build_args_schema(self._tool_definition())

        with self.assertRaises(ValidationError):
            args_schema.model_validate({
                "operation": "search",
                "filters": [{"operator": "="}],
            })
        with self.assertRaises(ValidationError):
            args_schema.model_validate({
                "operation": "search",
                "fields": "name",
            })
        with self.assertRaises(ValidationError):
            args_schema.model_validate({
                "operation": "search",
                "filters": [{
                    "field": "create_date",
                    "operator": "between",
                    "date_range": {"end": "2026-08-31"},
                }],
            })
        with self.assertRaises(ValidationError):
            args_schema.model_validate({
                "operation": "aggregate",
                "measures": [{"field": "amount_total", "aggregate": "median"}],
            })

    def test_scalar_parameters_remain_compatible(self):
        tool_definition = SimpleNamespace(
            name="scalar_tool",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "ratio": {"type": "number"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["query"],
            },
        )

        validated = _build_args_schema(tool_definition).model_validate({
            "query": "A260400250",
            "limit": 5,
            "ratio": 1.5,
            "enabled": True,
        })

        self.assertEqual(validated.query, "A260400250")
        self.assertEqual(validated.limit, 5)
        self.assertEqual(validated.ratio, 1.5)
        self.assertTrue(validated.enabled)

    @patch("app.tools.callback.requests.post")
    def test_callback_forwards_nested_arguments_without_flattening(self, post):
        response = post.return_value
        response.raise_for_status.return_value = None
        response.json.return_value = {"success": True, "result": {"count": 2}}
        callback = SimpleNamespace(
            url="https://odoo.example.test/callback",
            token="secret",
            context={"user_id": 7},
            timeout=10.0,
        )
        tool_results = []
        tool = build_callback_tool(self._tool_definition(), callback, tool_results)

        result = tool.invoke(self._arguments())

        self.assertEqual(json.loads(result), {"count": 2})
        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["arguments"], self._arguments())
        self.assertEqual(tool_results[0]["arguments"], self._arguments())


if __name__ == "__main__":
    unittest.main()
