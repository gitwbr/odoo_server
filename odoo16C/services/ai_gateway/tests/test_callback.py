# -*- coding: utf-8 -*-

import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from pydantic import ValidationError

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.tools.callback import _build_args_schema, build_callback_tool


class CallbackSchemaTestCase(unittest.TestCase):
    def test_schema_constraints_survive_gateway_conversion_and_validate(self):
        definition = SimpleNamespace(name='constrained', parameters={
            'type': 'object', 'properties': {
                'measures': {'type': 'array', 'minItems': 1, 'maxItems': 2, 'items': {
                    'type': 'object', 'properties': {
                        'alias': {'type': 'string', 'pattern': '^[A-Za-z_][A-Za-z0-9_]*$',
                                  'description': 'Internal identifier; omit to use the field name.'},
                    }, 'additionalProperties': False}},
                'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100},
                'keyword': {'type': 'string', 'minLength': 1, 'maxLength': 10},
                'names': {'type': 'array', 'items': {'type': 'string', 'pattern': '^[a-z]+$'}},
            }, 'required': ['measures']})
        schema = _build_args_schema(definition)
        for alias in ('total_amount', None):
            self.assertEqual(schema.model_validate({'measures': [{'alias': alias}]}).measures[0].alias, alias)
        schema.model_validate({'measures': [{}]})
        for request in (
            {'measures': [{'alias': '應收總額'}]},
            {'measures': [{'alias': 'sum(amount)'}]},
            {'measures': []}, {'measures': [{}, {}, {}]},
            {'measures': [{}], 'limit': 101},
            {'measures': [{}], 'keyword': 'longer than ten'},
            {'measures': [{}], 'names': ['INVALID']},
        ):
            with self.subTest(request=request), self.assertRaises(ValidationError):
                schema.model_validate(request)
        generated = schema.model_json_schema()
        item = generated['$defs']['ConstrainedArgsMeasuresItem']
        self.assertEqual(item['properties']['alias']['anyOf'][0]['pattern'], '^[A-Za-z_][A-Za-z0-9_]*$')
        self.assertIn('omit', item['properties']['alias']['description'])
        self.assertEqual(generated['properties']['limit']['anyOf'][0]['maximum'], 100)

    def test_optional_null_and_required_filter_value_preserved(self):
        definition = SimpleNamespace(name='generic', parameters={
            'type': 'object', 'properties': {
                'operation': {'type': 'string'},
                'limit': {'type': 'integer'},
                'value': {},
            }, 'required': ['operation', 'value']})
        schema = _build_args_schema(definition)
        result = schema.model_validate({'operation': 'search', 'limit': None, 'value': None})
        self.assertEqual(result.model_dump(exclude_unset=True),
                         {'operation': 'search', 'limit': None, 'value': None})
        with self.assertRaises(ValidationError):
            schema.model_validate({'operation': None, 'value': None})
        with self.assertRaises(ValidationError):
            schema.model_validate({'operation': 'search', 'limit': 'bad', 'value': None})

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
        def non_null(node):
            return next((item for item in node.get("anyOf", []) if item.get("type") != "null"), node)
        for key in ("filters", "fields", "group_by", "measures", "order"):
            generated["properties"][key] = non_null(generated["properties"][key])
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
        date_range_ref = non_null(filter_item["properties"]["date_range"])["$ref"]
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

        self.assertEqual(json.loads(result), {"count": 2, "_evidence_id": 1})
        request_payload = post.call_args.kwargs["json"]
        self.assertEqual(request_payload["arguments"], self._arguments())
        self.assertEqual(tool_results[0]["arguments"], self._arguments())

    def test_async_callback_forwards_identity_and_nested_arguments(self):
        response = Mock()
        response.json.return_value = {"success": True, "result": {"count": 0}}
        client = AsyncMock()
        client.post.return_value = response
        manager = AsyncMock()
        manager.__aenter__.return_value = client
        callback = SimpleNamespace(url='https://odoo.example.test/callback', token='test',
                                   context={'user_id': 7}, timeout=10)
        results = []
        tool = build_callback_tool(self._tool_definition(), callback, results)
        with patch('app.tools.callback.httpx.AsyncClient', return_value=manager):
            result = asyncio.run(tool.ainvoke(self._arguments()))
        self.assertEqual(json.loads(result), {'count': 0, '_evidence_id': 1})
        payload = client.post.call_args.kwargs['json']
        self.assertEqual(payload['arguments'], self._arguments())
        self.assertEqual(payload['context'], {'user_id': 7})
        self.assertEqual(results[0]['result'], {'count': 0})


if __name__ == "__main__":
    unittest.main()

class SchemaGuardTest(unittest.TestCase):
    def test_query_without_description_is_rejected_before_http(self):
        from app.schemas import ToolDefinition, ToolCallback
        definition=ToolDefinition(name='universal_odoo_query',parameters={'type':'object','properties':{
            'operation':{'type':'string'},'model':{'type':'string'}},'required':['operation','model']})
        callback=ToolCallback(url='https://example.test/callback',token='test')
        calls=[]
        tool=build_callback_tool(definition,callback,calls)
        with patch('app.tools.callback.requests.post') as post:
            output=json.loads(tool.invoke({'operation':'aggregate','model':'unknown.invoice'}))
        post.assert_not_called()
        self.assertEqual(output['error']['code'],'model_discovery_required')
        self.assertEqual(output['_evidence_id'],1)
        self.assertFalse(calls[0]['result']['ok'])


    def test_discovered_model_still_requires_description_before_data(self):
        from app.agents.query_protocol import query_prerequisite
        discovery={'result':{'ok':True,'query_type':'universal_discover','models':[{'model':'custom.invoice'}]}}
        request={'operation':'aggregate','model':'custom.invoice'}
        self.assertEqual(query_prerequisite(request,[discovery])['code'],'schema_required')
        description={'result':{'ok':True,'query_type':'universal_describe','model':'custom.invoice','fields':[]}}
        self.assertIsNone(query_prerequisite(request,[discovery,description]))
