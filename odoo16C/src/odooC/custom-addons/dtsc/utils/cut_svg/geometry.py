# -*- coding: utf-8 -*-
"""Geometry engine: structured JSON -> layered SVG (mm units)."""

from xml.sax.saxutils import escape


DEFAULT_TAB = {
    'tab_depth_mm': 30.0,
    'tab_bevel_mm': 10.0,
}


def _f(v, default=0.0):
    try:
        if v is None:
            return float(default)
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def merge_defaults(data, template_defaults=None):
    """Fill uncertain geometry params from template defaults."""
    data = dict(data or {})
    dims = dict(data.get('dimensions_mm') or {})
    structure = dict(data.get('structure') or {})
    order_size = dict(data.get('order_size') or {})
    defaults = dict(DEFAULT_TAB)
    if template_defaults:
        defaults.update(template_defaults)

    product_type = data.get('product_type') or 'unknown'
    fw = dims.get('front_width')
    fh = dims.get('front_height')
    depth = dims.get('depth')
    bw = dims.get('board_width')
    bh = dims.get('board_height')

    # Apply order_size role without inventing missing front/board blindly as the other
    role = order_size.get('role') or 'unknown'
    ow = order_size.get('width_mm')
    oh = order_size.get('height_mm')
    if ow is not None and oh is not None:
        if role == 'board':
            if bw is None:
                bw = ow
            if bh is None:
                bh = oh
        elif role == 'front':
            if fw is None:
                fw = ow
            if fh is None:
                fh = oh

    fw = _f(fw) if fw is not None else 0.0
    fh = _f(fh) if fh is not None else 0.0
    depth = _f(depth) if depth is not None else 0.0

    if bw is None:
        if product_type == 'rectangular_pedestal' and depth:
            bw = fw + 2 * depth
        else:
            bw = fw
    if bh is None:
        if product_type == 'rectangular_pedestal' and depth:
            bh = fh + 2 * depth
        else:
            bh = fh

    dims['front_width'] = fw
    dims['front_height'] = fh
    dims['depth'] = depth
    dims['board_width'] = _f(bw, fw)
    dims['board_height'] = _f(bh, fh)

    if product_type == 'rectangular_pedestal':
        for key in ('top_panel', 'bottom_panel', 'left_panel', 'right_panel', 'corner_tabs'):
            if key not in structure:
                structure[key] = None
    else:
        for key in ('top_panel', 'bottom_panel', 'left_panel', 'right_panel', 'corner_tabs'):
            if key not in structure:
                structure[key] = False if product_type == 'rectangle_cut' else None

    data['product_type'] = product_type
    data['dimensions_mm'] = dims
    data['structure'] = structure
    data['order_size'] = order_size
    data['template'] = {
        'tab_depth_mm': _f(data.get('tab_depth_mm'), defaults['tab_depth_mm']),
        'tab_bevel_mm': _f(data.get('tab_bevel_mm'), defaults['tab_bevel_mm']),
    }
    return data


def validate_geometry(data, tolerance_mm=2.0):
    """Validate rectangular_pedestal board ≈ front + 2*depth.

    Returns (ok: bool, message: str).
    """
    data = data or {}
    if data.get('product_type') != 'rectangular_pedestal':
        return True, 'skip_non_pedestal'

    d = data.get('dimensions_mm') or {}
    required = (
        d.get('front_width'),
        d.get('front_height'),
        d.get('depth'),
        d.get('board_width'),
        d.get('board_height'),
    )
    if any(v is None for v in required):
        return False, 'missing_required_dimensions'

    fw, fh, depth, bw, bh = (_f(v) for v in required)
    if depth <= 0:
        return False, 'depth_missing_or_zero'

    expected_w = fw + depth * 2
    expected_h = fh + depth * 2
    width_ok = abs(expected_w - bw) <= tolerance_mm
    height_ok = abs(expected_h - bh) <= tolerance_mm
    if width_ok and height_ok:
        return True, f'ok expected={expected_w}x{expected_h} board={bw}x{bh}'
    return (
        False,
        f'geometry_mismatch expected={expected_w}x{expected_h} got={bw}x{bh} '
        f'front={fw}x{fh} depth={depth}',
    )


def _svg_header(width, height, remark=''):
    """Illustrator-friendly SVG: real mm size, path-only (no <text> fonts)."""
    remark = escape((remark or '').replace('--', '—'))
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
        f'<!-- {remark} -->\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        f'width="{width}mm" height="{height}mm" '
        f'viewBox="0 0 {width} {height}" '
        f'xml:space="preserve">\n'
    )


def build_rectangle_cut_svg(data):
    dims = data['dimensions_mm']
    w = dims['front_width']
    h = dims['front_height']
    remark = (
        f"{data.get('label') or 'rectangle_cut'} "
        f"front={w}x{h}mm (paths only, no text)"
    )
    parts = [
        _svg_header(w, h, remark=remark),
        '  <g id="KISS" data-name="KISS" stroke="#C000C0" stroke-width="0.5" fill="none">\n',
        f'    <rect x="0" y="0" width="{w}" height="{h}"/>\n',
        '  </g>\n',
        '  <g id="CUT" data-name="CUT" stroke="#0000FF" stroke-width="0.35" fill="none">\n',
        f'    <rect x="0" y="0" width="{w}" height="{h}"/>\n',
        '  </g>\n',
        '  <g id="CREASE" data-name="CREASE" stroke="#00A0FF" stroke-width="0.25" fill="none"/>\n',
        '</svg>\n',
    ]
    return ''.join(parts)


def build_rectangular_pedestal_svg(data):
    dims = data['dimensions_mm']
    tmpl = data['template']
    fw = dims['front_width']
    fh = dims['front_height']
    d = dims['depth']
    bw = dims['board_width']
    bh = dims['board_height']
    tab = tmpl['tab_depth_mm']
    bevel = tmpl['tab_bevel_mm']

    # Layout: left flap | front | right flap ; top/bottom flaps on front column
    # Origin top-left of full board.
    x0 = d  # front left
    y0 = d  # front top
    # Outer kiss board
    remark = (
        f"{data.get('label') or 'rectangular_pedestal'} "
        f"front={fw}x{fh} depth={d} board={bw}x{bh} tab={tab}/{bevel} "
        f"(paths only, no text)"
    )
    parts = [
        _svg_header(bw, bh, remark=remark),
        '  <g id="KISS" data-name="KISS" stroke="#C000C0" stroke-width="0.5" fill="none">\n',
        f'    <rect x="0" y="0" width="{bw}" height="{bh}"/>\n',
        '  </g>\n',
        '  <g id="CUT" data-name="CUT" stroke="#0000FF" stroke-width="0.35" fill="none">\n',
    ]

    structure = data.get('structure') or {}
    # null = unknown → for MVP drawing use template default (tabs on for pedestal)
    use_tabs = structure.get('corner_tabs')
    if use_tabs is None:
        use_tabs = True
    if use_tabs and d > 0:
        # Build outer cut path with tabs on left and right vertical flaps
        # Left panel outer edge tabs near top and bottom of left flap
        # Coordinates:
        # left flap: x=0..d, y=d..d+fh
        # right flap: x=d+fw..d+fw+d, y=d..d+fh
        # top flap: x=d..d+fw, y=0..d
        # bottom flap: x=d..d+fw, y=d+fh..d+fh+d
        lx = 0
        rx = d + fw
        ty = 0
        by = d + fh
        # Tab geometry on left outer edge
        # top tab: from y=d+bevel down to d+bevel+tab? Actually tabs protrude outward (x negative)
        # Use protruding tabs to the left/right
        path = [
            f'M {d} 0',
            f'L {d + fw} 0',
            f'L {d + fw} {d}',
            # right top tab
            f'L {d + fw + d - bevel} {d}',
            f'L {d + fw + d} {d + bevel}',
            f'L {d + fw + d} {d + bevel + tab}',
            f'L {d + fw + d - bevel} {d + 2 * bevel + tab}',
            f'L {d + fw + d} {d + 2 * bevel + tab}',
            # continue right outer down to bottom tab start
            f'L {d + fw + d} {d + fh - 2 * bevel - tab}',
            # right bottom tab
            f'L {d + fw + d - bevel} {d + fh - 2 * bevel - tab}',
            f'L {d + fw + d} {d + fh - bevel - tab}',
            f'L {d + fw + d} {d + fh - bevel}',
            f'L {d + fw + d - bevel} {d + fh}',
            f'L {d + fw} {d + fh}',
            f'L {d + fw} {d + fh + d}',
            f'L {d} {d + fh + d}',
            f'L {d} {d + fh}',
            # left bottom tab (protrude left)
            f'L {bevel} {d + fh}',
            f'L 0 {d + fh - bevel}',
            f'L 0 {d + fh - bevel - tab}',
            f'L {bevel} {d + fh - 2 * bevel - tab}',
            f'L 0 {d + fh - 2 * bevel - tab}',
            f'L 0 {d + 2 * bevel + tab}',
            # left top tab
            f'L {bevel} {d + 2 * bevel + tab}',
            f'L 0 {d + bevel + tab}',
            f'L 0 {d + bevel}',
            f'L {bevel} {d}',
            f'L {d} {d}',
            'Z',
        ]
        # The path above is a bit idealized; also draw cross outline as fallback rects
        parts.append(f'    <path d="{" ".join(path)}"/>\n')
    else:
        # Simple cross without tabs
        parts.append(f'    <rect x="{d}" y="0" width="{fw}" height="{bh}"/>\n')  # vertical bar
        parts.append(f'    <rect x="0" y="{d}" width="{bw}" height="{fh}"/>\n')  # horizontal bar

    parts.append('  </g>\n')

    # Crease / V-cut lines at panel folds
    parts.append(
        '  <g id="CREASE" data-name="CREASE" stroke="#00A0FF" stroke-width="0.35" '
        'fill="none" stroke-dasharray="4 2">\n'
    )
    if d > 0:
        parts.append(f'    <line x1="{d}" y1="{d}" x2="{d + fw}" y2="{d}"/>\n')  # top fold
        parts.append(f'    <line x1="{d}" y1="{d + fh}" x2="{d + fw}" y2="{d + fh}"/>\n')  # bottom fold
        parts.append(f'    <line x1="{d}" y1="{d}" x2="{d}" y2="{d + fh}"/>\n')  # left fold
        parts.append(f'    <line x1="{d + fw}" y1="{d}" x2="{d + fw}" y2="{d + fh}"/>\n')  # right fold
    parts.append('  </g>\n')
    parts.append('</svg>\n')
    return ''.join(parts)


def build_svg(data, label=None):
    data = merge_defaults(data)
    if label:
        data['label'] = label
    product_type = data.get('product_type') or 'unknown'
    if product_type == 'rectangular_pedestal' and _f((data.get('dimensions_mm') or {}).get('depth')) > 0:
        return build_rectangular_pedestal_svg(data)
    # Default / 四邊裁齊 / unknown → rectangle
    if product_type == 'unknown':
        data['product_type'] = 'rectangle_cut'
    return build_rectangle_cut_svg(data)


def fallback_from_order(width_cm, height_cm, aftermake='', filename=''):
    """Build JSON without GPT, using order line sizes.

    Without a drawing we cannot know if ERP size is board or front; mark unknown.
    """
    w = _f(width_cm) * 10.0
    h = _f(height_cm) * 10.0
    after = (aftermake or '').lower()
    pedestal_keys = ('包', '底座', '側板', '侧板', '五面', '四面', '立體', '立体')
    is_pedestal = any(k in after for k in pedestal_keys)
    data = {
        'product_type': 'rectangular_pedestal' if is_pedestal else 'rectangle_cut',
        'order_size': {
            'width_mm': w,
            'height_mm': h,
            'role': 'unknown',
        },
        'dimensions_mm': {
            # Conservative: treat as board=front until GPT/drawing resolves role
            'front_width': w,
            'front_height': h,
            'depth': None,
            'board_width': w,
            'board_height': h,
        },
        'structure': {},
        'material': {'name': None, 'thickness_mm': None},
        'confidence': 'low',
        'notes': ['fallback_from_order', 'order_size.role=unknown without drawing'],
        'label': filename or '',
    }
    return merge_defaults(data)
