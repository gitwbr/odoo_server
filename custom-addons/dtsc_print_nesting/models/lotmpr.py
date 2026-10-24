# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class LotMpr(models.Model):
    _inherit = 'dtsc.lotmpr'

    print_roll_ids = fields.Many2many(
        'dtsc.print.roll',
        string='印刷排版捲料',
        compute='_compute_print_roll_ids',
    )
    print_preview_html = fields.Html(
        string='印刷排版預覽',
        compute='_compute_print_preview_html',
        sanitize=False,
    )

    def _compute_print_roll_ids(self):
        Roll = self.env['dtsc.print.roll']
        for rec in self:
            if not rec.product_lot:
                rec.print_roll_ids = Roll
                continue
            rec.print_roll_ids = Roll.search([
                ('stock_lot_id', '=', rec.product_lot.id),
                ('order_id.state', 'not in', ('cancel',)),
            ], order='id desc')

    def _compute_print_preview_html(self):
        for rec in self:
            parts = []
            for roll in rec.print_roll_ids[:8]:
                title = '%s / %s' % (
                    roll.order_id.name or '',
                    roll.name or _('捲料'),
                )
                body = roll.preview_svg or '<div class="text-muted">（無預覽）</div>'
                parts.append(
                    '<div class="mb-3">'
                    '<div class="fw-bold mb-1">%s</div>%s</div>' % (title, body)
                )
            rec.print_preview_html = (
                ''.join(parts) if parts else
                '<div class="text-muted">尚無印刷排版記錄</div>'
            )

    @api.model
    def _print_nesting_find_or_create(self, stock_lot):
        """依實體捲找到／建立捲料扣料總表（與掃碼開單一致，含邊料損耗行）。"""
        stock_lot.ensure_one()
        barcode = (stock_lot.barcode or stock_lot.name or '').strip()
        if not barcode:
            raise UserError(_('捲料「%s」沒有條碼／序號，無法建立扣料表。') % stock_lot.display_name)
        lotmpr = self.search([
            '|',
            ('product_lot', '=', stock_lot.id),
            ('name', '=ilike', barcode),
        ], limit=1)
        if lotmpr:
            if not lotmpr.product_lot:
                lotmpr.product_lot = stock_lot.id
            return lotmpr
        lotmpr = self.create({
            'name': barcode,
            'product_id': stock_lot.product_id.id,
            'product_lot': stock_lot.id,
        })
        # 與掃碼開單一致：預建邊料損耗
        self.env['dtsc.lotmprline'].create({
            'lotmpr_id': lotmpr.id,
            'name': '邊料損耗',
            'sjkl': 25,
        })
        return lotmpr

    def ok_btn(self):
        """支援 context print_nesting_line_ids：只扣指定項次（印刷單自動扣料）。"""
        line_ids = self.env.context.get('print_nesting_line_ids')
        if not line_ids:
            return super().ok_btn()
        for rec in self:
            lines = rec.lotmprline_id.filtered(
                lambda l: l.id in line_ids and l.state != 'succ'
            )
            if not lines:
                continue
            rec.with_context(
                print_nesting_line_ids=False,
                print_nesting_only_lines=lines.ids,
            )._print_nesting_ok_selected(lines)
        return True

    def _print_nesting_ok_selected(self, lines):
        """對指定 draft 行執行與 ok_btn 相同的扣料（才數）。"""
        self.ensure_one()
        # 暫時只保留要扣的 draft 行給原生 ok_btn：把其它 draft 行先標記跳過不現實
        # 改為直接呼叫原生邏輯前，用 context 讓覆寫過濾
        other_draft = self.lotmprline_id.filtered(
            lambda l: l.state != 'succ' and l.id not in lines.ids
        )
        # 若有其它待扣掃碼行，仍只扣印刷單這批，不碰其它
        return self._print_nesting_deduct_lines(lines)

    def _print_nesting_deduct_lines(self, lines):
        """複製 ok_btn 核心：對 lines 做庫存→生產調撥（單位才）。"""
        self.ensure_one()
        uom_obj = self.env['uom.uom']
        uom_record = uom_obj.browse(self.uom_id.id)
        now_category_id = uom_record.category_id.id
        other_uom = uom_obj.search([
            ('category_id', '=', now_category_id),
            ('id', '!=', uom_record.id),
        ], limit=1)
        uomid = other_uom.id if other_uom else self.uom_id.id

        if self.lot_stock_num == '無':
            raise UserError(_('此料無庫存!'))
        try:
            if float(self.lot_stock_num) < 0:
                raise UserError(_('此料無庫存!'))
        except (TypeError, ValueError):
            raise UserError(_('此料無庫存!'))

        factor = other_uom.factor if other_uom else 1.0
        now_stock_p = float(self.lot_stock_num) * factor

        for record in lines:
            if record.state == 'succ':
                continue
            if record.sjkl == 0:
                qty_done_cai = record.yujixiaohao
            else:
                qty_done_cai = record.sjkl
            if not qty_done_cai:
                record.state = 'succ'
                continue
            if (now_stock_p - qty_done_cai) < 0:
                raise UserError(_(
                    '印刷單自動扣料失敗：捲「%s」才數不足（需要 %.2f，剩餘約 %.2f）。'
                ) % (self.name, qty_done_cai, now_stock_p))

            now_stock_p -= qty_done_cai
            picking = self.env['stock.picking'].create({
                'picking_type_id': 1,
                'location_id': self.stock_location_id.id,
                'location_dest_id': 15,
                'origin': record.name,
            })
            record.picking_id = picking.id
            move = self.env['stock.move'].create({
                'name': record.name,
                'reference': '工單扣料' + record.name,
                'product_id': self.product_id.id,
                'product_uom_qty': qty_done_cai,
                'product_uom': uomid,
                'picking_id': picking.id,
                'quantity_done': qty_done_cai,
                'origin': record.name,
                'location_id': self.stock_location_id.id,
                'location_dest_id': 15,
            })
            record.stock_move_id = move.id
            stock_lot_obj = self.env['stock.lot'].search([('barcode', '=', self.name)], limit=1)
            if not stock_lot_obj and self.product_lot:
                stock_lot_obj = self.product_lot
            move_line = self.env['stock.move.line'].create({
                'reference': '工單扣料' + record.name,
                'origin': record.name,
                'move_id': move.id,
                'picking_id': picking.id,
                'product_id': self.product_id.id,
                'qty_done': qty_done_cai,
                'product_uom_id': uomid,
                'location_id': self.stock_location_id.id,
                'location_dest_id': 15,
                'lot_name': stock_lot_obj.name,
                'lot_id': stock_lot_obj.id,
                'state': 'draft',
            })
            record.stock_move_line_id = [(4, move_line.id)]
            self.env['stock.move.line'].search([
                '|',
                ('lot_id', '=', False),
                ('lot_name', '=', False),
                ('product_id', '=', self.product_id.id),
                ('picking_id', '=', picking.id),
            ]).unlink()
            picking.action_confirm()
            picking.action_assign()
            picking.button_validate()
            record.state = 'succ'
            record.sjkl = qty_done_cai
        return True


class LotMprLine(models.Model):
    _inherit = 'dtsc.lotmprline'

    print_order_id = fields.Many2one(
        'dtsc.print.order', string='印刷單', index=True, ondelete='set null',
    )
    print_roll_id = fields.Many2one(
        'dtsc.print.roll', string='印刷捲料', index=True, ondelete='set null',
    )
