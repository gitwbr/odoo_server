# -*- coding: utf-8 -*-
import html
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .nesting_engine import NestingEngine, PieceDemand, Obstacle, RollResult, Placement


class PrintOrder(models.Model):
    _name = 'dtsc.print.order'
    _description = '印刷單'
    _order = 'id desc'

    name = fields.Char(string='單號', default='New', copy=False, readonly=True)
    state = fields.Selection(
        [
            ('draft', '草稿'),
            ('nested', '已排版'),
            ('confirmed', '已確認'),
            ('done', '完成'),
            ('cancel', '作廢'),
        ],
        default='draft',
        string='狀態',
    )
    material_product_id = fields.Many2one(
        'product.template',
        string='捲材',
        required=True,
        domain="[('tracking', '=', 'serial')]",
    )
    machine_id = fields.Many2one('dtsc.machineprice', string='機台')
    roll_width_mm = fields.Float(string='門幅(mm)')
    gap_mm = fields.Float(string='圖間距(mm)', default=2.0)
    margin_mm = fields.Float(string='邊距(mm)', default=0.0)
    allow_rotate = fields.Boolean(string='允許90°旋轉', default=True)
    need_renest = fields.Boolean(string='需重排', default=False)
    company_id = fields.Many2one(
        'res.company', string='公司', default=lambda self: self.env.company
    )
    note = fields.Text(string='備註')

    line_ids = fields.One2many('dtsc.print.order.line', 'order_id', string='需求項次')
    roll_ids = fields.One2many('dtsc.print.roll', 'order_id', string='捲料排版')
    piece_ids = fields.One2many('dtsc.print.piece', 'order_id', string='全部圖塊')

    total_demand_qty = fields.Integer(string='需求總數', compute='_compute_totals')
    total_placed_qty = fields.Integer(string='已排總數', compute='_compute_totals')
    total_used_length_mm = fields.Float(string='總用料長(mm)', compute='_compute_totals')
    utilization_rate = fields.Float(string='平均利用率%', compute='_compute_totals')
    unplaced_info = fields.Text(string='未排提示', readonly=True)
    earliest_delivery = fields.Datetime(string='最早交期', compute='_compute_totals')

    @api.depends(
        'line_ids.qty',
        'line_ids.placed_qty',
        'line_ids.delivery_date',
        'roll_ids.used_length_mm',
        'roll_ids.utilization_rate',
    )
    def _compute_totals(self):
        for rec in self:
            rec.total_demand_qty = sum(rec.line_ids.mapped('qty'))
            rec.total_placed_qty = sum(rec.line_ids.mapped('placed_qty'))
            rec.total_used_length_mm = sum(rec.roll_ids.mapped('used_length_mm'))
            rates = rec.roll_ids.mapped('utilization_rate')
            rec.utilization_rate = round(sum(rates) / len(rates), 2) if rates else 0.0
            dates = [d for d in rec.line_ids.mapped('delivery_date') if d]
            rec.earliest_delivery = min(dates) if dates else False

    @api.onchange('material_product_id')
    def _onchange_material(self):
        if self.material_product_id:
            self.roll_width_mm = (self.material_product_id.roll_width_cm or 0.0) * 10.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dtsc.print.order') or 'P'
            mat_id = vals.get('material_product_id')
            if mat_id and not vals.get('roll_width_mm'):
                mat = self.env['product.template'].browse(mat_id)
                vals['roll_width_mm'] = (mat.roll_width_cm or 0.0) * 10.0
        return super().create(vals_list)

    def action_set_draft(self):
        for rec in self:
            if rec.piece_ids.filtered(lambda p: p.lock_state == 'printed'):
                raise UserError(_('已有圖塊標記為已印刷，無法回到草稿。請作廢後另開新單。'))
            rec.state = 'draft'

    def action_cancel(self):
        for rec in self:
            if rec.piece_ids.filtered(lambda p: p.lock_state == 'printed'):
                raise UserError(_('已有已印刷圖塊，不可作廢。'))
            rec.roll_ids.unlink()
            rec.state = 'cancel'
            rec.need_renest = False
            rec.line_ids._sync_placed_qty()
        return True

    def action_confirm(self):
        for rec in self:
            if not rec.roll_ids:
                raise UserError(_('請先執行自動排版。'))
            rec.state = 'confirmed'
            rec.need_renest = False
        return True

    def action_done(self):
        """整單標記完成：未 printed 的圖塊一併標已印刷。"""
        for rec in self:
            open_or_res = rec.piece_ids.filtered(lambda p: p.lock_state != 'printed')
            open_or_res.write({'lock_state': 'printed'})
            rec.state = 'done'
            rec.need_renest = False
            rec.line_ids._sync_placed_qty()
        return True

    def action_auto_nest(self):
        for rec in self:
            rec._auto_nest()
        return True

    def action_renest(self):
        return self.action_auto_nest()

    def _auto_nest(self):
        self.ensure_one()
        if self.state in ('done', 'cancel'):
            raise UserError(_('完成或作廢的印刷單不可重排。'))
        if self.piece_ids.filtered(lambda p: p.lock_state == 'printed') and self.state == 'done':
            raise UserError(_('已完成印刷單不可重排。'))
        width = self.roll_width_mm or (
            (self.material_product_id.roll_width_cm or 0.0) * 10.0 if self.material_product_id else 0
        )
        if not width:
            raise UserError(_('請先在產品主檔設定「捲材寬度(cm)」。'))
        self.roll_width_mm = width

        # Build demands: outstanding open qty per line
        demands = []
        for line in self.line_ids:
            locked_qty = len(line.piece_ids.filtered(
                lambda p: p.lock_state in ('reserved', 'printed')
            ))
            need = max((line.qty or 0) - locked_qty, 0)
            w_mm, h_mm = line._size_mm()
            if need <= 0:
                continue
            if not w_mm or not h_mm:
                raise UserError(_('項次 %s 寬高無效，無法排版。') % (line.display_label or line.id))
            for i in range(need):
                demands.append(
                    PieceDemand(
                        key='%s:%s' % (line.id, i),
                        width=w_mm,
                        height=h_mm,
                        meta={
                            'line_id': line.id,
                            'makeinline_id': line.makeinline_id.id,
                            'label': line.display_label,
                        },
                    )
                )

        # Seed rolls from locked pieces; remove only open pieces
        Piece = self.env['dtsc.print.piece']
        self.piece_ids.filtered(lambda p: p.lock_state == 'open').unlink()

        seed_rolls_engine = []
        roll_records_ordered = self.roll_ids.sorted('sequence')
        for roll in roll_records_ordered:
            obstacles = []
            for p in roll.piece_ids.filtered(lambda x: x.lock_state in ('reserved', 'printed')):
                obstacles.append(Obstacle(x=p.x_mm, y=p.y_mm, width=p.width_mm, height=p.height_mm))
            used = roll.used_length_mm or 0.0
            if obstacles:
                used = max(used, max(o.y + o.height for o in obstacles) + self.margin_mm)
            seed_rolls_engine.append(
                RollResult(width=width, used_length=used, placements=[], obstacles=obstacles)
            )

        engine = NestingEngine(
            roll_width=width,
            gap=self.gap_mm,
            margin=self.margin_mm,
            allow_rotate=self.allow_rotate,
        )
        roll_results, unplaced = engine.pack(demands, seed_rolls=seed_rolls_engine or None)

        # Map engine rolls back: first N match existing seed rolls; extras are new
        existing = list(roll_records_ordered)
        for idx, result in enumerate(roll_results):
            if idx < len(existing):
                roll_rec = existing[idx]
            else:
                roll_rec = self.env['dtsc.print.roll'].create({
                    'order_id': self.id,
                    'sequence': idx + 1,
                    'roll_width_mm': width,
                })
            # Create new open placements from result.placements
            for pl in result.placements:
                meta = pl.meta or {}
                Piece.create({
                    'order_id': self.id,
                    'roll_id': roll_rec.id,
                    'order_line_id': meta.get('line_id'),
                    'makeinline_id': meta.get('makeinline_id'),
                    'label': meta.get('label') or '',
                    'x_mm': pl.x,
                    'y_mm': pl.y,
                    'width_mm': pl.width,
                    'height_mm': pl.height,
                    'rotated': pl.rotated,
                    'lock_state': 'open',
                })
            # Refresh used length / util including locked
            all_placements = []
            for p in roll_rec.piece_ids:
                all_placements.append(
                    Placement(
                        key=str(p.id),
                        x=p.x_mm,
                        y=p.y_mm,
                        width=p.width_mm,
                        height=p.height_mm,
                        rotated=p.rotated,
                    )
                )
            used_len = max(
                [self.margin_mm]
                + [p.y_mm + p.height_mm for p in roll_rec.piece_ids]
            ) + self.margin_mm if roll_rec.piece_ids else 0.0
            roll_rec.write({
                'used_length_mm': used_len,
                'utilization_rate': NestingEngine.utilization(width, used_len, all_placements),
                'roll_width_mm': width,
            })
            roll_rec._refresh_preview_svg()

        # Remove empty rolls that have no pieces left
        empty_rolls = self.roll_ids.filtered(lambda r: not r.piece_ids)
        empty_rolls.unlink()

        # Re-sequence + 自動綁定倉庫可用實體捲（庫存>0，同一 Lot 不重複）
        used_lot_ids = set(
            self.roll_ids.filtered('stock_lot_id').mapped('stock_lot_id').ids
        )
        for i, roll in enumerate(self.roll_ids.sorted('sequence'), start=1):
            roll.sequence = i
            if not roll.stock_lot_id:
                lot = roll._assign_available_lot(exclude_lot_ids=used_lot_ids)
                if lot:
                    used_lot_ids.add(lot.id)
            if not roll.name or roll.name == 'New':
                roll.name = (roll.stock_lot_id.name if roll.stock_lot_id else None) or (
                    '%s-R%02d' % (self.name, i)
                )

        self.unplaced_info = ''
        if unplaced:
            self.unplaced_info = _('有 %s 塊因超出門幅或其他原因未能排入。') % len(unplaced)
        unbound = self.roll_ids.filtered(lambda r: not r.stock_lot_id)
        if unbound:
            tip = _('有 %s 條排版捲尚未綁定倉庫實體捲（該捲材內部倉可用庫存不足或為 0）。') % len(unbound)
            self.unplaced_info = ((self.unplaced_info or '') + '\n' + tip).strip()
        self.need_renest = False
        if self.state == 'draft':
            self.state = 'nested'
        self.line_ids._sync_placed_qty()
        return True

    def action_mark_dirty(self):
        self.write({'need_renest': True})

    def action_reserve_selected_wizard(self):
        """UI helper: reserve all open pieces on this order (bulk)."""
        self.ensure_one()
        opens = self.piece_ids.filtered(lambda p: p.lock_state == 'open')
        opens.write({'lock_state': 'reserved'})
        return True

    def action_unlock_reserved(self):
        self.ensure_one()
        reserved = self.piece_ids.filtered(lambda p: p.lock_state == 'reserved')
        reserved.write({'lock_state': 'open'})
        return True


class PrintOrderLine(models.Model):
    _name = 'dtsc.print.order.line'
    _description = '印刷單需求行'

    order_id = fields.Many2one('dtsc.print.order', required=True, ondelete='cascade')
    makeinline_id = fields.Many2one('dtsc.makeinline', string='工單項次', required=True, ondelete='restrict')
    makein_id = fields.Many2one(related='makeinline_id.make_order_id', store=True, string='內部工單')
    makein_name = fields.Char(related='makein_id.name', store=True, string='工單號')
    sequence_label = fields.Char(string='項次', compute='_compute_label', store=True)
    display_label = fields.Char(string='標籤', compute='_compute_label', store=True)
    piece_w_mm = fields.Float(string='寬(mm)')
    piece_h_mm = fields.Float(string='高(mm)')
    qty = fields.Integer(string='需求數量', required=True)
    placed_qty = fields.Integer(string='已排數量', compute='_compute_placed', store=True)
    printed_qty = fields.Integer(string='已印數量', compute='_compute_placed', store=True)
    delivery_date = fields.Datetime(string='交期')
    piece_ids = fields.One2many('dtsc.print.piece', 'order_line_id', string='圖塊')

    _sql_constraints = [
        (
            'uniq_order_makeinline',
            'unique(order_id, makeinline_id)',
            '同一印刷單不可重複加入同一工單項次。',
        ),
    ]

    @api.depends('makeinline_id', 'makeinline_id.sequence', 'makein_name')
    def _compute_label(self):
        for rec in self:
            seq = rec.makeinline_id.sequence or ''
            rec.sequence_label = str(seq)
            name = rec.makein_name or ''
            rec.display_label = ('%s-%s' % (name, seq)) if name else str(seq)

    @api.depends('piece_ids', 'piece_ids.lock_state')
    def _compute_placed(self):
        for rec in self:
            pieces = rec.piece_ids
            rec.placed_qty = len(pieces)
            rec.printed_qty = len(pieces.filtered(lambda p: p.lock_state == 'printed'))

    def _sync_placed_qty(self):
        self._compute_placed()
        # touch makeinline compute
        self.mapped('makeinline_id')._compute_print_state()

    def _size_mm(self):
        self.ensure_one()
        if self.piece_w_mm and self.piece_h_mm:
            return self.piece_w_mm, self.piece_h_mm
        if self.makeinline_id:
            return self.makeinline_id._parse_size_cm()
        return 0.0, 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ml = self.env['dtsc.makeinline'].browse(vals.get('makeinline_id'))
            if ml and not vals.get('piece_w_mm'):
                w, h = ml._parse_size_cm()
                vals['piece_w_mm'] = w
                vals['piece_h_mm'] = h
            if ml and not vals.get('qty'):
                vals['qty'] = ml.quantity or 1
            if ml and not vals.get('delivery_date') and ml.make_order_id:
                vals['delivery_date'] = ml.make_order_id.delivery_date
        lines = super().create(vals_list)
        lines.mapped('order_id').write({'need_renest': True})
        return lines

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ('qty', 'piece_w_mm', 'piece_h_mm', 'makeinline_id')):
            self.mapped('order_id').filtered(lambda o: o.state not in ('done', 'cancel')).write(
                {'need_renest': True}
            )
        return res
