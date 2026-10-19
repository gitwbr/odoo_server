# -*- coding: utf-8 -*-
import html
from odoo import api, fields, models, _
from odoo.exceptions import UserError


def _available_lot_domain(env, product_tmpl):
    """Domain for stock.lot with qty > 0 in internal locations for this roll material."""
    if not product_tmpl:
        return [('id', '=', False)]
    products = env['product.product'].search([('product_tmpl_id', '=', product_tmpl.id)])
    if not products:
        return [('id', '=', False)]
    quants = env['stock.quant'].search([
        ('product_id', 'in', products.ids),
        ('quantity', '>', 0),
        ('lot_id', '!=', False),
        ('location_id.usage', '=', 'internal'),
    ])
    lot_ids = quants.mapped('lot_id').ids
    return [('id', 'in', lot_ids)] if lot_ids else [('id', '=', False)]


def _available_lots(env, product_tmpl):
    domain = _available_lot_domain(env, product_tmpl)
    return env['stock.lot'].search(domain)


class PrintRoll(models.Model):
    _name = 'dtsc.print.roll'
    _description = '印刷捲料排版'
    _order = 'order_id desc, sequence, id'

    name = fields.Char(string='捲料編號', default='New', copy=False)
    order_id = fields.Many2one('dtsc.print.order', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='序', default=1)
    roll_width_mm = fields.Float(string='門幅(mm)')
    used_length_mm = fields.Float(string='用料長(mm)')
    utilization_rate = fields.Float(string='利用率%')
    stock_lot_id = fields.Many2one(
        'stock.lot',
        string='倉庫實體捲',
        help='僅可選該捲材在內部倉庫庫存 > 0 的序號捲。',
        domain="[]",
    )
    lot_qty = fields.Float(
        string='庫存',
        compute='_compute_lot_stock',
        help='該實體捲在內部倉的合計數量',
    )
    lot_barcode = fields.Char(related='stock_lot_id.barcode', string='捲條碼', readonly=True)
    state = fields.Selection(
        related='order_id.state', store=True, string='印刷單狀態'
    )
    piece_ids = fields.One2many('dtsc.print.piece', 'roll_id', string='圖塊')
    preview_svg = fields.Html(string='排版預覽', sanitize=False, compute='_compute_preview_svg')
    material_product_id = fields.Many2one(
        related='order_id.material_product_id', store=True, string='捲材'
    )
    piece_count = fields.Integer(string='圖塊數', compute='_compute_piece_count')

    @api.depends('piece_ids')
    def _compute_piece_count(self):
        for rec in self:
            rec.piece_count = len(rec.piece_ids)

    @api.depends('stock_lot_id')
    def _compute_lot_stock(self):
        Quant = self.env['stock.quant']
        for rec in self:
            if not rec.stock_lot_id:
                rec.lot_qty = 0.0
                continue
            quants = Quant.search([
                ('lot_id', '=', rec.stock_lot_id.id),
                ('location_id.usage', '=', 'internal'),
            ])
            rec.lot_qty = sum(quants.mapped('quantity'))

    @api.onchange('material_product_id', 'order_id')
    def _onchange_material_lot_domain(self):
        tmpl = self.material_product_id or self.order_id.material_product_id
        return {'domain': {'stock_lot_id': _available_lot_domain(self.env, tmpl)}}

    @api.onchange('stock_lot_id')
    def _onchange_stock_lot(self):
        if self.stock_lot_id and self.lot_qty <= 0:
            return {
                'warning': {
                    'title': _('庫存不足'),
                    'message': _('所選實體捲目前內部倉庫存為 0，請改選其他可用捲。'),
                }
            }

    def _assign_available_lot(self, exclude_lot_ids=None):
        """Bind first unused warehouse lot with qty > 0 for this material."""
        self.ensure_one()
        exclude = set(exclude_lot_ids or [])
        lots = _available_lots(self.env, self.material_product_id)
        for lot in lots:
            if lot.id in exclude:
                continue
            self.stock_lot_id = lot
            if self.stock_lot_id.name and (not self.name or self.name.startswith(self.order_id.name or 'P')):
                self.name = lot.name
            return lot
        return self.env['stock.lot']

    def write(self, vals):
        res = super().write(vals)
        if 'stock_lot_id' in vals:
            for rec in self.filtered('stock_lot_id'):
                # 必須是對應捲材產品，且內部倉庫存 > 0
                tmpl = rec.material_product_id
                lot = rec.stock_lot_id
                if tmpl and lot.product_id.product_tmpl_id != tmpl:
                    raise UserError(_('所選實體捲不屬於本單捲材「%s」。') % tmpl.display_name)
                if rec.lot_qty <= 0:
                    raise UserError(_('實體捲「%s」內部倉庫存為 0，不可用於排版。') % lot.display_name)
        return res

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.name or rec.name == 'New':
                rec.name = '%s-R%02d' % (rec.order_id.name or 'P', rec.sequence or 1)
        return records

    @api.depends(
        'piece_ids',
        'piece_ids.x_mm',
        'piece_ids.y_mm',
        'piece_ids.width_mm',
        'piece_ids.height_mm',
        'piece_ids.label',
        'piece_ids.lock_state',
        'roll_width_mm',
        'used_length_mm',
    )
    def _compute_preview_svg(self):
        for rec in self:
            rec.preview_svg = rec._build_svg()

    def _refresh_preview_svg(self):
        # force recompute by touching depends
        self.invalidate_recordset(['preview_svg'])

    def _build_svg(self):
        self.ensure_one()
        width = self.roll_width_mm or 1.0
        length = max(self.used_length_mm or 0.0, 1.0)
        # Add padding so last row is visible
        length = max(length, max([1.0] + [p.y_mm + p.height_mm for p in self.piece_ids]))
        # Scale to fit ~720px wide
        display_w = 720.0
        scale = display_w / width
        display_h = max(length * scale, 40.0)
        colors = {
            'open': '#7CB342',
            'reserved': '#FB8C00',
            'printed': '#546E7A',
        }
        parts = [
            '<div class="o_print_nesting_preview">',
            '<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" '
            'viewBox="0 0 %s %s" style="border:1px solid #ccc;background:#fafafa;">'
            % (int(display_w), int(display_h), width, length),
            '<rect x="0" y="0" width="%s" height="%s" fill="#f5f5f5" stroke="#999"/>'
            % (width, length),
        ]
        for p in self.piece_ids:
            fill = colors.get(p.lock_state, '#7CB342')
            label = html.escape(p.label or '')
            font_size = max(min(p.width_mm, p.height_mm) * 0.18, 8)
            parts.append(
                '<rect x="%s" y="%s" width="%s" height="%s" fill="%s" fill-opacity="0.75" '
                'stroke="#333" stroke-width="%s"/>'
                % (p.x_mm, p.y_mm, p.width_mm, p.height_mm, fill, max(width * 0.002, 0.5))
            )
            parts.append(
                '<text x="%s" y="%s" font-size="%s" text-anchor="middle" '
                'dominant-baseline="middle" fill="#111">%s</text>'
                % (
                    p.x_mm + p.width_mm / 2.0,
                    p.y_mm + p.height_mm / 2.0,
                    font_size,
                    label,
                )
            )
        parts.append('</svg>')
        legend = (
            '<div style="margin-top:4px;font-size:12px;">'
            '<span style="color:#7CB342;">■</span> 可動 '
            '<span style="color:#FB8C00;">■</span> 已鎖定 '
            '<span style="color:#546E7A;">■</span> 已印刷 '
            '| 門幅 %s mm / 用料 %s mm / 利用率 %s%%'
        ) % (width, round(self.used_length_mm or 0, 1), self.utilization_rate or 0)
        parts.append(legend)
        parts.append('</div></div>')
        return ''.join(parts)

    def action_reserve_all(self):
        for rec in self:
            rec.piece_ids.filtered(lambda p: p.lock_state == 'open').write(
                {'lock_state': 'reserved'}
            )
        return True

    def action_mark_printed(self):
        for rec in self:
            rec.piece_ids.filtered(lambda p: p.lock_state != 'printed').write(
                {'lock_state': 'printed'}
            )
            rec.order_id.line_ids._sync_placed_qty()
        return True

    def action_unlock_all_reserved(self):
        for rec in self:
            rec.piece_ids.filtered(lambda p: p.lock_state == 'reserved').write(
                {'lock_state': 'open'}
            )
        return True


class PrintPiece(models.Model):
    _name = 'dtsc.print.piece'
    _description = '印刷圖塊'
    _order = 'roll_id, y_mm, x_mm, id'

    order_id = fields.Many2one('dtsc.print.order', required=True, ondelete='cascade', index=True)
    roll_id = fields.Many2one('dtsc.print.roll', required=True, ondelete='cascade', index=True)
    order_line_id = fields.Many2one('dtsc.print.order.line', ondelete='cascade', index=True)
    makeinline_id = fields.Many2one('dtsc.makeinline', string='工單項次', index=True)
    label = fields.Char(string='標籤')
    x_mm = fields.Float(string='X(mm)')
    y_mm = fields.Float(string='Y(mm)')
    width_mm = fields.Float(string='寬(mm)')
    height_mm = fields.Float(string='高(mm)')
    rotated = fields.Boolean(string='已旋轉')
    lock_state = fields.Selection(
        [
            ('open', '可重排'),
            ('reserved', '已鎖定'),
            ('printed', '已印刷'),
        ],
        default='open',
        string='鎖定',
        required=True,
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('order_id') and vals.get('roll_id'):
                roll = self.env['dtsc.print.roll'].browse(vals['roll_id'])
                vals['order_id'] = roll.order_id.id
            if not vals.get('label') and vals.get('makeinline_id'):
                ml = self.env['dtsc.makeinline'].browse(vals['makeinline_id'])
                if ml.make_order_id:
                    vals['label'] = '%s-%s' % (ml.make_order_id.name or '', ml.sequence or '')
            if not vals.get('order_line_id') and vals.get('makeinline_id') and vals.get('order_id'):
                line = self.env['dtsc.print.order.line'].search([
                    ('order_id', '=', vals['order_id']),
                    ('makeinline_id', '=', vals['makeinline_id']),
                ], limit=1)
                if line:
                    vals['order_line_id'] = line.id
        return super().create(vals_list)

    def write(self, vals):
        for rec in self:
            if rec.lock_state == 'printed':
                # only allow no-op / same printed
                forbidden = set(vals.keys()) - {'lock_state'} if vals.get('lock_state') == 'printed' else set(vals.keys())
                if vals.get('lock_state') and vals['lock_state'] != 'printed':
                    raise UserError(_('已印刷圖塊不可解除或更改狀態。'))
                coord_keys = {'x_mm', 'y_mm', 'width_mm', 'height_mm', 'rotated', 'roll_id'}
                if coord_keys & set(vals.keys()):
                    raise UserError(_('已印刷圖塊不可更改位置。'))
            if rec.lock_state == 'reserved':
                coord_keys = {'x_mm', 'y_mm', 'width_mm', 'height_mm', 'rotated', 'roll_id'}
                if coord_keys & set(vals.keys()):
                    raise UserError(_('已鎖定圖塊請先解鎖再移動。'))
                if vals.get('lock_state') == 'printed':
                    pass  # allowed
                elif 'lock_state' in vals and vals['lock_state'] not in ('open', 'reserved', 'printed'):
                    raise UserError(_('無效的鎖定狀態。'))
        res = super().write(vals)
        if any(k in vals for k in ('x_mm', 'y_mm', 'width_mm', 'height_mm', 'lock_state', 'roll_id')):
            self.mapped('roll_id')._refresh_preview_svg()
            self.mapped('order_line_id')._sync_placed_qty()
        return res

    def unlink(self):
        if self.filtered(lambda p: p.lock_state == 'printed'):
            raise UserError(_('已印刷圖塊不可刪除。'))
        if self.filtered(lambda p: p.lock_state == 'reserved'):
            raise UserError(_('已鎖定圖塊請先解鎖再刪除／重排。'))
        rolls = self.mapped('roll_id')
        lines = self.mapped('order_line_id')
        res = super().unlink()
        rolls._refresh_preview_svg()
        lines._sync_placed_qty()
        return res

    def action_reserve(self):
        for rec in self:
            if rec.lock_state == 'printed':
                raise UserError(_('已印刷圖塊不可改為鎖定。'))
            rec.lock_state = 'reserved'
        return True

    def action_unlock(self):
        for rec in self:
            if rec.lock_state == 'printed':
                raise UserError(_('已印刷圖塊不可解鎖。'))
            rec.lock_state = 'open'
        return True

    def action_mark_printed(self):
        self.write({'lock_state': 'printed'})
        return True

