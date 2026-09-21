# -*- coding: utf-8 -*-
"""End-to-end cut SVG pipeline for one checkout line context."""

import json
import logging
import os

from . import geometry
from . import gpt_client
from . import validator

_logger = logging.getLogger(__name__)


def run_pipeline(image_b64, context, api_key=None, use_gpt=True):
    """Return dict with svg + intermediate debug fields.

    mode: 'gpt' | 'fallback' | 'fallback_after_gpt_error' | 'no_api_key'
    """
    json_data = None
    mode = 'fallback'
    gpt_raw = ''
    gpt_error = ''
    gpt_model = gpt_client.get_model_name()
    gpt_usage = {}
    has_key = bool((api_key or '').strip() or gpt_client.get_api_key())

    # ERP cm → mm is always done in Python (source of truth).
    try:
        order_width_mm = gpt_client.cm_to_mm(context.get('width'))
        order_height_mm = gpt_client.cm_to_mm(context.get('height'))
    except ValueError as exc:
        return {
            'svg_text': '',
            'json_data': {},
            'mode': 'error',
            'json_text': '',
            'gpt_raw': '',
            'gpt_error': str(exc),
            'gpt_model': gpt_model,
            'debug_text': str(exc),
            'verification': {
                'erp_match': False,
                'geometry_match': False,
                'role_consistent': False,
                'ready_for_svg': False,
                'messages': [str(exc)],
            },
        }

    ctx = dict(context or {})
    ctx['width_mm'] = order_width_mm
    ctx['height_mm'] = order_height_mm

    if not use_gpt or not has_key:
        mode = 'no_api_key'
        gpt_error = '未提供 GPT_API_KEY，改用訂單寬高 fallback'
    elif not image_b64:
        mode = 'fallback'
        gpt_error = '沒有參考圖，跳過 GPT'
    else:
        try:
            gpt_result = gpt_client.analyze_cut_image(image_b64, ctx, api_key=api_key)
            json_data = gpt_result['parsed']
            gpt_raw = gpt_result.get('raw_content') or ''
            gpt_model = gpt_result.get('model') or gpt_model
            gpt_usage = gpt_result.get('usage') or {}
            mode = 'gpt'
        except Exception as exc:
            _logger.warning('GPT cut analysis failed, fallback to order sizes: %s', exc)
            gpt_error = str(exc)
            mode = 'fallback_after_gpt_error'
            json_data = None

    if not json_data:
        json_data = geometry.fallback_from_order(
            context.get('width'),
            context.get('height'),
            aftermake=context.get('aftermake') or '',
            filename=context.get('filename') or '',
        )
        if mode == 'gpt':
            mode = 'fallback'

    # Always force ERP mm onto order_size.
    order_size = dict(json_data.get('order_size') or {})
    if order_width_mm is not None:
        order_size['width_mm'] = order_width_mm
    if order_height_mm is not None:
        order_size['height_mm'] = order_height_mm
    order_size.setdefault('role', 'unknown')
    json_data['order_size'] = order_size

    role = order_size.get('role')
    dims = dict(json_data.get('dimensions_mm') or {})
    if role == 'board' and order_width_mm and order_height_mm:
        dims['board_width'] = order_width_mm
        dims['board_height'] = order_height_mm
    elif role == 'front' and order_width_mm and order_height_mm:
        dims['front_width'] = order_width_mm
        dims['front_height'] = order_height_mm
    json_data['dimensions_mm'] = dims

    json_data = geometry.merge_defaults(json_data)
    verification = validator.verify_cut_data(
        json_data,
        order_width_mm=order_width_mm,
        order_height_mm=order_height_mm,
    )
    json_data['verification'] = verification

    notes = list(json_data.get('notes') or [])
    notes.extend(verification.get('messages') or [])
    if not verification.get('ready_for_svg'):
        notes.append('WARNING: not ready_for_svg (MVP still emits SVG for inspection)')
        if json_data.get('confidence') == 'high':
            json_data['confidence'] = 'medium'
    json_data['notes'] = notes
    json_data['label'] = context.get('filename') or json_data.get('label') or ''

    svg_text = geometry.build_svg(json_data)
    json_text = json.dumps(json_data, ensure_ascii=False, indent=2)

    debug_parts = [
        f"mode={mode}",
        f"model={gpt_model}",
        f"has_api_key={has_key}",
        f"erp_mm={order_width_mm}x{order_height_mm}",
        f"product_type={json_data.get('product_type')}",
        f"order_size={json.dumps(json_data.get('order_size'), ensure_ascii=False)}",
        f"dimensions_mm={json.dumps(json_data.get('dimensions_mm'), ensure_ascii=False)}",
        f"verification={json.dumps(verification, ensure_ascii=False)}",
        f"context={json.dumps(ctx, ensure_ascii=False)}",
        f"gpt_usage={json.dumps(gpt_usage, ensure_ascii=False)}",
        f"gpt_error={gpt_error or '(none)'}",
        '--- GPT raw ---',
        gpt_raw or '(empty)',
        '--- final JSON ---',
        json_text,
        '--- SVG head ---',
        (svg_text or '')[:800],
    ]
    err_parts = []
    if gpt_error:
        err_parts.append(gpt_error)
    if not verification.get('ready_for_svg'):
        err_parts.append('ready_for_svg=false: ' + '; '.join(verification.get('messages') or []))
    return {
        'svg_text': svg_text,
        'json_data': json_data,
        'mode': mode,
        'json_text': json_text,
        'gpt_raw': gpt_raw,
        'gpt_error': ' | '.join(err_parts),
        'gpt_model': gpt_model,
        'debug_text': '\n'.join(debug_parts),
        'verification': verification,
    }
