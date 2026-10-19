# -*- coding: utf-8 -*-
"""印刷池：按材料可視化排版，舊料優先 + 預留新料，截斷鎖定成印刷單。"""
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .nesting_engine import NestingEngine, PieceDemand, RollResult


def _placement_to_demand(pl):
    """Restore original demand size from a placement (undo rotation for re-queue)."""
    w = pl.height if pl.rotated else pl.width
    h = pl.width if pl.rotated else pl.height
    return PieceDemand(key=pl.key, width=w, height=h, meta=dict(pl.meta or {}))



class PrintPool(models.AbstractModel):
    _name = 'dtsc.print.pool'
    _description = '印刷池'

    # ------------------------------------------------------------------
    # Public API for OWL
    # ------------------------------------------------------------------
    @api.model
    def get_pool_overview(self):
        """左側材料列表。"""
        lines = self._pending_makeinlines()
        by_mat = defaultdict(list)
        for ml in lines:
            mat = ml.print_material_id
            if not mat:
                continue
            by_mat[mat.id].append(ml)

        materials = []
        for mat_id, mls in by_mat.items():
            mat = self.env['product.template'].browse(mat_id)
            pending_pcs = 0
            for ml in mls:
                pending_pcs += max((ml.quantity or 0) - (ml.print_placed_qty or 0), 0)
            if pending_pcs <= 0:
                continue
            materials.append({
                'id': mat.id,
                'name': mat.display_name,
                'width_cm': mat.roll_width_cm or 0.0,
                'length_m': mat.roll_length_m or 0.0,
                'pending_pieces': pending_pcs,
                'pending_lines': len(mls),
                'lot_count': len(self._available_lots(mat)),
            })
        materials.sort(key=lambda m: (-m['pending_pieces'], m['name'] or ''))
        return {'materials': materials}

    @api.model
    def get_material_layout(self, material_id):
        """右側長條：舊料優先排，再預留一條新料。"""
        mat = self.env['product.template'].browse(material_id)
        if not mat:
            raise UserError(_('請選擇材料。'))
        width_mm = (mat.roll_width_cm or 0.0) * 10.0
        full_len_mm = (mat.roll_length_m or 0.0) * 1000.0
        if not width_mm:
            raise UserError(_('產品「%s」尚未設定寬度(cm)。') % mat.display_name)
        if not full_len_mm:
            # 無標準長度時給一個可視預設（50m），僅用於排版預覽
            full_len_mm = 50000.0

        demands = self._build_demands(mat)
        strips_meta = self._build_strips(mat, width_mm, full_len_mm)
        gap = 2.0
        engine = NestingEngine(roll_width=width_mm, gap=gap, margin=0.0, allow_rotate=True)

        remaining = list(demands)
        strip_results = []
        for meta in strips_meta:
            # 座標系：僅針對「剩餘可排區」從 0 起算；寫入印刷單時再加 y_offset
            capacity = meta['capacity_mm']
            y_offset = meta.get('y_offset_mm') or 0.0
            seed = [RollResult(
                width=width_mm,
                used_length=0.0,
                placements=[],
                obstacles=[],
            )]
            packed, leftover = engine.pack(remaining, seed_rolls=seed)
            roll = packed[0] if packed else seed[0]
            kept = []
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

            strip_results.append({
                'key': meta['key'],
                'label': meta['label'],
                'kind': meta['kind'],  # leftover | new
                'lot_id': meta.get('lot_id'),
                'lot_name': meta.get('lot_name'),
                'width_mm': width_mm,
                'capacity_mm': capacity,
                'y_offset_mm': y_offset,
                'used_mm': used_free,
                'default_cutoff_mm': used_free,
                'pieces': [
                    {
                        'key': p.key,
                        'x': p.x,
                        'y': p.y,
                        'w': p.width,
                        'h': p.height,
                        'rotated': p.rotated,
                        'label': (p.meta or {}).get('label') or p.key,
                        'makeinline_id': (p.meta or {}).get('makeinline_id'),
                        'line_qty_index': (p.meta or {}).get('idx'),
                    }
                    for p in kept
                ],
            })
            remaining = leftover

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
            'strips': strip_results,
            'unplaced': unplaced,
            'pending_total': len(demands),
            'placed_total': sum(len(s['pieces']) for s in strip_results),
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

        selected = []  # piece dicts
        for strip in layout['strips']:
            cut = cutoff_map.get(strip['key'])
            if cut is None:
                continue
            for p in strip['pieces']:
                if p['y'] + p['h'] <= cut + 1e-6:
                    selected.append({**p, 'strip': strip})

        if not selected:
            raise UserError(_('截斷範圍內沒有可鎖定的圖塊。'))

        # 聚合 makeinline → qty
        qty_by_ml = defaultdict(int)
        for p in selected:
            ml_id = p.get('makeinline_id')
            if ml_id:
                qty_by_ml[ml_id] += 1

        order = self.env['dtsc.print.order'].create({
            'material_product_id': mat.id,
            'roll_width_mm': layout['material']['width_mm'],
            'gap_mm': 2.0,
            'allow_rotate': True,
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

        # 按 strip 建 roll + piece（直接寫座標，狀態 reserved）
        rolls_by_key = {}
        seq = 1
        Piece = self.env['dtsc.print.piece']
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
            y_off = strip.get('y_offset_mm') or 0.0
            roll = self.env['dtsc.print.roll'].create({
                'order_id': order.id,
                'sequence': seq,
                'roll_width_mm': strip['width_mm'],
                'used_length_mm': y_off + max(p['y'] + p['h'] for p in strip_pieces),
                'stock_lot_id': strip.get('lot_id') or False,
                'name': strip.get('lot_name') or ('%s-R%02d' % (order.name, seq)),
            })
            rolls_by_key[strip['key']] = roll
            seq += 1
            for p in strip_pieces:
                ml_id = p.get('makeinline_id')
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
                    'rotated': p.get('rotated'),
                    'lock_state': 'reserved',
                })
            roll._refresh_preview_svg()

        order.state = 'confirmed'
        order.need_renest = False
        order.line_ids._sync_placed_qty()

        return {
            'order_id': order.id,
            'order_name': order.name,
            'piece_count': len(selected),
            'action': {
                'type': 'ir.actions.act_window',
                'res_model': 'dtsc.print.order',
                'res_id': order.id,
                'view_mode': 'form',
                'target': 'current',
            },
        }

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

    def _pending_makeinlines(self):
        since = self._pool_since()
        return self.env['dtsc.makeinline'].search([
            ('need_print_nesting', '=', True),
            ('print_state', 'in', ('none', 'partial')),
            ('make_order_id.install_state', 'not in', ('stock_in', 'cancel')),
            ('print_material_id', '!=', False),
            ('make_order_id.create_date', '>=', since),
        ])

    def _available_lots(self, mat):
        products = self.env['product.product'].search([('product_tmpl_id', '=', mat.id)])
        if not products:
            return self.env['stock.lot']
        quants = self.env['stock.quant'].search([
            ('product_id', 'in', products.ids),
            ('quantity', '>', 0),
            ('lot_id', '!=', False),
            ('location_id.usage', '=', 'internal'),
        ])
        return quants.mapped('lot_id')

    def _lot_remaining_mm(self, mat, lot, full_len_mm):
        """估算該實體捲剩餘可排長度(mm)。"""
        # 已在印刷單 reserved/printed 占用的長度
        pieces = self.env['dtsc.print.piece'].search([
            ('roll_id.stock_lot_id', '=', lot.id),
            ('lock_state', 'in', ('reserved', 'printed')),
            ('order_id.state', 'not in', ('cancel',)),
        ])
        used = 0.0
        if pieces:
            # 按 roll 分開取 max
            by_roll = defaultdict(list)
            for p in pieces:
                by_roll[p.roll_id.id].append(p)
            for plist in by_roll.values():
                used = max(used, max(x.y_mm + x.height_mm for x in plist))

        # 庫存比例：serial 通常 1 捲；若 qty<1 按比例縮減容量
        quant_qty = sum(self.env['stock.quant'].search([
            ('lot_id', '=', lot.id),
            ('location_id.usage', '=', 'internal'),
        ]).mapped('quantity'))
        capacity = full_len_mm
        if 0 < quant_qty < 1:
            capacity = full_len_mm * quant_qty
        remaining = max(capacity - used, 0.0)
        return remaining, used, capacity

    def _build_strips(self, mat, width_mm, full_len_mm):
        """舊料（剩餘>0）在前，最後一條預留新料。"""
        strips = []
        lots = self._available_lots(mat)
        lot_rows = []
        for lot in lots:
            rem, used, cap = self._lot_remaining_mm(mat, lot, full_len_mm)
            if rem <= 1.0:
                continue
            # 只把「已用過 / 半截料」當舊料；整捲未開的留給「新料預留」
            is_partial = used > 1.0 or rem < full_len_mm * 0.98
            if not is_partial:
                continue
            lot_rows.append({
                'key': 'lot:%s' % lot.id,
                'label': _('舊料 %s（剩 %.2f m）') % (lot.name, rem / 1000.0),
                'kind': 'leftover',
                'lot_id': lot.id,
                'lot_name': lot.name,
                'capacity_mm': rem,  # 僅剩餘可排區
                'y_offset_mm': used,  # 寫回實體捲座標時偏移
                'sort_rem': rem,
            })
        # 剩餘少的先用（接近用完的舊料優先消化）
        lot_rows.sort(key=lambda r: r['sort_rem'])
        strips.extend(lot_rows)

        # 預留新料：優先綁一筆未開封的庫存 Lot；否則虛擬新料
        virgin = None
        for lot in lots:
            rem, used, cap = self._lot_remaining_mm(mat, lot, full_len_mm)
            if used <= 1.0 and rem >= full_len_mm * 0.98:
                virgin = lot
                break
        if virgin:
            strips.append({
                'key': 'lot:%s' % virgin.id,
                'label': _('新料預留 %s（整捲 %.2f m）') % (virgin.name, full_len_mm / 1000.0),
                'kind': 'new',
                'lot_id': virgin.id,
                'lot_name': virgin.name,
                'capacity_mm': full_len_mm,
                'y_offset_mm': 0.0,
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
            })
        return strips

    def _build_demands(self, mat):
        lines = self._pending_makeinlines().filtered(lambda l: l.print_material_id == mat)
        demands = []
        for ml in lines:
            remain = max((ml.quantity or 0) - (ml.print_placed_qty or 0), 0)
            if remain <= 0:
                continue
            w, h = ml._parse_size_cm()
            if not w or not h:
                continue
            label = '%s-%s' % (ml.make_order_id.name or '', ml.sequence or '')
            for i in range(remain):
                demands.append(PieceDemand(
                    key='%s:%s' % (ml.id, i),
                    width=w,
                    height=h,
                    meta={
                        'makeinline_id': ml.id,
                        'label': label,
                        'idx': i,
                    },
                ))
        return demands
