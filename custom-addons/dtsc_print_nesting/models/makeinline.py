# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class MakeInLine(models.Model):
    _inherit = 'dtsc.makeinline'

    need_print_nesting = fields.Boolean(
        string='需印刷排版',
        compute='_compute_need_print_nesting',
        store=True,
        readonly=False,
    )
    print_material_candidate_ids = fields.Many2many(
        'product.template',
        'dtsc_makeinline_print_mat_cand_rel',
        'line_id',
        'material_id',
        string='可選捲材',
        compute='_compute_print_material_candidates',
        store=True,
        help='商品基礎扣料物中所有序號追蹤捲料（多門幅候選）。',
    )
    # 由印刷池優化器寫入；不再「永遠取第一筆」
    print_material_id = fields.Many2one(
        'product.template',
        string='排版捲材',
        store=True,
        index=True,
        help='當前分配的捲材門幅。印刷池刷新時會依出血尺寸在可選捲材中重算。',
    )
    print_state = fields.Selection(
        [
            ('none', '未排'),
            ('partial', '部分已排'),
            ('full', '已排滿'),
            ('printed', '已印刷'),
        ],
        string='印刷排版狀態',
        compute='_compute_print_state',
        store=True,
        default='none',
    )
    print_piece_ids = fields.One2many(
        'dtsc.print.piece',
        'makeinline_id',
        string='印刷圖塊',
    )
    print_placed_qty = fields.Integer(
        string='已排數量',
        compute='_compute_print_state',
        store=True,
    )
    print_printed_qty = fields.Integer(
        string='已印數量',
        compute='_compute_print_state',
        store=True,
    )
    print_preview = fields.Binary(
        string='預覽',
        related='checkout_line_id.layout_tiff_preview',
    )
    print_colorspace = fields.Char(
        string='色彩',
        related='checkout_line_id.layout_tiff_colorspace',
    )
    print_size_text = fields.Char(
        string='印刷尺寸(cm)',
        compute='_compute_print_size_text',
        help='排版實際使用的尺寸：上傳 TIFF 後依像素/DPI 抓到的出血後寬高；沒有才用訂單寬高。',
    )
    print_order_names = fields.Char(
        string='印刷單',
        compute='_compute_print_order_names',
    )

    def _compute_print_size_text(self):
        for rec in self:
            w_mm, h_mm = rec._parse_size_cm()
            if w_mm and h_mm:
                rec.print_size_text = '%s × %s' % (
                    ('%.2f' % (w_mm / 10.0)).rstrip('0').rstrip('.'),
                    ('%.2f' % (h_mm / 10.0)).rstrip('0').rstrip('.'),
                )
            else:
                rec.print_size_text = ''

    def _compute_print_order_names(self):
        for rec in self:
            orders = rec.print_piece_ids.mapped('order_id').filtered(
                lambda o: o.state != 'cancel'
            )
            rec.print_order_names = ', '.join(orders.sorted('id').mapped('name'))

    def _resolve_roll_materials(self):
        """所有序號追蹤基礎扣料物（多門幅）。"""
        self.ensure_one()
        materials = self.env['product.template']
        if self.product_id:
            materials |= self.product_id.get_make_ori_products().filtered(
                lambda p: p.tracking == 'serial'
            )
        for att in self.product_atts:
            if att.make_ori_product_id and att.make_ori_product_id.tracking == 'serial':
                materials |= att.make_ori_product_id
        return materials

    def _resolve_roll_material(self):
        """相容舊呼叫：取候選中第一筆。"""
        return self._resolve_roll_materials()[:1]

    @api.depends(
        'product_id',
        'product_id.make_ori_product_id',
        'product_id.make_ori_product_id.tracking',
        'product_id.make_ori_product_ids',
        'product_id.make_ori_product_ids.tracking',
        'product_atts',
        'product_atts.make_ori_product_id',
        'product_atts.make_ori_product_id.tracking',
    )
    def _compute_print_material_candidates(self):
        for rec in self:
            rec.print_material_candidate_ids = rec._resolve_roll_materials()

    @api.depends('print_material_candidate_ids', 'print_material_id')
    def _compute_need_print_nesting(self):
        for rec in self:
            rec.need_print_nesting = bool(
                rec.print_material_candidate_ids
                or (rec.print_material_id and rec.print_material_id.tracking == 'serial')
            )

    @api.depends(
        'quantity',
        'print_piece_ids',
        'print_piece_ids.lock_state',
        'print_piece_ids.order_id',
        'print_piece_ids.order_id.state',
    )
    def _compute_print_state(self):
        for rec in self:
            pieces = rec.print_piece_ids.filtered(
                lambda p: p.order_id and p.order_id.state != 'cancel'
            )
            placed = len(pieces)
            printed = len(pieces.filtered(lambda p: p.lock_state == 'printed'))
            rec.print_placed_qty = placed
            rec.print_printed_qty = printed
            qty = rec.quantity or 0
            if printed and printed >= qty and qty > 0:
                rec.print_state = 'printed'
            elif placed >= qty and qty > 0:
                rec.print_state = 'full'
            elif placed > 0:
                rec.print_state = 'partial'
            else:
                rec.print_state = 'none'

    def _print_film_gap_group(self):
        """冷裱屬性值，供排版異膜間距分組。無冷裱則空字串（彼此視為同組）。"""
        self.ensure_one()
        for att in self.product_atts:
            if att.attribute_id.name == '冷裱':
                return (att.name or '').strip()
        return ''

    def _parse_size_cm(self):
        """Parse size as cm → (w_mm, h_mm).

        印刷排版優先用大圖「自動排版」出血後寬高；沒有再回退產品寬高。
        """
        self.ensure_one()

        def _to_float(val):
            try:
                return float(str(val).strip().replace(',', '.'))
            except (TypeError, ValueError):
                return 0.0

        cl = self.checkout_line_id
        if cl:
            w_cm = (
                _to_float(cl.layout_bleed_width)
                or _to_float(cl.product_width)
                or _to_float(self.product_width)
            )
            h_cm = (
                _to_float(cl.layout_bleed_height)
                or _to_float(cl.product_height)
                or _to_float(self.product_height)
            )
        else:
            w_cm = _to_float(self.product_width)
            h_cm = _to_float(self.product_height)
        return w_cm * 10.0, h_cm * 10.0  # cm → mm

    @api.model
    def _piece_fits_roll_width(self, piece_w_mm, piece_h_mm, roll_width_mm, eps=1e-6):
        """允許旋轉：任一邊 ≤ 門幅即可。"""
        if not roll_width_mm or not piece_w_mm or not piece_h_mm:
            return False
        return (
            piece_w_mm <= roll_width_mm + eps
            or piece_h_mm <= roll_width_mm + eps
        )

    def _roll_width_mm_of(self, mat):
        if not mat:
            return 0.0
        return float(mat.roll_width_mm or 0.0) or float(mat.roll_width_cm or 0.0) * 10.0

    def _has_locked_print_pieces(self):
        """已有 reserved/printed 圖塊則不可再改分配門幅。"""
        self.ensure_one()
        return bool(self.print_piece_ids.filtered(
            lambda p: p.order_id
            and p.order_id.state != 'cancel'
            and p.lock_state in ('reserved', 'printed')
        ))

    def action_open_print_pieces(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': '印刷圖塊',
            'res_model': 'dtsc.print.piece',
            'view_mode': 'tree,form',
            'domain': [('makeinline_id', '=', self.id)],
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # 新建後先給一個初始分配；印刷池刷新時會再優化
        to_fix = records.filtered(
            lambda r: not r.print_material_id and r.print_material_candidate_ids
        )
        if to_fix:
            self.env['dtsc.print.pool']._assign_materials_for_lines(to_fix)
        return records

    def write(self, vals):
        size_keys = {'product_width', 'product_height', 'quantity'}
        touched = bool(size_keys & set(vals.keys()))
        old_map = {}
        if touched:
            for rec in self:
                old_map[rec.id] = (rec.product_width, rec.product_height, rec.quantity)
        res = super().write(vals)
        if touched:
            orders = self.env['dtsc.print.order']
            for rec in self:
                old = old_map.get(rec.id)
                if not old:
                    continue
                if (rec.product_width, rec.product_height, rec.quantity) == old:
                    continue
                lines = self.env['dtsc.print.order.line'].search([
                    ('makeinline_id', '=', rec.id),
                    ('order_id.state', 'not in', ('done', 'cancel')),
                ])
                for line in lines:
                    w, h = rec._parse_size_cm()
                    printed = line.piece_ids.filtered(lambda p: p.lock_state == 'printed')
                    if printed:
                        warn = _('項次 %s 尺寸/數量已變更，但已有已印刷圖塊，請人工處理差額。') % (
                            line.display_label,
                        )
                        prev = line.order_id.unplaced_info or ''
                        line.order_id.unplaced_info = (prev + '\n' + warn).strip()
                    else:
                        line.piece_w_mm = w
                        line.piece_h_mm = h
                        if 'quantity' in vals:
                            line.qty = rec.quantity or line.qty
                    orders |= line.order_id
                if orders:
                    orders.write({'need_renest': True})
        return res
