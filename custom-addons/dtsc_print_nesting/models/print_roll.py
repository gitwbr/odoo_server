# -*- coding: utf-8 -*-
import base64
import contextlib
import html
import io
import logging
import os

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# 印刷合成：必須維持來源解析度，禁止為省記憶體降 DPI。
# 畫布估算超過此位元組數時改報錯（勿輸出模糊縮圖）。
_COMPOSE_MAX_CANVAS_BYTES = 1_600_000_000  # ~1.6GB（按 CMYK 4 通道估算）
_COMPOSE_DPI_FALLBACK = 150.0


@contextlib.contextmanager
def _compose_memory_headroom():
    """合成整卷 TIFF 時暫時解除 worker 的 RLIMIT_AS 軟上限。

    Odoo 只設軟上限（limit_memory_hard），硬上限不變，因此可在本行程內調高。
    結束後若虛擬記憶體已超過原上限則維持放寬，交給 Odoo 在請求結束後依
    limit_memory_soft 自動回收 worker，避免同一請求後續配置失敗。
    """
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    except Exception:  # noqa: BLE001
        yield
        return
    raised = False
    if soft != resource.RLIM_INFINITY and (hard == resource.RLIM_INFINITY or hard > soft):
        try:
            resource.setrlimit(resource.RLIMIT_AS, (hard, hard))
            raised = True
        except (ValueError, OSError) as err:
            _logger.warning('無法放寬合成 TIFF 記憶體上限：%s', err)
    try:
        yield
    finally:
        if raised:
            vms = 0
            try:
                with open('/proc/%s/statm' % os.getpid()) as fh:
                    vms = int(fh.read().split()[0]) * os.sysconf('SC_PAGE_SIZE')
            except Exception:  # noqa: BLE001
                vms = 0
            if vms and vms < soft:
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (soft, hard))
                except (ValueError, OSError):
                    pass


def _pil_to_cmyk(Image, img, transform=None):
    """轉成 CMYK 供印刷輸出；白底展開透明通道。有 ICC transform 時走色彩管理。"""
    if img is None:
        return None
    if img.mode == 'CMYK':
        return img
    if img.mode in ('RGBA', 'RGBa'):
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode == 'LA':
        rgba = img.convert('RGBA')
        bg = Image.new('RGB', rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode == 'P':
        img = img.convert('RGBA')
        bg = Image.new('RGB', img.size, (255, 255, 255))
        if 'A' in img.getbands():
            bg.paste(img, mask=img.split()[-1])
        else:
            bg.paste(img)
        img = bg
    elif img.mode == 'L':
        img = img.convert('RGB')
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    if transform is not None:
        from PIL import ImageCms
        return ImageCms.applyTransform(img, transform)
    return img.convert('CMYK')


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
    layout_tiff = fields.Binary(
        string='排版 TIFF',
        attachment=True,
        copy=False,
        help='依本捲圖塊座標合成的整版 TIFF（含留白），供下載印刷。',
    )
    layout_tiff_filename = fields.Char(string='TIFF 檔名', copy=False)
    layout_tiff_note = fields.Text(
        string='合成說明',
        copy=False,
        help='合成時缺圖、降採樣等提示。',
    )

    def _has_layout_tiff_file(self):
        self.ensure_one()
        if self.layout_tiff_filename:
            return True
        return bool(self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_tiff'),
            ('file_size', '>', 0),
        ], limit=1))

    def _rpc_safe_bin_size(self):
        if self.env.context.get('layout_tiff_raw'):
            return self
        return self.with_context(bin_size=True)

    def read(self, fields=None, load='_classic_read'):
        return super(PrintRoll, self._rpc_safe_bin_size()).read(fields=fields, load=load)

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        return super(PrintRoll, self._rpc_safe_bin_size()).search_read(
            domain=domain, fields=fields, offset=offset, limit=limit, order=order, **read_kwargs
        )

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

    def _effect_thumb_style(self, piece):
        """與印刷池 pieceThumbStyle 相同：畫面捲長向右、門幅向下（相對直立預覽多轉 90°）。"""
        rot = (piece.rotation or (90 if piece.rotated else 0)) % 360
        css_rot = (rot - 90) % 360
        flip = ' scaleX(-1)' if piece.flip_h else ''
        base = 'position:absolute;display:block;max-width:none;'
        if css_rot == 0:
            tf = 'transform:scaleX(-1);' if piece.flip_h else ''
            return base + 'left:0;top:0;width:100%;height:100%;object-fit:fill;' + tf
        if css_rot == 180:
            return base + (
                'left:0;top:0;width:100%%;height:100%%;object-fit:fill;'
                'transform:rotate(180deg)%s;' % flip
            )
        box_w = max(piece.height_mm or 1.0, 1e-6)
        box_h = max(piece.width_mm or 1.0, 1e-6)
        return base + (
            'left:50%%;top:50%%;width:%.4f%%;height:%.4f%%;object-fit:fill;'
            'transform:translate(-50%%,-50%%) rotate(%ddeg)%s;'
        ) % (box_h / box_w * 100.0, box_w / box_h * 100.0, css_rot, flip)

    def _build_effect_html(self, max_w=900.0, max_h=300.0, min_h=0.0, img_size=512, show_label=True):
        """印刷效果圖：與印刷池同方向，圖塊貼大圖項次預覽縮圖。"""
        self.ensure_one()
        width = self.roll_width_mm or 1.0
        length = max(
            [self.used_length_mm or 0.0, 1.0]
            + [p.y_mm + p.height_mm for p in self.piece_ids]
        )
        scale = min(max_w / length, max_h / width)
        if min_h:
            scale = max(scale, min_h / width)
        box_w = length * scale
        box_h = width * scale
        colors = {'open': '#C5E1A5', 'reserved': '#FFCC80', 'printed': '#B0BEC5'}

        pool = self.env['dtsc.print.pool']
        url_cache = {}

        def preview_url(ml):
            key = ml.checkout_line_id.id if ml else 0
            if key not in url_cache:
                url = pool._makeinline_preview_url(ml) if ml else False
                if url and img_size:
                    path, _sep, query = url.partition('?')
                    url = '%s/%sx%s?%s' % (path, img_size, img_size, query)
                url_cache[key] = url
            return url_cache[key]

        parts = [
            '<div style="position:relative;display:inline-block;vertical-align:top;'
            'width:%.1fpx;height:%.1fpx;background:#fff;border:1px solid #999;'
            'overflow:hidden;box-sizing:content-box;">' % (box_w, box_h)
        ]
        for p in self.piece_ids:
            title = html.escape(p.label or '')
            parts.append(
                '<div title="%s" style="position:absolute;left:%.1fpx;top:%.1fpx;'
                'width:%.1fpx;height:%.1fpx;overflow:hidden;background:%s;'
                'outline:1px solid rgba(0,0,0,.35);">'
                % (
                    title,
                    p.y_mm * scale,
                    p.x_mm * scale,
                    p.height_mm * scale,
                    p.width_mm * scale,
                    colors.get(p.lock_state, '#C5E1A5'),
                )
            )
            url = preview_url(p.makeinline_id)
            if url:
                parts.append(
                    '<img src="%s" alt="" loading="lazy" style="%s"/>'
                    % (html.escape(url), self._effect_thumb_style(p))
                )
            if show_label and p.label:
                parts.append(
                    '<span style="position:absolute;left:1px;bottom:1px;font-size:10px;'
                    'line-height:12px;padding:0 3px;background:rgba(255,255,255,.8);'
                    'color:#111;white-space:nowrap;">%s</span>' % title
                )
            parts.append('</div>')
        parts.append('</div>')
        return ''.join(parts)

    def action_reserve_all(self):
        self.mapped('order_id')._ensure_layout_editable()
        for rec in self:
            rec.piece_ids.filtered(lambda p: p.lock_state == 'open').write(
                {'lock_state': 'reserved'}
            )
        return True

    def action_mark_printed(self):
        for rec in self:
            if rec.order_id.state in ('cancel',):
                raise UserError(_('作廢單不可標記已印刷。'))
            rec.piece_ids.filtered(lambda p: p.lock_state != 'printed').write(
                {'lock_state': 'printed'}
            )
            rec.order_id.line_ids._sync_placed_qty()
        return True

    def action_unlock_all_reserved(self):
        self.mapped('order_id')._ensure_layout_editable()
        for rec in self:
            rec.piece_ids.filtered(lambda p: p.lock_state == 'reserved').write(
                {'lock_state': 'open'}
            )
        return True

    def action_compose_layout_tiff(self):
        """手動重新合成排版 TIFF。"""
        for rec in self:
            rec._compose_layout_tiff()
        return True

    def action_download_layout_tiff(self):
        """下載合成 TIFF（走 /web/content，不經表單 JSON）。"""
        self.ensure_one()
        if not self._has_layout_tiff_file():
            raise UserError(_('尚無排版 TIFF，請先點「重新合成排版TIFF」。'))
        return self._layout_tiff_download_action()

    def _layout_tiff_download_url(self):
        self.ensure_one()
        return '/web/content?model=dtsc.print.roll&id=%s&field=layout_tiff&filename_field=layout_tiff_filename&download=true' % self.id

    def _layout_tiff_download_action(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'dtsc_print_nesting.download_urls',
            'params': {'urls': [roll._layout_tiff_download_url() for roll in self]},
        }

    def _compose_layout_tiff(self):
        """依本捲圖塊座標，把各項次 TIFF 貼到白底畫布（含間隙留白），寫入 layout_tiff。"""
        try:
            from PIL import Image
        except ImportError as err:
            raise UserError(_('伺服器未安裝 Pillow，無法合成排版 TIFF。')) from err

        total = len(self)
        for idx, rec in enumerate(self):
            rec = rec.with_context(print_compose_slot=(idx, total))
            with _compose_memory_headroom():
                rec._compose_layout_tiff_one(Image)

    def _print_cmyk_icc(self):
        """回傳 (ICC bytes|None, 檔名)；取印刷單公司設定。"""
        company = self.order_id.company_id or self.env.company
        data = company.sudo().with_context(bin_size=False).print_cmyk_icc
        if not data:
            return None, ''
        return base64.b64decode(data), company.sudo().print_cmyk_icc_filename or ''

    def _compose_progress(self, stage_pct, message):
        """回報合成進度（context print_compose_job 有值時才寫）。"""
        key = self.env.context.get('print_compose_job')
        if not key:
            return
        idx, total = self.env.context.get('print_compose_slot') or (0, 1)
        total = max(int(total or 1), 1)
        overall = (idx + max(0.0, min(stage_pct, 100.0)) / 100.0) / total * 100.0
        prefix = ('第 %s/%s 捲 %s：' % (idx + 1, total, self.name or '')) if total > 1 else ''
        self.env['dtsc.print.compose.job']._report(
            key, percent=min(overall, 99.0), message=prefix + message, state='running',
        )

    @api.model
    def _tiff_magic_ok(self, raw):
        """True = TIFF 檔頭；False = 明顯非 TIFF（如 JPEG）。"""
        if not raw or len(raw) < 4:
            return False
        if raw[:2] == b'\xff\xd8':
            return False
        return raw[:4] in (b'II*\x00', b'MM\x00*')

    @api.model
    def _read_pil_dpi(self, img):
        """從 TIFF tag / info 讀 DPI；讀不到回傳 None。"""
        tag = getattr(img, 'tag_v2', None)
        if tag is not None:
            try:
                xres = float(tag[282])
                yres = float(tag[283])
                unit = 2
                try:
                    unit = int(tag[296])
                except Exception:  # noqa: BLE001
                    unit = 2
                if xres > 0 and yres > 0:
                    if unit == 3:  # pixels/cm
                        return (xres * 2.54 + yres * 2.54) / 2.0
                    return (xres + yres) / 2.0
            except Exception:  # noqa: BLE001
                pass
        dpi_info = img.info.get('dpi') or ()
        if len(dpi_info) >= 1 and dpi_info[0]:
            try:
                return float(dpi_info[0])
            except Exception:  # noqa: BLE001
                return None
        return None

    def _compose_layout_tiff_one(self, Image):
        self.ensure_one()
        pieces = self.piece_ids.sorted(lambda p: (p.y_mm, p.x_mm, p.id))
        if not pieces:
            self.write({
                'layout_tiff': False,
                'layout_tiff_filename': False,
                'layout_tiff_note': _('無圖塊，未生成 TIFF。'),
            })
            return

        notes = []
        # makeinline_id -> (PIL Image|None, dpi|None, warn|None, src_mode)
        tiff_cache = {}
        src_modes = set()

        def load_source(ml):
            mid = ml.id if ml else 0
            if mid in tiff_cache:
                return tiff_cache[mid]
            raw, fname = self._read_makeinline_tiff_bytes(ml)
            label = ml.display_name if ml else mid
            if not raw:
                tiff_cache[mid] = (None, None, _('項次 %s 無 TIFF') % label, None)
                return tiff_cache[mid]
            if not self._tiff_magic_ok(raw):
                msg = _(
                    '項次 %s 存檔不是有效 TIFF（可能是預覽/JPEG）。'
                    '請回大圖訂單重新上傳印刷原檔 TIFF。'
                ) % label
                tiff_cache[mid] = (None, None, msg, None)
                return tiff_cache[mid]
            try:
                img = Image.open(io.BytesIO(raw))
                img.load()
                src_dpi = self._read_pil_dpi(img)
                src_mode = img.mode or ''
                # 來源盡量保持原色彩空間；貼到 CMYK 畫布時再統一轉換
                tiff_cache[mid] = (img, src_dpi, None, src_mode)
                return tiff_cache[mid]
            except Exception as err:  # noqa: BLE001
                msg = _('項次 %s TIFF 無法開啟：%s') % (label, err)
                _logger.warning(msg)
                tiff_cache[mid] = (None, None, msg, None)
                return tiff_cache[mid]

        def infer_dpi_from_piece(p, img):
            """無 DPI 標籤時，用圖塊物理尺寸與像素反推。"""
            if img is None:
                return None
            pw, ph = img.size
            if p.rotated:
                pw, ph = ph, pw
            w_mm = float(p.width_mm or 0)
            h_mm = float(p.height_mm or 0)
            if w_mm <= 0 or h_mm <= 0 or pw <= 0 or ph <= 0:
                return None
            dpi_x = pw / (w_mm / 25.4)
            dpi_y = ph / (h_mm / 25.4)
            return (dpi_x + dpi_y) / 2.0

        # 來源 DPI：取各塊最大值（印刷不降解析度）
        dpi = None
        n_pieces = len(pieces)
        self._compose_progress(0, _('讀取來源 TIFF…'))
        for i, p in enumerate(pieces):
            img, src_dpi, warn, src_mode = load_source(p.makeinline_id)
            self._compose_progress(30.0 * (i + 1) / n_pieces, _('讀取來源 TIFF（%s/%s）') % (i + 1, n_pieces))
            if warn:
                notes.append(warn)
            if src_mode:
                src_modes.add(src_mode)
            cand = src_dpi or infer_dpi_from_piece(p, img)
            if cand and cand > 0:
                dpi = max(dpi or 0.0, cand)

        if not dpi:
            dpi = _COMPOSE_DPI_FALLBACK
            notes.append(_('未從來源讀到 DPI，暫用 %.0f（請確認來源 TIFF 含解析度）') % dpi)

        # 本單相對座標：去掉本捲歷史偏移，只輸出本印刷單這一段
        y0 = min(p.y_mm for p in pieces)
        y_extent = max(p.y_mm + p.height_mm for p in pieces) - y0
        x_extent = max(p.x_mm + p.width_mm for p in pieces)
        roll_w = float(self.roll_width_mm or 0) or x_extent

        def mm_to_px(mm, d):
            return max(1, int(round(float(mm or 0) / 25.4 * d)))

        canvas_w = mm_to_px(roll_w, dpi)
        canvas_h = mm_to_px(y_extent, dpi)
        est_bytes = canvas_w * canvas_h * 4  # CMYK
        if est_bytes > _COMPOSE_MAX_CANVAS_BYTES:
            self.write({
                'layout_tiff': False,
                'layout_tiff_filename': False,
                'layout_tiff_note': _(
                    '排版 TIFF 未生成：畫布約 %sx%s px（DPI %.0f，約 %.1f GB），超過伺服器安全上限。'
                    '請勿降解析度印刷；請聯絡管理員提高記憶體或改分段輸出。'
                ) % (canvas_w, canvas_h, dpi, est_bytes / (1024 ** 3)),
            })
            return

        # 任一來源無效則整卷不輸出模糊替代檔
        if any(load_source(p.makeinline_id)[0] is None for p in pieces):
            self.write({
                'layout_tiff': False,
                'layout_tiff_filename': False,
                'layout_tiff_note': _(
                    '排版 TIFF 未生成：來源大圖不是可用的原解析度 TIFF。\n%s'
                ) % '\n'.join(dict.fromkeys(notes)),
            })
            return

        self._compose_progress(32, _('建立畫布 %sx%s px…') % (canvas_w, canvas_h))
        try:
            # 印刷輸出固定 CMYK；白紙 = (0,0,0,0)
            canvas = Image.new('CMYK', (canvas_w, canvas_h), (0, 0, 0, 0))
        except Exception as err:  # noqa: BLE001
            self.write({
                'layout_tiff': False,
                'layout_tiff_filename': False,
                'layout_tiff_note': _(
                    '排版 TIFF 合成失敗（記憶體不足：%s）。'
                    '不會降解析度輸出；請提高 worker 記憶體後重試。'
                ) % err,
            })
            return

        placed = 0
        converted_from_rgb = False
        icc_bytes, icc_name = self._print_cmyk_icc()
        icc_intent = int(self.env['ir.config_parameter'].sudo().get_param(
            'dtsc_print_nesting.print_cmyk_intent', '0') or 0)
        icc_transforms = {}

        def rgb_to_cmyk_transform(src_icc):
            """RGB 來源 → 印刷 CMYK ICC；來源無內嵌描述檔時視為 sRGB。"""
            if not icc_bytes:
                return None
            cache_key = src_icc or b''
            if cache_key not in icc_transforms:
                from PIL import ImageCms
                out_prof = ImageCms.ImageCmsProfile(io.BytesIO(icc_bytes))
                in_prof = None
                if src_icc:
                    try:
                        in_prof = ImageCms.ImageCmsProfile(io.BytesIO(src_icc))
                        if (in_prof.profile.xcolor_space or '').strip().upper() != 'RGB':
                            in_prof = None
                    except Exception:  # noqa: BLE001
                        in_prof = None
                if in_prof is None:
                    in_prof = ImageCms.createProfile('sRGB')
                flags_enum = getattr(ImageCms, 'Flags', None)
                bpc = (
                    getattr(flags_enum, 'BLACKPOINTCOMPENSATION', None) if flags_enum else None
                ) or getattr(ImageCms, 'FLAGS', {}).get('BLACKPOINTCOMPENSATION', 0)
                icc_transforms[cache_key] = ImageCms.buildTransform(
                    in_prof, out_prof, 'RGB', 'CMYK',
                    renderingIntent=icc_intent, flags=int(bpc),
                )
            return icc_transforms[cache_key]

        # 僅在毫米換算有 1px 級誤差時微調，避免大幅縮放變糊
        resample = getattr(getattr(Image, 'Resampling', Image), 'LANCZOS', Image.LANCZOS)
        rot = getattr(getattr(Image, 'Transpose', Image), 'ROTATE_90', Image.ROTATE_90)
        for i, p in enumerate(pieces):
            self._compose_progress(35.0 + 35.0 * i / n_pieces, _('貼圖（%s/%s）') % (i + 1, n_pieces))
            src, _src_dpi, _warn, src_mode = load_source(p.makeinline_id)
            tw = mm_to_px(p.width_mm, dpi)
            th = mm_to_px(p.height_mm, dpi)
            left = mm_to_px(p.x_mm, dpi)
            top = mm_to_px(p.y_mm - y0, dpi)
            if src is None:
                continue
            try:
                tile = src.copy()
                # 先水平翻轉，再依角度旋轉（0/90/180/270）
                if getattr(p, 'flip_h', False):
                    flip = getattr(
                        getattr(Image, 'Transpose', Image),
                        'FLIP_LEFT_RIGHT',
                        Image.FLIP_LEFT_RIGHT,
                    )
                    tile = tile.transpose(flip)
                rot_deg = int(getattr(p, 'rotation', None) or (90 if p.rotated else 0)) % 360
                if rot_deg == 90:
                    tile = tile.transpose(rot)
                elif rot_deg == 180:
                    rot180 = getattr(
                        getattr(Image, 'Transpose', Image),
                        'ROTATE_180',
                        Image.ROTATE_180,
                    )
                    tile = tile.transpose(rot180)
                elif rot_deg == 270:
                    rot270 = getattr(
                        getattr(Image, 'Transpose', Image),
                        'ROTATE_270',
                        Image.ROTATE_270,
                    )
                    tile = tile.transpose(rot270)
                if tile.size != (tw, th):
                    # 允許極小誤差；若差超過 2%，代表來源尺寸與排版毫米不一致
                    sw, sh = tile.size
                    drift = max(abs(sw - tw) / float(tw or 1), abs(sh - th) / float(th or 1))
                    if drift > 0.02:
                        notes.append(_(
                            '圖塊 %s 像素 %sx%s 與排版毫米換算 %sx%s（DPI %.0f）差 %.1f%%，已按毫米對齊縮放'
                        ) % (p.label or p.id, sw, sh, tw, th, dpi, drift * 100.0))
                    tile = tile.resize((tw, th), resample)
                transform = None
                if src_mode and src_mode != 'CMYK':
                    converted_from_rgb = True
                    try:
                        transform = rgb_to_cmyk_transform(src.info.get('icc_profile'))
                    except Exception as err:  # noqa: BLE001
                        notes.append(_('ICC 色彩轉換失敗，改用軟體近似轉換：%s') % err)
                tile = _pil_to_cmyk(Image, tile, transform)
                if left + tw > canvas_w or top + th > canvas_h:
                    tile = tile.crop((
                        0, 0,
                        min(tw, max(0, canvas_w - left)),
                        min(th, max(0, canvas_h - top)),
                    ))
                if left < canvas_w and top < canvas_h and tile.size[0] > 0 and tile.size[1] > 0:
                    canvas.paste(tile, (max(0, left), max(0, top)))
                    placed += 1
            except Exception as err:  # noqa: BLE001
                notes.append(_('圖塊 %s 貼圖失敗：%s') % (p.label or p.id, err))

        self._compose_progress(72, _('壓縮儲存 CMYK TIFF（檔案大，需要一點時間）…'))
        try:
            buf = io.BytesIO()
            if icc_bytes:
                # Pillow 8 的 TIFF 存檔只認 im.info，不認 icc_profile 參數
                canvas.info['icc_profile'] = icc_bytes
            canvas.save(
                buf,
                format='TIFF',
                compression='tiff_lzw',
                dpi=(dpi, dpi),
            )
            raw_out = buf.getvalue()
        except Exception as err:  # noqa: BLE001
            self.write({
                'layout_tiff': False,
                'layout_tiff_filename': False,
                'layout_tiff_note': _(
                    '排版 TIFF 寫入失敗：%s。請點「重新合成排版TIFF」。'
                ) % err,
            })
            return
        finally:
            try:
                canvas.close()
            except Exception:  # noqa: BLE001
                pass
            for mid, cached in list(tiff_cache.items()):
                img = cached[0] if cached else None
                try:
                    if img is not None:
                        img.close()
                except Exception:  # noqa: BLE001
                    pass
                tiff_cache[mid] = (None, None, None, None)

        fname = '%s-%s.tif' % (
            self.order_id.name or 'P',
            self.name or ('R%s' % self.sequence),
        )
        mode_txt = ','.join(sorted(src_modes)) or '?'
        note = _(
            '已按來源原解析度合成 CMYK：%s 塊 / %sx%s px / DPI %.0f；來源模式 %s'
        ) % (placed, canvas_w, canvas_h, dpi, mode_txt)
        if converted_from_rgb:
            if icc_bytes and icc_transforms:
                notes.append(_('RGB 來源已用 ICC「%s」轉成 CMYK（%s）。') % (
                    icc_name or 'ICC', _('相對比色') if icc_intent == 1 else _('感知'),
                ))
            else:
                notes.append(_(
                    '部分來源非 CMYK，已用軟體近似轉成 CMYK（未設定印刷 ICC，顏色可能不準；'
                    '可到設定上傳印刷機 CMYK ICC）。'
                ))
        if icc_bytes:
            notes.append(_('輸出檔已內嵌 ICC「%s」。') % (icc_name or 'ICC'))
        if notes:
            uniq = []
            for n in notes:
                if n not in uniq:
                    uniq.append(n)
            note = note + '\n' + '\n'.join(uniq)

        self._compose_progress(88, _('寫入檔案（%.0f MB）…') % (len(raw_out) / 1048576.0))
        # 禁止 Odoo 自動把合成 TIFF 壓成 1920 JPEG
        self.with_context(image_no_postprocess=True).write({
            'layout_tiff': base64.b64encode(raw_out),
            'layout_tiff_filename': fname,
            'layout_tiff_note': note,
        })
        _logger.info(
            'print roll %s composed layout tiff %s bytes (%s)',
            self.id, len(raw_out), fname,
        )

    def _read_makeinline_tiff_bytes(self, makeinline):
        """回傳 (raw_bytes|None, filename|None)。"""
        if not makeinline:
            return None, None
        cl = makeinline.checkout_line_id
        if not cl:
            return None, None
        Att = self.env['ir.attachment'].sudo()
        att = Att.search([
            ('res_model', '=', 'dtsc.checkoutline'),
            ('res_id', '=', cl.id),
            ('res_field', '=', 'layout_tiff'),
        ], limit=1)
        if att and att.datas:
            raw = base64.b64decode(att.with_context(bin_size=False).datas)
            return raw, att.name or cl.layout_tiff_filename
        data = cl.with_context(bin_size=False, layout_tiff_raw=True).layout_tiff
        if data:
            if isinstance(data, bytes):
                try:
                    raw = base64.b64decode(data)
                except Exception:  # noqa: BLE001
                    raw = data
            else:
                raw = base64.b64decode(data)
            return raw, cl.layout_tiff_filename
        return None, None


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
    rotation = fields.Integer(string='旋轉角度', default=0)
    flip_h = fields.Boolean(string='水平翻轉', default=False)
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
    order_state = fields.Selection(
        related='order_id.state',
        string='印刷單狀態',
        store=False,
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
        force = self.env.context.get('force_print_piece_unlink')
        if not force and self.filtered(lambda p: p.lock_state == 'printed'):
            raise UserError(_('已印刷圖塊不可刪除。'))
        if not force and self.filtered(lambda p: p.lock_state == 'reserved'):
            raise UserError(_('已鎖定圖塊請先解鎖再刪除／重排。若要整單作廢，請用印刷單「作廢」。'))
        rolls = self.mapped('roll_id')
        lines = self.mapped('order_line_id')
        makeinlines = self.mapped('makeinline_id')
        res = super().unlink()
        if rolls.exists():
            rolls._refresh_preview_svg()
        if lines.exists():
            lines._sync_placed_qty()
        if makeinlines.exists():
            makeinlines._compute_print_state()
        return res

    def action_reserve(self):
        self.mapped('order_id')._ensure_layout_editable()
        for rec in self:
            if rec.lock_state == 'printed':
                raise UserError(_('已印刷圖塊不可改為鎖定。'))
            rec.lock_state = 'reserved'
        return True

    def action_unlock(self):
        self.mapped('order_id')._ensure_layout_editable()
        for rec in self:
            if rec.lock_state == 'printed':
                raise UserError(_('已印刷圖塊不可解鎖。'))
            rec.lock_state = 'open'
        return True

    def action_mark_printed(self):
        self.write({'lock_state': 'printed'})
        return True

