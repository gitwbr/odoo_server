# -*- coding: utf-8 -*-
"""印刷池：按材料可視化排版，舊料優先 + 預留新料，截斷鎖定成印刷單。

圖塊可釘選（位置不動）與拖到其他可放門幅。
"""
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .nesting_engine import NestingEngine, Obstacle, PieceDemand, Placement, RollResult


def _placement_to_demand(pl):
    """Restore original demand size from a placement (undo rotation for re-queue)."""
    w = pl.height if pl.rotated else pl.width
    h = pl.width if pl.rotated else pl.height
    return PieceDemand(key=pl.key, width=w, height=h, meta=dict(pl.meta or {}))


class PrintPool(models.AbstractModel):
    _name = 'dtsc.print.pool'
    _description = '印刷池'

    @api.model
    def _print_pool_allow_rotate(self):
        """印刷池高級設定：預設允許旋轉以省料。"""
        val = self.env['ir.config_parameter'].sudo().get_param(
            'dtsc_print_nesting.print_pool_allow_rotate', 'True',
        )
        return str(val).lower() not in ('0', 'false', 'False')

    @api.model
    def _print_pool_gap_mm(self):
        """一般圖間距(mm)，設定單位為 cm，預設 0.5cm。"""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'dtsc_print_nesting.print_pool_gap_cm', '0.5',
        )
        try:
            cm = float(raw)
        except (TypeError, ValueError):
            cm = 0.5
        return max(cm, 0.0) * 10.0

    @api.model
    def _print_pool_gap_diff_film_mm(self):
        """異膜圖間距(mm)，設定單位為 cm，預設 5cm。"""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'dtsc_print_nesting.print_pool_gap_diff_film_cm', '5.0',
        )
        try:
            cm = float(raw)
        except (TypeError, ValueError):
            cm = 5.0
        return max(cm, 0.0) * 10.0

    @api.model
    def _print_pool_margin_mm(self):
        """系統預設捲材邊距(mm)，設定單位為 cm，預設 0（貼邊）。"""
        raw = self.env['ir.config_parameter'].sudo().get_param(
            'dtsc_print_nesting.print_pool_margin_cm', '0.0',
        )
        try:
            cm = float(raw)
        except (TypeError, ValueError):
            cm = 0.0
        return max(cm, 0.0) * 10.0

    @api.model
    def _print_pool_gap_cm_default(self):
        return self._print_pool_gap_mm() / 10.0

    @api.model
    def _print_pool_gap_diff_film_cm_default(self):
        return self._print_pool_gap_diff_film_mm() / 10.0

    @api.model
    def _print_pool_margin_cm_default(self):
        return self._print_pool_margin_mm() / 10.0

    @api.model
    def _nest_gap_mm_for_material(self, mat):
        """本捲材一般圖間距。"""
        if mat and mat.print_nest_margin_override:
            return max(mat.print_nest_gap_cm or 0.0, 0.0) * 10.0
        return self._print_pool_gap_mm()

    @api.model
    def _nest_gap_diff_film_mm_for_material(self, mat):
        """本捲材異膜圖間距。"""
        if mat and mat.print_nest_margin_override:
            return max(mat.print_nest_gap_diff_film_cm or 0.0, 0.0) * 10.0
        return self._print_pool_gap_diff_film_mm()

    @api.model
    def _nest_margin_mm_for_material(self, mat):
        """本捲材邊距：有自訂則用產品設定，否則用系統預設。"""
        if mat and mat.print_nest_margin_override:
            return max(mat.print_nest_margin_cm or 0.0, 0.0) * 10.0
        return self._print_pool_margin_mm()

    @api.model
    def _nest_params_payload(self, mat):
        """供印刷池 UI 顯示／編輯的間距參數。"""
        override = bool(mat.print_nest_margin_override)
        gap_sys = self._print_pool_gap_cm_default()
        gap_diff_sys = self._print_pool_gap_diff_film_cm_default()
        margin_sys = self._print_pool_margin_cm_default()
        return {
            'override': override,
            'gap_cm': (
                max(mat.print_nest_gap_cm or 0.0, 0.0) if override else gap_sys
            ),
            'gap_diff_film_cm': (
                max(mat.print_nest_gap_diff_film_cm or 0.0, 0.0)
                if override else gap_diff_sys
            ),
            'margin_cm': (
                max(mat.print_nest_margin_cm or 0.0, 0.0)
                if override else margin_sys
            ),
            'gap_system_cm': gap_sys,
            'gap_diff_film_system_cm': gap_diff_sys,
            'margin_system_cm': margin_sys,
            # 相容舊前端欄位名
            'margin_override': override,
        }

    # ------------------------------------------------------------------
    # Public API for OWL
    # ------------------------------------------------------------------
    @api.model
    def optimize_and_refresh(self):
        """重新整理：清掉未釘選的手動門幅，只保留位置釘選，再重算最優分配。

        - pinned=True：位置+門幅保留，當障礙物
        - 僅拖放過、未釘選：清掉，重新參與智能門幅與排版
        """
        self._clear_unpinned_overrides()
        return self.get_pool_overview()

    @api.model
    def _clear_unpinned_overrides(self):
        """刪除未釘選、且無翻轉／旋轉偏好的 pin（僅清手動拖門幅）。

        翻轉／旋轉會寫在 pin 上但不一定釘選，重新整理時要保留朝向。
        """
        pins = self.env['dtsc.print.pool.pin'].search([
            ('pinned', '=', False),
            ('flip_h', '=', False),
            ('rotation', 'in', [0, False]),
        ])
        if pins:
            pins.unlink()
        return True

    @api.model
    def _all_print_roll_materials(self):
        """所有捲材類目（序號追蹤且有門幅設定）。"""
        return self.env['product.template'].search([
            ('tracking', '=', 'serial'),
            ('roll_width_cm', '>', 0),
        ], order='default_code, name, id')

    @api.model
    def get_pool_overview(self):
        """左側列出全部捲材類目（PVC37／PVC51…），方便查看各料舊料用到哪。

        右側點進後仍是：該料全部舊料 + 一卷新料預留。
        """
        self.reassign_pending_materials()
        piece_mat = self._pending_piece_material_map()
        by_mat = defaultdict(list)  # mat_id -> [ml_id, ...]
        pcs_by_mat = defaultdict(int)
        for (ml_id, _idx), mat_id in piece_mat.items():
            if not mat_id:
                continue
            by_mat[mat_id].append(ml_id)
            pcs_by_mat[mat_id] += 1

        # 有待排／有庫存捲／有印刷歷史的類目都要出現；再加上有門幅的捲材主檔
        mat_ids = set(by_mat.keys())
        for mat in self._all_print_roll_materials():
            mat_ids.add(mat.id)
        # 有印刷歷史但可能沒門幅欄位的也納入
        hist_mats = self.env['dtsc.print.piece'].search([
            ('roll_id.stock_lot_id', '!=', False),
            ('lock_state', 'in', ('reserved', 'printed')),
            ('order_id.state', 'not in', ('cancel',)),
        ]).mapped('roll_id.stock_lot_id.product_id.product_tmpl_id')
        mat_ids.update(hist_mats.ids)

        materials = []
        for mat in self.env['product.template'].browse(list(mat_ids)):
            if not mat.exists():
                continue
            # 非捲材略過
            if mat.tracking != 'serial':
                continue
            pending_pcs = pcs_by_mat.get(mat.id, 0)
            ml_ids = by_mat.get(mat.id, [])
            has_leftover = self._material_has_leftover(mat)
            lot_count = len(self._available_lots(mat))
            # 無待排、無庫存捲、無舊料的純主檔不佔左側
            if pending_pcs <= 0 and lot_count <= 0 and not has_leftover:
                continue
            materials.append({
                'id': mat.id,
                'name': mat.display_name,
                'default_code': mat.default_code or '',
                'width_cm': mat.roll_width_cm or 0.0,
                'length_m': mat.roll_length_m or 0.0,
                'pending_pieces': pending_pcs,
                'pending_lines': len(set(ml_ids)),
                'lot_count': lot_count,
                'has_leftover': has_leftover,
            })
        # 待排多的在前 → 有舊料 → 名稱
        materials.sort(key=lambda m: (
            0 if m['pending_pieces'] else 1,
            0 if m['has_leftover'] else 1,
            m['name'] or '',
        ))
        return {'materials': materials}

    @api.model
    def get_material_layout(self, material_id):
        """右側長條：舊料優先排，再預留一條新料。釘選圖塊當障礙物固定。"""
        # 切換材料時不強制清拖放；「重新整理」才走 optimize_and_refresh
        self.reassign_pending_materials()
        mat = self.env['product.template'].browse(material_id)
        if not mat:
            raise UserError(_('請選擇材料。'))
        width_mm = (mat.roll_width_cm or 0.0) * 10.0
        full_len_mm = (mat.roll_length_m or 0.0) * 1000.0
        if not width_mm:
            raise UserError(_('產品「%s」尚未設定寬度(cm)。') % mat.display_name)
        if not full_len_mm:
            full_len_mm = 50000.0

        strips_meta = self._build_strips(mat, width_mm, full_len_mm)
        strip_keys = {s['key'] for s in strips_meta}
        fallback_key = strips_meta[0]['key'] if strips_meta else None

        pin_map = self._pin_map_for_material(mat)
        free_demands, fixed_by_strip = self._split_demands_and_fixed(
            mat, pin_map, strip_keys, fallback_key,
        )

        gap = self._nest_gap_mm_for_material(mat)
        gap_diff = self._nest_gap_diff_film_mm_for_material(mat)
        margin = self._nest_margin_mm_for_material(mat)
        allow_rotate = self._print_pool_allow_rotate()
        engine = NestingEngine(
            roll_width=width_mm,
            gap=gap,
            margin=margin,
            allow_rotate=allow_rotate,
            gap_diff_group=gap_diff,
        )

        remaining = list(free_demands)
        strip_results = []
        for meta in strips_meta:
            capacity = meta['capacity_mm']
            y_offset = meta.get('y_offset_mm') or 0.0
            packable = meta.get('packable', True) and capacity > 1e-6
            if not packable:
                history_pieces = self._history_pieces_for_lot(meta.get('lot_id'))
                strip_results.append({
                    'key': meta['key'],
                    'label': meta['label'],
                    'kind': meta['kind'],
                    'lot_id': meta.get('lot_id'),
                    'lot_name': meta.get('lot_name'),
                    'width_mm': width_mm,
                    'capacity_mm': capacity,
                    'y_offset_mm': y_offset,
                    'used_mm': 0.0,
                    'default_cutoff_mm': 0.0,
                    'pieces': [],
                    'history_pieces': history_pieces,
                    'packable': False,
                })
                continue
            fixed_pins = fixed_by_strip.get(meta['key'], [])
            obstacles = []
            fixed_placements = []
            for pin in fixed_pins:
                if pin.y_mm + pin.height_mm > capacity + 1e-6:
                    # 釘選超出容量：降為自由重排，並解除釘選座標
                    remaining.append(self._pin_to_demand(pin))
                    pin.write({
                        'pinned': False,
                        'x_mm': 0.0,
                        'y_mm': 0.0,
                        'width_mm': 0.0,
                        'height_mm': 0.0,
                        'strip_key': False,
                        'lot_id': False,
                    })
                    continue
                obstacles.append(Obstacle(
                    x=pin.x_mm, y=pin.y_mm,
                    width=pin.width_mm, height=pin.height_mm,
                    gap_group=pin.makeinline_id._print_film_gap_group() if pin.makeinline_id else '',
                ))
                fixed_placements.append(self._pin_to_placement(pin))

            seed = [RollResult(
                width=width_mm,
                used_length=0.0,
                placements=[],
                obstacles=obstacles,
            )]
            packed, leftover = engine.pack(remaining, seed_rolls=seed)
            roll = packed[0] if packed else seed[0]
            kept = list(fixed_placements)
            overflow = []
            for pl in roll.placements:
                if pl.y + pl.height <= capacity + 1e-6:
                    kept.append(pl)
                else:
                    overflow.append(pl)
            for pl in overflow:
                leftover.append(_placement_to_demand(pl))
            for extra in packed[1:]:
                for pl in extra.placements:
                    leftover.append(_placement_to_demand(pl))

            used_free = max((p.y + p.height for p in kept), default=0.0)

            pieces_out = []
            for p in kept:
                meta_p = p.meta or {}
                ml_id = meta_p.get('makeinline_id')
                idx = meta_p.get('idx')
                pin = pin_map.get((ml_id, idx)) if ml_id is not None and idx is not None else None
                bleed_w = bleed_h = 0.0
                preview_url = False
                if ml_id:
                    ml_rec = self.env['dtsc.makeinline'].browse(ml_id)
                    if ml_rec.exists():
                        bleed_w, bleed_h = ml_rec._parse_size_cm()
                        preview_url = self._makeinline_preview_url(ml_rec)
                rotation = 90 if p.rotated else 0
                flip_h = False
                if pin:
                    rotation = self._normalize_rotation(pin.rotation, pin.rotated or p.rotated)
                    flip_h = bool(pin.flip_h)
                pieces_out.append({
                    'key': p.key,
                    'x': p.x,
                    'y': p.y,
                    'w': p.width,
                    'h': p.height,
                    'rotated': rotation in (90, 270),
                    'rotation': rotation,
                    'flip_h': flip_h,
                    'label': meta_p.get('label') or p.key,
                    'makeinline_id': ml_id,
                    'line_qty_index': idx,
                    'piece_idx': idx,
                    'pinned': bool(pin and pin.pinned),
                    'manual_material': bool(pin and pin.material_id),
                    'bleed_w_mm': bleed_w,
                    'bleed_h_mm': bleed_h,
                    'preview_url': preview_url,
                })

            history_pieces = self._history_pieces_for_lot(meta.get('lot_id'))
            strip_results.append({
                'key': meta['key'],
                'label': meta['label'],
                'kind': meta['kind'],
                'lot_id': meta.get('lot_id'),
                'lot_name': meta.get('lot_name'),
                'width_mm': width_mm,
                'capacity_mm': capacity,
                'y_offset_mm': y_offset,
                'used_mm': used_free,
                'default_cutoff_mm': used_free,
                'pieces': pieces_out,
                'history_pieces': history_pieces,
                'packable': True,
            })
            remaining = leftover

        total_demands = len(free_demands) + sum(len(v) for v in fixed_by_strip.values())
        unplaced = [
            {
                'key': d.key,
                'label': (d.meta or {}).get('label'),
                'w': d.width,
                'h': d.height,
                'makeinline_id': (d.meta or {}).get('makeinline_id'),
            }
            for d in remaining
        ]
        return {
            'material': {
                'id': mat.id,
                'name': mat.display_name,
                'width_cm': mat.roll_width_cm or 0.0,
                'length_m': mat.roll_length_m or 0.0,
                'width_mm': width_mm,
                'full_length_mm': full_len_mm,
            },
            'nest_params': self._nest_params_payload(mat),
            'strips': strip_results,
            'unplaced': unplaced,
            'pending_total': total_demands,
            'placed_total': sum(len(s['pieces']) for s in strip_results),
        }

    @api.model
    def set_material_nest_params(self, material_id, params):
        """印刷池：寫入當前捲材的間距／邊距並立即重排。

        params: {
          gap_cm, gap_diff_film_cm, margin_cm: float,
          override / margin_override: bool,  # False=恢復系統預設
        }
        """
        mat = self.env['product.template'].browse(int(material_id))
        if not mat.exists():
            raise UserError(_('請選擇材料。'))
        params = params or {}
        override = bool(params.get('override', params.get('margin_override')))
        vals = {'print_nest_margin_override': override}
        if override:
            def _cm(key, default=0.0):
                try:
                    return max(float(params.get(key)), 0.0)
                except (TypeError, ValueError):
                    return default
            vals.update({
                'print_nest_gap_cm': _cm('gap_cm', 0.5),
                'print_nest_gap_diff_film_cm': _cm('gap_diff_film_cm', 5.0),
                'print_nest_margin_cm': _cm('margin_cm', 0.0),
            })
        mat.write(vals)
        return self.get_material_layout(mat.id)

    @api.model
    def _normalize_rotation(self, rotation, rotated=None):
        """統一為 0/90/180/270；相容舊 rotated 布林。"""
        try:
            rot = int(rotation or 0) % 360
        except (TypeError, ValueError):
            rot = 0
        if rot not in (0, 90, 180, 270):
            rot = (round(rot / 90) * 90) % 360
        if rotation in (None, False, 0) and rotated and rot == 0:
            rot = 90
        return rot

    @api.model
    def toggle_piece_pin(self, makeinline_id, piece_idx, geometry):
        """點擊圖塊：釘選 / 取消釘選。釘選時寫入當前座標，重排不可移動。

        geometry: {
          material_id, strip_key, lot_id,
          x, y, w, h, rotated, rotation, flip_h
        }
        """
        ml = self.env['dtsc.makeinline'].browse(int(makeinline_id))
        if not ml:
            raise UserError(_('項次不存在。'))
        idx = int(piece_idx or 0)
        geometry = geometry or {}
        mat_id = int(geometry.get('material_id') or ml.print_material_id.id or 0)
        if not mat_id:
            raise UserError(_('無法判定圖塊所屬捲材。'))

        Pin = self.env['dtsc.print.pool.pin']
        pin = Pin.search([
            ('makeinline_id', '=', ml.id),
            ('piece_idx', '=', idx),
        ], limit=1)

        if pin and pin.pinned:
            pin.pinned = False
            return {'pinned': False, 'makeinline_id': ml.id, 'piece_idx': idx}

        rotation = self._normalize_rotation(
            geometry.get('rotation'), geometry.get('rotated'),
        )
        vals = {
            'makeinline_id': ml.id,
            'piece_idx': idx,
            'material_id': mat_id,
            'pinned': True,
            'strip_key': geometry.get('strip_key') or False,
            'lot_id': int(geometry['lot_id']) if geometry.get('lot_id') else False,
            'x_mm': float(geometry.get('x') or 0.0),
            'y_mm': float(geometry.get('y') or 0.0),
            'width_mm': float(geometry.get('w') or 0.0),
            'height_mm': float(geometry.get('h') or 0.0),
            'rotated': rotation in (90, 270),
            'rotation': rotation,
            'flip_h': bool(geometry.get('flip_h')),
        }
        if pin:
            pin.write(vals)
        else:
            pin = Pin.create(vals)
        return {'pinned': True, 'makeinline_id': ml.id, 'piece_idx': idx, 'pin_id': pin.id}

    @api.model
    def transform_pool_piece(self, makeinline_id, piece_idx, action, geometry):
        """印刷池圖塊：水平翻轉 / 左轉90 / 右轉90。

        action: flip_h | rotate_ccw | rotate_cw
        會釘選當前座標並更新朝向；超出門幅則報錯。
        """
        ml = self.env['dtsc.makeinline'].browse(int(makeinline_id))
        if not ml:
            raise UserError(_('項次不存在。'))
        idx = int(piece_idx or 0)
        geometry = geometry or {}
        action = (action or '').strip()
        if action not in ('flip_h', 'rotate_cw', 'rotate_ccw'):
            raise UserError(_('未知操作：%s') % action)

        mat_id = int(geometry.get('material_id') or ml.print_material_id.id or 0)
        if not mat_id:
            raise UserError(_('無法判定圖塊所屬捲材。'))
        mat = self.env['product.template'].browse(mat_id)
        roll_w = float(mat.roll_width_cm or 0.0) * 10.0
        if not roll_w:
            raise UserError(_('產品「%s」尚未設定寬度(cm)。') % mat.display_name)

        x = float(geometry.get('x') or 0.0)
        y = float(geometry.get('y') or 0.0)
        w = float(geometry.get('w') or 0.0)
        h = float(geometry.get('h') or 0.0)
        rotation = self._normalize_rotation(
            geometry.get('rotation'), geometry.get('rotated'),
        )
        flip_h = bool(geometry.get('flip_h'))

        if action == 'flip_h':
            flip_h = not flip_h
        elif action == 'rotate_cw':
            w, h = h, w
            rotation = (rotation + 90) % 360
        else:  # rotate_ccw
            w, h = h, w
            rotation = (rotation - 90) % 360

        if x + w > roll_w + 1e-3:
            raise UserError(_(
                '旋轉後寬度 %.1f mm 超出門幅 %.1f mm，請先移到可容納位置或改其他門幅。'
            ) % (w, roll_w))

        Pin = self.env['dtsc.print.pool.pin']
        pin = Pin.search([
            ('makeinline_id', '=', ml.id),
            ('piece_idx', '=', idx),
        ], limit=1)
        # 翻轉／旋轉不自動釘選；保留原本是否已鎖
        keep_pinned = bool(pin.pinned) if pin else False
        vals = {
            'makeinline_id': ml.id,
            'piece_idx': idx,
            'material_id': mat_id,
            'pinned': keep_pinned,
            'strip_key': geometry.get('strip_key') or False,
            'lot_id': int(geometry['lot_id']) if geometry.get('lot_id') else False,
            'x_mm': x,
            'y_mm': y,
            'width_mm': w,
            'height_mm': h,
            'rotated': rotation in (90, 270),
            'rotation': rotation,
            'flip_h': flip_h,
        }
        if pin:
            pin.write(vals)
        else:
            pin = Pin.create(vals)

        layout = self.get_material_layout(mat_id)
        return {
            'ok': True,
            'action': action,
            'rotation': rotation,
            'flip_h': flip_h,
            'pinned': keep_pinned,
            'layout': layout,
        }

    @api.model
    def get_piece_move_targets(self, makeinline_id, piece_idx=None, current_material_id=None):
        """拖動開始：回傳此項次可改放到的其他門幅捲材。"""
        ml = self.env['dtsc.makeinline'].browse(int(makeinline_id))
        if not ml:
            return {'targets': []}
        w_mm, h_mm = ml._parse_size_cm()
        candidates = ml.print_material_candidate_ids or ml._resolve_roll_materials()
        cur = int(current_material_id or 0)
        if not cur:
            pin = self.env['dtsc.print.pool.pin'].search([
                ('makeinline_id', '=', ml.id),
                ('piece_idx', '=', int(piece_idx or 0)),
            ], limit=1)
            cur = (pin.material_id.id if pin else 0) or (ml.print_material_id.id if ml.print_material_id else 0)

        targets = []
        for mat in candidates:
            width = ml._roll_width_mm_of(mat)
            if not ml._piece_fits_roll_width(w_mm, h_mm, width):
                continue
            if mat.id == cur:
                continue
            targets.append({
                'id': mat.id,
                'name': mat.display_name,
                'width_cm': mat.roll_width_cm or 0.0,
                'length_m': mat.roll_length_m or 0.0,
                'has_leftover': self._material_has_leftover(mat),
                'lot_count': len(self._available_lots(mat)),
            })
        targets.sort(key=lambda t: (0 if t['has_leftover'] else 1, t['width_cm'] or 0, t['name'] or ''))
        return {
            'targets': targets,
            'makeinline_id': ml.id,
            'piece_idx': int(piece_idx or 0),
            'label': '%s-%s' % (ml.make_order_id.name or '', ml.sequence or ''),
        }

    @api.model
    def move_piece_to_material(self, makeinline_id, piece_idx, material_id):
        """拖放到其他門幅：寫入指定捲材，清除釘選座標以便在新料上重排。"""
        ml = self.env['dtsc.makeinline'].browse(int(makeinline_id))
        if not ml:
            raise UserError(_('項次不存在。'))
        mat = self.env['product.template'].browse(int(material_id))
        if not mat:
            raise UserError(_('目標捲材不存在。'))
        candidates = ml.print_material_candidate_ids or ml._resolve_roll_materials()
        if mat not in candidates:
            raise UserError(_('「%s」不在此項次可選捲材內。') % mat.display_name)
        w_mm, h_mm = ml._parse_size_cm()
        if not ml._piece_fits_roll_width(w_mm, h_mm, ml._roll_width_mm_of(mat)):
            raise UserError(_('圖塊尺寸放不進「%s」門幅。') % mat.display_name)

        idx = int(piece_idx or 0)
        Pin = self.env['dtsc.print.pool.pin']
        pin = Pin.search([
            ('makeinline_id', '=', ml.id),
            ('piece_idx', '=', idx),
        ], limit=1)
        vals = {
            'makeinline_id': ml.id,
            'piece_idx': idx,
            'material_id': mat.id,
            'pinned': False,
            'strip_key': False,
            'lot_id': False,
            'x_mm': 0.0,
            'y_mm': 0.0,
            'width_mm': 0.0,
            'height_mm': 0.0,
            'rotated': False,
        }
        if pin:
            pin.write(vals)
        else:
            Pin.create(vals)

        # 若該項次已無任何圖塊留在原 print_material_id，順便改預設分配
        piece_mat = self._piece_material_for_line(ml)
        remain = max(int(ml.quantity or 0) - int(ml.print_placed_qty or 0), 0)
        still_on_default = any(
            piece_mat.get(i) == (ml.print_material_id.id if ml.print_material_id else False)
            for i in range(remain)
        )
        if not still_on_default and remain > 0:
            ml.print_material_id = mat.id

        return {
            'ok': True,
            'makeinline_id': ml.id,
            'piece_idx': idx,
            'material_id': mat.id,
            'material_name': mat.display_name,
        }

    @api.model
    def lock_cutoff_to_print_order(self, material_id, strip_cutoffs):
        """
        截斷鎖定生成印刷單。
        strip_cutoffs: [{'key': 'lot:12'|'new:0', 'cutoff_mm': 1234}, ...]
        只鎖定各條 y+h <= cutoff 的圖塊。
        """
        if not strip_cutoffs:
            raise UserError(_('請至少指定一條捲的截斷位置。'))
        mat = self.env['product.template'].browse(material_id)
        layout = self.get_material_layout(material_id)
        cutoff_map = {c['key']: float(c['cutoff_mm']) for c in strip_cutoffs if c.get('key')}

        selected = []
        for strip in layout['strips']:
            cut = cutoff_map.get(strip['key'])
            if cut is None:
                continue
            for p in strip['pieces']:
                if p['y'] + p['h'] <= cut + 1e-6:
                    selected.append({**p, 'strip': strip})

        if not selected:
            raise UserError(_('截斷範圍內沒有可鎖定的圖塊。'))

        qty_by_ml = defaultdict(int)
        for p in selected:
            ml_id = p.get('makeinline_id')
            if ml_id:
                qty_by_ml[ml_id] += 1

        order = self.env['dtsc.print.order'].create({
            'material_product_id': mat.id,
            'roll_width_mm': layout['material']['width_mm'],
            'gap_mm': self._nest_gap_mm_for_material(mat),
            'margin_mm': self._nest_margin_mm_for_material(mat),
            'allow_rotate': self._print_pool_allow_rotate(),
            'note': _('由印刷池截斷鎖定產生'),
        })
        Line = self.env['dtsc.print.order.line']
        line_by_ml = {}
        for ml_id, qty in qty_by_ml.items():
            ml = self.env['dtsc.makeinline'].browse(ml_id)
            w, h = ml._parse_size_cm()
            line = Line.create({
                'order_id': order.id,
                'makeinline_id': ml.id,
                'piece_w_mm': w,
                'piece_h_mm': h,
                'qty': qty,
                'delivery_date': ml.make_order_id.delivery_date if ml.make_order_id else False,
            })
            line_by_ml[ml_id] = line

        rolls_by_key = {}
        seq = 1
        Piece = self.env['dtsc.print.piece']
        Pin = self.env['dtsc.print.pool.pin']
        for strip in layout['strips']:
            cut = cutoff_map.get(strip['key'])
            if cut is None:
                continue
            strip_pieces = [
                p for p in strip['pieces']
                if p['y'] + p['h'] <= cut + 1e-6
            ]
            if not strip_pieces:
                continue
            if not strip.get('lot_id'):
                raise UserError(_(
                    '截斷區落在「待領料」新料預留上，請先在倉庫領用實體捲（或選有庫存的新料條）再生成印刷單，以便自動扣料。'
                ))
            y_off = strip.get('y_offset_mm') or 0.0
            free_used = max(p['y'] + p['h'] for p in strip_pieces)
            area = sum(float(p['w']) * float(p['h']) for p in strip_pieces)
            width_mm = float(strip['width_mm'] or 0.0)
            util = round(100.0 * area / (width_mm * free_used), 1) if width_mm and free_used else 0.0
            roll = self.env['dtsc.print.roll'].create({
                'order_id': order.id,
                'sequence': seq,
                'roll_width_mm': strip['width_mm'],
                'used_length_mm': y_off + free_used,
                'utilization_rate': util,
                'stock_lot_id': strip.get('lot_id') or False,
                'name': strip.get('lot_name') or ('%s-R%02d' % (order.name, seq)),
            })
            rolls_by_key[strip['key']] = roll
            seq += 1
            for p in strip_pieces:
                ml_id = p.get('makeinline_id')
                rotation = self._normalize_rotation(p.get('rotation'), p.get('rotated'))
                Piece.create({
                    'order_id': order.id,
                    'roll_id': roll.id,
                    'order_line_id': line_by_ml[ml_id].id if ml_id in line_by_ml else False,
                    'makeinline_id': ml_id,
                    'label': p.get('label') or '',
                    'x_mm': p['x'],
                    'y_mm': p['y'] + y_off,
                    'width_mm': p['w'],
                    'height_mm': p['h'],
                    'rotated': rotation in (90, 270),
                    'rotation': rotation,
                    'flip_h': bool(p.get('flip_h')),
                    'lock_state': 'reserved',
                })
                # 已進印刷單：清掉對應釘選
                idx = p.get('piece_idx')
                if ml_id is not None and idx is not None:
                    Pin.search([
                        ('makeinline_id', '=', ml_id),
                        ('piece_idx', '=', int(idx)),
                    ]).unlink()
            roll._refresh_preview_svg()
            # 依大圖項次已上傳 TIFF 自動合成整版（含留白）；失敗不擋出單
            try:
                roll._compose_layout_tiff()
            except Exception as err:  # noqa: BLE001
                roll.write({
                    'layout_tiff': False,
                    'layout_tiff_filename': False,
                    'layout_tiff_note': _(
                        '排版 TIFF 自動合成失敗：%s\n'
                        '大圖訂單裡的 TIFF 仍在，請打開本捲點「重新合成排版TIFF」（無需再上傳）。'
                    ) % err,
                })

        order.state = 'confirmed'
        order.need_renest = False
        order.line_ids._sync_placed_qty()
        # 生成印刷單即自動寫入捲料扣料表並扣才數（與掃碼行為一致）
        order._print_nesting_auto_deduct()

        return {
            'order_id': order.id,
            'order_name': order.name,
            'piece_count': len(selected),
            'tiff_ok': all(r._has_layout_tiff_file() for r in order.roll_ids),
            'action': {
                'type': 'ir.actions.act_window',
                'name': _('印刷單 %s') % order.name,
                'res_model': 'dtsc.print.order',
                'res_id': order.id,
                'view_mode': 'form',
                'views': [(False, 'form')],
                'target': 'current',
                'context': {'form_view_initial_mode': 'readonly'},
            },
        }

    @api.model
    def pack_all_pending_to_strip(self, material_id, strip_key):
        """把本材料待排圖塊全部改排到指定捲（並釘選），方便只在新料上出單。"""
        mat = self.env['product.template'].browse(int(material_id))
        if not mat:
            raise UserError(_('請選擇材料。'))
        width_mm = (mat.roll_width_cm or 0.0) * 10.0
        full_len_mm = (mat.roll_length_m or 0.0) * 1000.0 or 50000.0
        if not width_mm:
            raise UserError(_('產品「%s」尚未設定寬度(cm)。') % mat.display_name)

        strips_meta = self._build_strips(mat, width_mm, full_len_mm)
        target = next((s for s in strips_meta if s['key'] == strip_key), None)
        if not target:
            raise UserError(_('找不到目標捲料條帶。'))
        if not target.get('packable', True) or float(target.get('capacity_mm') or 0) <= 1e-6:
            raise UserError(_('此捲不可排版。'))
        if not target.get('lot_id'):
            raise UserError(_('請先選有實體序號的新料捲，待領料預留無法釘選出單。'))

        Pin = self.env['dtsc.print.pool.pin']
        # 解除本材料待排圖塊的釘選，全部改排到目標捲
        pins = Pin.search([('material_id', '=', mat.id)])
        for pin in pins:
            ml = pin.makeinline_id
            if not ml:
                continue
            remain = max(int(ml.quantity or 0) - int(ml.print_placed_qty or 0), 0)
            if pin.piece_idx is not None and int(pin.piece_idx) >= remain:
                continue
            pin.write({
                'pinned': False,
                'x_mm': 0.0,
                'y_mm': 0.0,
                'width_mm': 0.0,
                'height_mm': 0.0,
                'strip_key': False,
                'lot_id': False,
            })

        pin_map = self._pin_map_for_material(mat)
        free_demands, _fixed = self._split_demands_and_fixed(
            mat, pin_map, {strip_key}, strip_key,
        )
        if not free_demands:
            raise UserError(_('目前沒有可排到此捲的待排圖塊。'))

        engine = NestingEngine(
            roll_width=width_mm,
            gap=self._nest_gap_mm_for_material(mat),
            margin=self._nest_margin_mm_for_material(mat),
            allow_rotate=self._print_pool_allow_rotate(),
            gap_diff_group=self._nest_gap_diff_film_mm_for_material(mat),
        )
        capacity = float(target['capacity_mm'])
        seed = [RollResult(width=width_mm, used_length=0.0, placements=[], obstacles=[])]
        packed, leftover = engine.pack(list(free_demands), seed_rolls=seed)
        roll = packed[0] if packed else seed[0]
        kept = []
        for pl in roll.placements:
            if pl.y + pl.height <= capacity + 1e-6:
                kept.append(pl)
            else:
                leftover.append(_placement_to_demand(pl))
        for extra in packed[1:]:
            for pl in extra.placements:
                leftover.append(_placement_to_demand(pl))

        for pl in kept:
            meta_p = pl.meta or {}
            ml_id = meta_p.get('makeinline_id')
            idx = meta_p.get('idx')
            if ml_id is None or idx is None:
                continue
            rotation = 90 if pl.rotated else 0
            pin = Pin.search([
                ('makeinline_id', '=', ml_id),
                ('piece_idx', '=', int(idx)),
            ], limit=1)
            vals = {
                'makeinline_id': ml_id,
                'piece_idx': int(idx),
                'material_id': mat.id,
                'pinned': True,
                'strip_key': strip_key,
                'lot_id': target.get('lot_id') or False,
                'x_mm': pl.x,
                'y_mm': pl.y,
                'width_mm': pl.width,
                'height_mm': pl.height,
                'rotated': rotation in (90, 270),
                'rotation': rotation,
                'flip_h': bool(meta_p.get('flip_h')),
            }
            if pin:
                pin.write(vals)
            else:
                Pin.create(vals)

        layout = self.get_material_layout(material_id)
        return {
            'ok': True,
            'placed': len(kept),
            'unplaced': len(leftover),
            'strip_key': strip_key,
            'layout': layout,
        }

    @api.model
    def archive_strip_lot(self, material_id, lot_id):
        """印刷池「材料耗盡」：扣料表材料耗盡 + 捲料歸檔。"""
        lot = self.env['stock.lot'].browse(int(lot_id))
        if not lot.exists():
            raise UserError(_('捲料不存在。'))
        if lot.print_archived:
            raise UserError(_('捲料「%s」已歸檔。') % lot.display_name)
        lot.action_print_archive_exhausted()
        layout = self.get_material_layout(material_id) if material_id else False
        return {
            'ok': True,
            'lot_id': lot.id,
            'lot_name': lot.name,
            'layout': layout,
        }

    # ------------------------------------------------------------------
    # 多門幅智能分配
    # ------------------------------------------------------------------
    @api.model
    def reassign_pending_materials(self):
        """對印刷池待排項次重算最適捲材門幅。

        規則（可放下的候選中）：
        1. 優先有舊料（半截捲）庫存的門幅
        2. 再選能放下圖塊的最窄門幅（省料）
        3. 同寬則庫存捲數多者優先

        已有 reserved/printed 圖塊的項次不改分配。
        已手動指定門幅（pin）的圖塊不受影響；此處只改 print_material_id 預設。
        """
        since = self._pool_since()
        lines = self.env['dtsc.makeinline'].search([
            ('need_print_nesting', '=', True),
            ('print_state', 'in', ('none', 'partial')),
            ('make_order_id.install_state', 'not in', ('stock_in', 'cancel')),
            ('make_order_id.create_date', '>=', since),
            ('print_material_candidate_ids', '!=', False),
        ])
        ordered = lines.sorted(
            key=lambda l: max(l._parse_size_cm() or (0, 0)),
            reverse=True,
        )
        self._assign_materials_for_lines(ordered)
        return True

    @api.model
    def _assign_materials_for_lines(self, lines):
        """為給定 makeinline 寫入 print_material_id（未手動指定的圖塊預設門幅）。"""
        leftover_cache = {}
        lot_count_cache = {}

        def has_leftover(mat):
            mid = mat.id
            if mid not in leftover_cache:
                leftover_cache[mid] = self._material_has_leftover(mat)
            return leftover_cache[mid]

        def lot_count(mat):
            mid = mat.id
            if mid not in lot_count_cache:
                lot_count_cache[mid] = len(self._available_lots(mat))
            return lot_count_cache[mid]

        for ml in lines:
            if ml._has_locked_print_pieces():
                continue
            candidates = ml.print_material_candidate_ids or ml._resolve_roll_materials()
            if not candidates:
                if ml.print_material_id:
                    ml.print_material_id = False
                continue
            w_mm, h_mm = ml._parse_size_cm()
            fitting = self.env['product.template']
            for mat in candidates:
                width = ml._roll_width_mm_of(mat)
                if ml._piece_fits_roll_width(w_mm, h_mm, width):
                    fitting |= mat
            pool = fitting or candidates
            best = min(
                pool,
                key=lambda m: (
                    0 if has_leftover(m) else 1,
                    ml._roll_width_mm_of(m) or 1e12,
                    -lot_count(m),
                    m.id,
                ),
            )
            if ml.print_material_id != best:
                ml.print_material_id = best.id

    def _material_has_leftover(self, mat):
        """是否有半截舊料可排。"""
        full_len_mm = (mat.roll_length_m or 0.0) * 1000.0 or 50000.0
        for lot in self._available_lots(mat):
            rem, used, _cap = self._lot_remaining_mm(mat, lot, full_len_mm)
            if rem > 1.0 and (used > 1.0 or rem < full_len_mm * 0.98):
                return True
        return False

    # ------------------------------------------------------------------
    # Pin / piece helpers
    # ------------------------------------------------------------------
    def _pin_map_for_material(self, mat):
        pins = self.env['dtsc.print.pool.pin'].search([('material_id', '=', mat.id)])
        return {(p.makeinline_id.id, p.piece_idx): p for p in pins}

    def _piece_material_for_line(self, ml):
        """回傳 {piece_idx: material_id}（含 pin 覆蓋）。"""
        remain = max(int(ml.quantity or 0) - int(ml.print_placed_qty or 0), 0)
        default = ml.print_material_id.id if ml.print_material_id else False
        pins = {
            p.piece_idx: p.material_id.id
            for p in self.env['dtsc.print.pool.pin'].search([
                ('makeinline_id', '=', ml.id),
            ])
        }
        return {i: pins.get(i, default) for i in range(remain)}

    def _pending_piece_material_map(self):
        """所有待排圖塊 → 所屬門幅。"""
        result = {}
        for ml in self._pending_makeinlines_base():
            for idx, mat_id in self._piece_material_for_line(ml).items():
                result[(ml.id, idx)] = mat_id
        return result

    def _split_demands_and_fixed(self, mat, pin_map, strip_keys, fallback_key):
        """拆成自由需求 + 依 strip 固定的釘選。

        圖塊歸屬以 pin.material_id（手動拖放）優先，否則用 print_material_id。
        已拖到其他門幅的塊絕不能再出現在本材料上。
        """
        free = []
        fixed_by_strip = defaultdict(list)
        lines = self._pending_makeinlines_base()
        for ml in lines:
            qty = int(ml.quantity or 0)
            placed = int(ml.print_placed_qty or 0)
            remain = max(qty - placed, 0)
            if remain <= 0:
                continue
            w, h = ml._parse_size_cm()
            if not w or not h:
                continue
            label = '%s-%s' % (ml.make_order_id.name or '', ml.sequence or '')
            # 逐塊有效門幅（含拖到其他規格的覆蓋）
            piece_mats = self._piece_material_for_line(ml)
            for i in range(remain):
                if piece_mats.get(i) != mat.id:
                    continue
                pin = pin_map.get((ml.id, i))
                if pin and pin.pinned and pin.width_mm > 0 and pin.height_mm > 0:
                    sk = pin.strip_key if pin.strip_key in strip_keys else fallback_key
                    if sk:
                        if pin.strip_key != sk:
                            pin.strip_key = sk
                            pin.lot_id = False
                        fixed_by_strip[sk].append(pin)
                    else:
                        free.append(self._pin_to_demand(pin))
                else:
                    free.append(self._piece_to_demand(ml, i, label, w, h, pin))
        return free, fixed_by_strip

    def _piece_to_demand(self, ml, idx, label, w, h, pin=None):
        """自由需求；若有 pin 上的旋轉／翻轉偏好則帶入 force_rotation。"""
        meta = {
            'makeinline_id': ml.id,
            'label': label,
            'idx': idx,
            'gap_group': ml._print_film_gap_group() if ml else '',
        }
        if pin:
            rot = self._normalize_rotation(pin.rotation, pin.rotated)
            if rot:
                meta['force_rotation'] = rot
            if pin.flip_h:
                meta['flip_h'] = True
        return PieceDemand(
            key='%s:%s' % (ml.id, idx),
            width=w,
            height=h,
            meta=meta,
        )

    def _pin_to_demand(self, pin):
        ml = pin.makeinline_id
        w, h = ml._parse_size_cm()
        # 若釘選有旋轉後尺寸，還原需求用原始出血尺寸
        label = '%s-%s' % (ml.make_order_id.name or '', ml.sequence or '')
        return self._piece_to_demand(ml, pin.piece_idx, label, w, h, pin)

    def _pin_to_placement(self, pin):
        ml = pin.makeinline_id
        label = '%s-%s' % (ml.make_order_id.name or '', ml.sequence or '')
        return Placement(
            key='%s:%s' % (ml.id, pin.piece_idx),
            x=pin.x_mm,
            y=pin.y_mm,
            width=pin.width_mm,
            height=pin.height_mm,
            rotated=bool(pin.rotated),
            meta={
                'makeinline_id': ml.id,
                'label': label,
                'idx': pin.piece_idx,
                'gap_group': ml._print_film_gap_group() if ml else '',
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _pool_since(self):
        """只收此時間之後新產生的內部工單。未設定時記為現在，存量不進池。"""
        icp = self.env['ir.config_parameter'].sudo()
        key = 'dtsc_print_nesting.pool_since'
        value = icp.get_param(key)
        if not value:
            value = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            icp.set_param(key, value)
        return fields.Datetime.to_datetime(value)

    def _pending_makeinlines_base(self):
        """待排項次（不強制已有 print_material_id，因可能只有 pin 指定門幅）。"""
        since = self._pool_since()
        base_domain = [
            ('need_print_nesting', '=', True),
            ('print_state', 'in', ('none', 'partial')),
            ('make_order_id.install_state', 'not in', ('stock_in', 'cancel')),
            ('make_order_id.create_date', '>=', since),
        ]
        lines = self.env['dtsc.makeinline'].search(
            base_domain + [('print_material_id', '!=', False)]
        )
        pin_ml_ids = self.env['dtsc.print.pool.pin'].search([]).mapped('makeinline_id').ids
        if pin_ml_ids:
            extra = self.env['dtsc.makeinline'].search(
                base_domain + [('id', 'in', pin_ml_ids)]
            )
            lines |= extra
        return lines

    def _pending_makeinlines(self):
        """相容舊呼叫：有預設門幅的待排項次。"""
        return self._pending_makeinlines_base().filtered(lambda l: l.print_material_id)

    def _available_lots(self, mat):
        """當前材料全部未歸檔捲料：有庫存 + 有印刷歷史（即使庫存已扣完仍可查看）。"""
        products = self.env['product.product'].search([('product_tmpl_id', '=', mat.id)])
        if not products:
            return self.env['stock.lot']
        Lot = self.env['stock.lot']
        quants = self.env['stock.quant'].search([
            ('product_id', 'in', products.ids),
            ('quantity', '>', 0),
            ('lot_id', '!=', False),
            ('location_id.usage', '=', 'internal'),
        ])
        lots = quants.mapped('lot_id')
        hist_lot_ids = self.env['dtsc.print.piece'].search([
            ('roll_id.stock_lot_id.product_id', 'in', products.ids),
            ('lock_state', 'in', ('reserved', 'printed')),
            ('order_id.state', 'not in', ('cancel',)),
        ]).mapped('roll_id.stock_lot_id').ids
        if hist_lot_ids:
            lots |= Lot.browse(hist_lot_ids)
        return lots.filtered(lambda l: l and not l.print_archived)

    def _lot_remaining_mm(self, mat, lot, full_len_mm):
        """估算該實體捲剩餘可排長度(mm)。"""
        pieces = self.env['dtsc.print.piece'].search([
            ('roll_id.stock_lot_id', '=', lot.id),
            ('lock_state', 'in', ('reserved', 'printed')),
            ('order_id.state', 'not in', ('cancel',)),
        ])
        used = 0.0
        if pieces:
            by_roll = defaultdict(list)
            for p in pieces:
                by_roll[p.roll_id.id].append(p)
            for plist in by_roll.values():
                used = max(used, max(x.y_mm + x.height_mm for x in plist))

        quant_qty = sum(self.env['stock.quant'].search([
            ('lot_id', '=', lot.id),
            ('location_id.usage', '=', 'internal'),
        ]).mapped('quantity'))
        capacity = full_len_mm
        if 0 < quant_qty < 1:
            capacity = full_len_mm * quant_qty
        remaining = max(capacity - used, 0.0)
        return remaining, used, capacity

    @api.model
    def _checkout_preview_url(self, checkout_line):
        """大圖項次 TIFF 預覽圖 URL（不讀二進位內容）。"""
        if not checkout_line:
            return False
        att = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', 'dtsc.checkoutline'),
            ('res_id', '=', checkout_line.id),
            ('res_field', '=', 'layout_tiff_preview'),
            ('file_size', '>', 0),
        ], limit=1)
        if not att:
            return False
        unique = att.write_date or att.id
        return '/web/image/dtsc.checkoutline/%s/layout_tiff_preview?unique=%s' % (
            checkout_line.id, unique,
        )

    @api.model
    def _makeinline_preview_url(self, makeinline):
        if not makeinline:
            return False
        return self._checkout_preview_url(makeinline.checkout_line_id)

    def _history_pieces_for_lot(self, lot_id):
        """舊料已占用區：已確認／已印刷圖塊（灰塊顯示印刷單號）。"""
        if not lot_id:
            return []
        pieces = self.env['dtsc.print.piece'].search([
            ('roll_id.stock_lot_id', '=', int(lot_id)),
            ('lock_state', 'in', ('reserved', 'printed')),
            ('order_id.state', 'in', ('nested', 'confirmed', 'done')),
        ], order='y_mm, x_mm, id')
        out = []
        for p in pieces:
            order_name = p.order_id.name or ''
            out.append({
                'key': 'hist:%s' % p.id,
                'x': p.x_mm,
                'y': p.y_mm,
                'w': p.width_mm,
                'h': p.height_mm,
                'rotated': bool(p.rotated),
                'label': order_name or (p.label or ''),
                'order_name': order_name,
                'piece_label': p.label or '',
                'history': True,
                'lock_state': p.lock_state,
                'preview_url': self._makeinline_preview_url(p.makeinline_id),
            })
        return out

    def _build_strips(self, mat, width_mm, full_len_mm):
        """當前材料捲料條帶。

        - 未歸檔且已用過／有印刷歷史／剩餘明顯少於整捲 → 舊料（可多卷）
        - 整捲未開封只留 1 條「新料預留」
        - 點「材料耗盡」歸檔後不再出現；新料出過印刷單後自動變成舊料
        """
        lots = self._available_lots(mat)
        leftover_rows = []
        virgin_candidate = None
        empty_rows = []

        for lot in lots:
            rem, used, cap = self._lot_remaining_mm(mat, lot, full_len_mm)
            has_hist = bool(self.env['dtsc.print.piece'].search_count([
                ('roll_id.stock_lot_id', '=', lot.id),
                ('lock_state', 'in', ('reserved', 'printed')),
                ('order_id.state', 'not in', ('cancel',)),
            ]))
            is_partial = used > 1.0 or rem < full_len_mm * 0.98
            has_content = used > 1.0 or has_hist

            if rem <= 1.0:
                # 已用盡但仍有歷史：展示方便查舊單；無歷史則跳過
                if has_hist:
                    empty_rows.append({
                        'key': 'lot:%s' % lot.id,
                        'label': _('已用盡 %s（可歸檔）') % lot.name,
                        'kind': 'empty',
                        'lot_id': lot.id,
                        'lot_name': lot.name,
                        'capacity_mm': 0.0,
                        'y_offset_mm': used,
                        'packable': False,
                    })
                continue

            if is_partial or has_content:
                leftover_rows.append({
                    'key': 'lot:%s' % lot.id,
                    'label': _('舊料 %s（剩 %.2f m）') % (lot.name, rem / 1000.0),
                    'kind': 'leftover',
                    'lot_id': lot.id,
                    'lot_name': lot.name,
                    'capacity_mm': rem,
                    'y_offset_mm': used,
                    'packable': True,
                    'sort_content': 0 if has_content else 1,
                    'sort_rem': rem,
                })
            else:
                # 整捲未開封：只挑一卷當「新料預留」
                if virgin_candidate is None:
                    virgin_candidate = lot

        leftover_rows.sort(key=lambda r: (r.get('sort_content', 1), r.get('sort_rem', 0)))
        strips = leftover_rows

        if virgin_candidate:
            strips.append({
                'key': 'lot:%s' % virgin_candidate.id,
                'label': _('新料預留 %s（整捲 %.2f m）') % (
                    virgin_candidate.name, full_len_mm / 1000.0,
                ),
                'kind': 'new',
                'lot_id': virgin_candidate.id,
                'lot_name': virgin_candidate.name,
                'capacity_mm': full_len_mm,
                'y_offset_mm': 0.0,
                'packable': True,
            })
        else:
            strips.append({
                'key': 'new:0',
                'label': _('新料預留（整捲 %.2f m，待領料）') % (full_len_mm / 1000.0),
                'kind': 'new',
                'lot_id': False,
                'lot_name': False,
                'capacity_mm': full_len_mm,
                'y_offset_mm': 0.0,
                'packable': True,
            })

        # 已用盡但有歷史：放最下面方便查看／歸檔
        strips.extend(empty_rows)
        return strips
