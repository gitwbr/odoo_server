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
    # 鎖定時寫入當下系統設定，僅備查；實際排版讀印刷池高級設定
    gap_mm = fields.Float(string='圖間距(mm)', default=5.0)
    margin_mm = fields.Float(string='邊距(mm)', default=0.0)
    # 僅留存欄位；實際排版讀系統設定，表單不顯示
    allow_rotate = fields.Boolean(string='允許90°旋轉', default=True, copy=False)
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
    effect_preview_html = fields.Html(
        string='印刷效果圖', compute='_compute_effect_preview', sanitize=False,
    )
    effect_thumb_html = fields.Html(
        string='效果圖', compute='_compute_effect_preview', sanitize=False,
    )

    @api.depends(
        'roll_ids.roll_width_mm',
        'roll_ids.used_length_mm',
        'roll_ids.piece_ids.x_mm',
        'roll_ids.piece_ids.y_mm',
        'roll_ids.piece_ids.width_mm',
        'roll_ids.piece_ids.height_mm',
        'roll_ids.piece_ids.rotation',
        'roll_ids.piece_ids.flip_h',
        'roll_ids.piece_ids.lock_state',
    )
    def _compute_effect_preview(self):
        for rec in self:
            rolls = rec.roll_ids.filtered('piece_ids')
            if not rolls:
                rec.effect_preview_html = '<div class="text-muted">尚無排版</div>'
                rec.effect_thumb_html = ''
                continue
            big, small = [], []
            for roll in rolls:
                caption = html.escape('%s　%s' % (
                    roll.name or '',
                    roll.stock_lot_id.name or '',
                ))
                big.append(
                    '<div style="margin-bottom:10px;">'
                    '<div style="font-size:12px;color:#666;margin-bottom:2px;">%s'
                    '　用料 %.0f mm／門幅 %.0f mm</div>'
                    '<div style="overflow-x:auto;max-width:100%%;">%s</div></div>'
                    % (
                        caption,
                        roll.used_length_mm or 0.0,
                        roll.roll_width_mm or 0.0,
                        roll._build_effect_html(max_w=1100.0, max_h=320.0, min_h=160.0),
                    )
                )
                small.append(
                    '<div style="margin:1px 0;">%s</div>'
                    % roll._build_effect_html(
                        max_w=220.0, max_h=60.0, img_size=128, show_label=False,
                    )
                )
            rec.effect_preview_html = ''.join(big)
            rec.effect_thumb_html = ''.join(small)

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
            if rec.state == 'confirmed':
                raise UserError(_('已確認的印刷單不可回草稿（排版已鎖定）。若要重排請作廢後回印刷池再生成。'))
            if rec.piece_ids.filtered(lambda p: p.lock_state == 'printed'):
                raise UserError(_('已有圖塊標記為已印刷，無法回到草稿。請作廢後另開新單。'))
            rec.state = 'draft'

    def _ensure_layout_editable(self):
        """已確認／完成／作廢不可再改排版順序。"""
        locked = self.filtered(lambda r: r.state in ('confirmed', 'done', 'cancel'))
        if locked:
            raise UserError(
                _('印刷單 %s 已鎖定排版，不可再自動排版／解鎖／改座標。若要重排請作廢後回印刷池。')
                % ', '.join(locked.mapped('name'))
            )

    def action_cancel(self):
        """作廢未印刷單：返還扣料、刪除排版圖塊，項次回到印刷池待排。"""
        for rec in self:
            if rec.piece_ids.filtered(lambda p: p.lock_state == 'printed'):
                raise UserError(_('已有已印刷圖塊，不可作廢。'))
            rec._print_nesting_reverse_deduct()
            mls = rec.piece_ids.mapped('makeinline_id')
            # 池鎖定產生的 reserved 也要釋放，否則無法刪除圖塊
            rec.piece_ids.with_context(force_print_piece_unlink=True).unlink()
            rec.roll_ids.unlink()
            rec.state = 'cancel'
            rec.need_renest = False
            rec.line_ids._sync_placed_qty()
            if mls:
                mls._compute_print_state()
        return True

    def unlink(self):
        """刪除印刷單：返還扣料；未印刷則釋放圖塊回印刷池；已印刷不可刪。"""
        for rec in self:
            if rec.piece_ids.filtered(lambda p: p.lock_state == 'printed'):
                raise UserError(_('「%s」已有已印刷圖塊，不可刪除。請保留作廢單備查。') % rec.name)
            rec._print_nesting_reverse_deduct()
        mls_all = self.mapped('piece_ids.makeinline_id') | self.mapped('line_ids.makeinline_id')
        self.mapped('piece_ids').with_context(force_print_piece_unlink=True).unlink()
        res = super().unlink()
        if mls_all:
            mls_all.exists()._compute_print_state()
        return res

    def _print_nesting_auto_deduct(self):
        """生成印刷單後：寫入 dtsc.lotmpr / lotmprline 並扣才數。"""
        LotMpr = self.env['dtsc.lotmpr']
        LotMprLine = self.env['dtsc.lotmprline']
        for order in self:
            for roll in order.roll_ids.filtered('stock_lot_id'):
                lotmpr = LotMpr._print_nesting_find_or_create(roll.stock_lot_id)
                if lotmpr.state == 'succ':
                    raise UserError(_(
                        '捲料「%s」扣料表已材料耗盡，無法再生成印刷單扣料。'
                    ) % (roll.stock_lot_id.display_name,))
                barcodes = []
                for piece in roll.piece_ids:
                    ml = piece.makeinline_id
                    if ml and ml.barcode and ml.barcode not in barcodes:
                        barcodes.append(ml.barcode)
                new_lines = LotMprLine
                for barcode in barcodes:
                    existing = LotMprLine.search([
                        ('lotmpr_id', '=', lotmpr.id),
                        ('name', '=', barcode),
                    ], limit=1)
                    if existing:
                        if existing.state == 'succ':
                            # 已扣過（可能掃碼先扣）：不再重扣；扣料表 state=succ 時不可改行
                            continue
                        existing.write({
                            'print_order_id': order.id,
                            'print_roll_id': roll.id,
                        })
                        new_lines |= existing
                    else:
                        new_lines |= LotMprLine.create({
                            'lotmpr_id': lotmpr.id,
                            'name': barcode,
                            'print_order_id': order.id,
                            'print_roll_id': roll.id,
                        })
                if new_lines:
                    lotmpr._print_nesting_deduct_lines(new_lines)
        return True

    def _print_nesting_reverse_deduct(self):
        """刪除／作廢印刷單：返還本單產生的扣料行。"""
        LotMprLine = self.env['dtsc.lotmprline']
        for order in self:
            lines = LotMprLine.search([('print_order_id', '=', order.id)])
            for line in lines:
                if line.name == '邊料損耗':
                    continue
                try:
                    if line.state == 'succ':
                        line.delete_btn()
                    elif line.exists():
                        line.unlink()
                except Exception as err:  # noqa: BLE001
                    raise UserError(_(
                        '印刷單「%s」返還扣料失敗（項次 %s）：%s'
                    ) % (order.name, line.name, err)) from err
        return True

    def action_compose_layout_tiffs(self):
        """重新合成本單所有捲的排版 TIFF（前端顯示進度條）。"""
        for rec in self:
            if not rec.roll_ids:
                raise UserError(_('尚無捲料排版，無法合成 TIFF。'))
        return {
            'type': 'ir.actions.client',
            'tag': 'dtsc_print_nesting.compose_tiffs',
            'params': {
                'order_ids': self.ids,
                'title': '、'.join(self.mapped('name')),
            },
        }

    def compose_layout_tiffs_with_progress(self, job_key=None):
        Job = self.env['dtsc.print.compose.job']
        rolls = self.mapped('roll_ids')
        if not rolls:
            raise UserError(_('尚無捲料排版，無法合成 TIFF。'))
        try:
            rolls.with_context(print_compose_job=job_key).action_compose_layout_tiff()
        except Exception as err:
            Job._report(job_key, state='error', message=str(err))
            raise
        results = [{
            'name': '%s %s' % (roll.order_id.name or '', roll.name or ''),
            'ok': bool(roll.layout_tiff_filename),
            'note': roll.layout_tiff_note or '',
        } for roll in rolls]
        ok = all(r['ok'] for r in results)
        Job._report(
            job_key, percent=100.0, state='done' if ok else 'error',
            message=_('合成完成') if ok else _('部分捲料未生成 TIFF'),
        )
        return {'ok': ok, 'rolls': results}

    def action_download_layout_tiffs(self):
        """下載本單排版 TIFF（每捲一個檔）。"""
        self.ensure_one()
        rolls = self.roll_ids.filtered(lambda r: r._has_layout_tiff_file())
        if not rolls:
            # 嘗試自動合成一次再下
            if self.roll_ids:
                self.roll_ids.action_compose_layout_tiff()
                rolls = self.roll_ids.filtered(lambda r: r._has_layout_tiff_file())
            if not rolls:
                raise UserError(_('尚無可用的排版 TIFF，請確認已鎖定排版後再試。'))
        # 排版 TIFF 動輒數百 MB，不在伺服器打 zip；每捲各自串流下載
        return rolls._layout_tiff_download_action()

    def action_confirm(self):
        for rec in self:
            if not rec.roll_ids:
                raise UserError(_('請先執行自動排版。'))
            rec.state = 'confirmed'
            rec.need_renest = False
            # 若尚未由印刷池自動扣過，確認時補扣
            rec._print_nesting_auto_deduct()
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
        self._ensure_layout_editable()
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
            film_group = (
                line.makeinline_id._print_film_gap_group()
                if line.makeinline_id else ''
            )
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
                            'gap_group': film_group,
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
                g = (
                    p.makeinline_id._print_film_gap_group()
                    if p.makeinline_id else ''
                )
                obstacles.append(Obstacle(
                    x=p.x_mm, y=p.y_mm,
                    width=p.width_mm, height=p.height_mm,
                    gap_group=g,
                ))
            used = roll.used_length_mm or 0.0
            if obstacles:
                used = max(used, max(o.y + o.height for o in obstacles) + self.margin_mm)
            seed_rolls_engine.append(
                RollResult(width=width, used_length=used, placements=[], obstacles=obstacles)
            )

        # 間距／邊距優先用本單捲材自訂，否則系統設定
        pool = self.env['dtsc.print.pool']
        mat = self.material_product_id
        gap = pool._nest_gap_mm_for_material(mat)
        gap_diff = pool._nest_gap_diff_film_mm_for_material(mat)
        margin = pool._nest_margin_mm_for_material(mat)
        allow_rotate = pool._print_pool_allow_rotate()
        self.gap_mm = gap
        self.margin_mm = margin
        engine = NestingEngine(
            roll_width=width,
            gap=gap,
            margin=margin,
            allow_rotate=allow_rotate,
            gap_diff_group=gap_diff,
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
        self._ensure_layout_editable()
        opens = self.piece_ids.filtered(lambda p: p.lock_state == 'open')
        opens.write({'lock_state': 'reserved'})
        return True

    def action_unlock_reserved(self):
        self.ensure_one()
        self._ensure_layout_editable()
        reserved = self.piece_ids.filtered(lambda p: p.lock_state == 'reserved')
        reserved.write({'lock_state': 'open'})
        return True


class PrintOrderLine(models.Model):
    _name = 'dtsc.print.order.line'
    _description = '印刷單需求行'
    _order = 'sequence, id'

    order_id = fields.Many2one('dtsc.print.order', required=True, ondelete='cascade')
    sequence = fields.Integer(string='印刷項次', default=10, index=True)
    makeinline_id = fields.Many2one('dtsc.makeinline', string='工單項次', required=True, ondelete='restrict')
    makein_id = fields.Many2one(related='makeinline_id.make_order_id', store=True, string='內部工單')
    makein_name = fields.Char(related='makein_id.name', store=True, string='工單號')
    sequence_label = fields.Char(string='工單項次號', compute='_compute_label', store=True)
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
        # 同一印刷單內自動編印刷項次：10, 20, 30...
        next_seq_by_order = {}
        for vals in vals_list:
            order_id = vals.get('order_id')
            if order_id and not vals.get('sequence'):
                if order_id not in next_seq_by_order:
                    last = self.search([('order_id', '=', order_id)], order='sequence desc', limit=1)
                    next_seq_by_order[order_id] = (last.sequence if last else 0) + 10
                vals['sequence'] = next_seq_by_order[order_id]
                next_seq_by_order[order_id] += 10
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
        lines.mapped('order_id').filtered(lambda o: o.state not in ('done', 'cancel')).write(
            {'need_renest': True}
        )
        return lines

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in ('qty', 'piece_w_mm', 'piece_h_mm', 'makeinline_id')):
            self.mapped('order_id').filtered(lambda o: o.state not in ('done', 'cancel')).write(
                {'need_renest': True}
            )
        return res
