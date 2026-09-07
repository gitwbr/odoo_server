# -*- coding: utf-8 -*-
"""Production verification: GPT confidence != production confidence."""

from . import geometry


def _almost_equal(a, b, tolerance_mm=2.0):
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) <= tolerance_mm
    except (TypeError, ValueError):
        return False


def verify_cut_data(data, order_width_mm=None, order_height_mm=None, tolerance_mm=2.0):
    """Return verification dict for production readiness.

    Keys:
      erp_match: order_size numbers match ERP mm
      geometry_match: pedestal board ≈ front + 2*depth (or non-pedestal skip/pass)
      role_consistent: dimensions align with order_size.role
      ready_for_svg: production-safe to trust geometry for cutting
      messages: human-readable notes
    """
    data = data or {}
    dims = data.get('dimensions_mm') or {}
    order_size = data.get('order_size') or {}
    product_type = data.get('product_type') or 'unknown'
    role = order_size.get('role') or 'unknown'
    messages = []

    erp_match = True
    if order_width_mm is not None:
        if not _almost_equal(order_size.get('width_mm'), order_width_mm, tolerance_mm):
            erp_match = False
            messages.append(
                f"erp_width mismatch order_size={order_size.get('width_mm')} erp={order_width_mm}"
            )
    if order_height_mm is not None:
        if not _almost_equal(order_size.get('height_mm'), order_height_mm, tolerance_mm):
            erp_match = False
            messages.append(
                f"erp_height mismatch order_size={order_size.get('height_mm')} erp={order_height_mm}"
            )
    if erp_match:
        messages.append('erp_match=ok')

    role_consistent = True
    if role == 'board':
        if order_width_mm is not None and not _almost_equal(dims.get('board_width'), order_width_mm, tolerance_mm):
            role_consistent = False
            messages.append('role=board but board_width != ERP width')
        if order_height_mm is not None and not _almost_equal(dims.get('board_height'), order_height_mm, tolerance_mm):
            role_consistent = False
            messages.append('role=board but board_height != ERP height')
    elif role == 'front':
        if order_width_mm is not None and not _almost_equal(dims.get('front_width'), order_width_mm, tolerance_mm):
            role_consistent = False
            messages.append('role=front but front_width != ERP width')
        if order_height_mm is not None and not _almost_equal(dims.get('front_height'), order_height_mm, tolerance_mm):
            role_consistent = False
            messages.append('role=front but front_height != ERP height')
    else:
        messages.append('role=unknown')
        role_consistent = False

    geometry_ok, geometry_msg = geometry.validate_geometry(data, tolerance_mm=tolerance_mm)
    messages.append(f'geometry: {geometry_msg}')

    if product_type == 'rectangle_cut':
        geometry_match = bool(
            dims.get('front_width') and dims.get('front_height')
        )
        if geometry_match:
            messages.append('rectangle_cut has front size')
    elif product_type == 'rectangular_pedestal':
        geometry_match = bool(geometry_ok)
    else:
        geometry_match = False
        messages.append('product_type=unknown')

    ready_for_svg = bool(erp_match and geometry_match and role_consistent and product_type != 'unknown')

    return {
        'erp_match': erp_match,
        'geometry_match': geometry_match,
        'role_consistent': role_consistent,
        'ready_for_svg': ready_for_svg,
        'product_type': product_type,
        'role': role,
        'gpt_confidence': data.get('confidence'),
        'messages': messages,
    }
