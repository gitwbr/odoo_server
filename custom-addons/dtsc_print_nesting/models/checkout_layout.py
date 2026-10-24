# -*- coding: utf-8 -*-
import base64
import logging
import os
import re
from io import BytesIO

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import human_size

_logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

_LAYOUT_PREVIEW_MAX = 800  # 預覽最長邊像素
_BIN_SIZE_RE = re.compile(r'^\d+(\.\d*)? [^0-9]+$')


class CheckoutLayout(models.Model):
    _inherit = 'dtsc.checkout'

    # 僅顯示：內部工單(含代工進內部工單) + 捲料
    layout_line_ids = fields.One2many(
        'dtsc.checkoutline',
        'checkout_product_id',
        string='自動排版項次',
        domain=[
            ('is_roll_material', '=', True),
            ('is_purchse', 'in', ('make_in', 'make_om')),
        ],
    )

    @api.model
    def _is_layout_tiff_check_enabled(self):
        """系統參數：是否啟用轉工單前 TIFF/出血檢查。"""
        val = self.env['ir.config_parameter'].sudo().get_param(
            'dtsc_print_nesting.enable_layout_tiff_check', 'True'
        )
        return str(val).strip().lower() in ('1', 'true', 'yes', 'y')

    def _layout_tiff_check_lines(self):
        """需檢查的項次：功能開啟 + 捲料 + 會進內部工單(make_in/make_om)。"""
        self.ensure_one()
        if not self._is_layout_tiff_check_enabled():
            return self.env['dtsc.checkoutline']
        return self.product_ids.filtered(
            lambda l: l.is_roll_material and l.is_purchse in ('make_in', 'make_om')
        )

    def in_out_check(self):
        """訂單確認（轉工單）前：內部工單捲料項次須已上傳 TIFF 且出血寬高有值。"""
        for checkout in self:
            targets = checkout._layout_tiff_check_lines()
            if not targets:
                continue
            # 勿用 bool(layout_tiff)：會把整份大 TIFF 讀進記憶體
            missing = targets.filtered(lambda l: not l._has_layout_tiff_file())
            if missing:
                seqs = ', '.join(str(l.sequence) for l in missing.sorted('sequence'))
                raise UserError(
                    _('自動排版：以下內部工單捲料項次尚未上傳 TIFF 圖檔，無法轉工單。'
                      '請至「自動排版」標籤上傳後再確認：%s') % seqs
                )
            bad_size = targets.filtered(
                lambda l: (
                    not (l.layout_bleed_width or '').strip()
                    or not (l.layout_bleed_height or '').strip()
                )
            )
            if bad_size:
                seqs = ', '.join(str(l.sequence) for l in bad_size.sorted('sequence'))
                raise UserError(
                    _('自動排版：以下內部工單捲料項次尚未填寫出血後寬高，無法轉工單。'
                      '請至「自動排版」標籤補齊後再確認：%s') % seqs
                )
        return super().in_out_check()


class CheckOutLineLayout(models.Model):
    _inherit = 'dtsc.checkoutline'

    # 僅寫入這些欄位時，跳過 dtsc 對「已轉應收/已出貨」的 write 鎖定（不改 dtsc 源碼）
    _LAYOUT_ONLY_FIELDS = frozenset({
        'is_roll_material', 'layout_material_id', 'layout_material_ids',
        'layout_bleed_width', 'layout_bleed_height',
        'layout_tiff', 'layout_tiff_filename',
        'layout_tiff_preview',
    })

    is_roll_material = fields.Boolean(
        string='原料為捲料',
        compute='_compute_is_roll_material',
        store=True,
        index=True,
    )
    layout_material_ids = fields.Many2many(
        'product.template',
        'dtsc_checkoutline_layout_material_rel',
        'line_id',
        'material_id',
        string='排版捲材',
        compute='_compute_is_roll_material',
        store=True,
        help='商品「基礎扣料物」中所有序號追蹤（捲料）原料，多選時全部顯示。',
    )
    layout_material_id = fields.Many2one(
        'product.template',
        string='排版捲材(首筆)',
        compute='_compute_is_roll_material',
        store=True,
        help='多選捲材時取第一筆，供相容既有邏輯。',
    )
    layout_bleed_width = fields.Char(
        string='出血後寬',
        help='自動排版用尺寸（cm）。上傳 TIFF 後依檔案像素/DPI 自動帶入，可手動改。',
        copy=False,
    )
    layout_bleed_height = fields.Char(
        string='出血後高',
        help='自動排版用尺寸（cm）。上傳 TIFF 後依檔案像素/DPI 自動帶入，可手動改。',
        copy=False,
    )
    layout_tiff = fields.Binary(string='排版 TIFF', attachment=True, copy=False)
    layout_tiff_filename = fields.Char(string='TIFF 檔名', copy=False)
    layout_tiff_colorspace = fields.Char(
        string='色彩模式',
        copy=False,
        readonly=True,
        help='上傳 TIFF 時自動偵測（CMYK / RGB / 灰度等）。合成印刷檔一律輸出 CMYK。',
    )
    layout_tiff_preview = fields.Binary(
        string='TIFF 預覽',
        attachment=True,
        copy=False,
        help='由 TIFF 自動產生的 JPEG 縮圖，僅供瀏覽，不參與印刷。',
    )

    @api.model
    def _layout_tiff_colorspace_label(self, mode):
        """Pillow mode → 顯示用色彩模式。"""
        mode = (mode or '').upper()
        if mode == 'CMYK':
            return 'CMYK'
        if mode in ('RGB', 'RGBA', 'RGBX'):
            return 'RGB'
        if mode in ('L', 'LA', 'I', 'I;16', 'I;16B', 'I;16L'):
            return '灰度'
        return mode or ''

    def _has_layout_tiff_file(self):
        """是否已有印刷 TIFF（只查附件 metadata，不讀檔內容）。"""
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
        """開啟表單/RPC 時禁止把整份 TIFF base64 塞進 JSON（否則 MemoryError）。"""
        if self.env.context.get('layout_tiff_raw'):
            return self
        return self.with_context(bin_size=True)

    def read(self, fields=None, load='_classic_read'):
        return super(CheckOutLineLayout, self._rpc_safe_bin_size()).read(
            fields=fields, load=load
        )

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None, **read_kwargs):
        return super(CheckOutLineLayout, self._rpc_safe_bin_size()).search_read(
            domain=domain, fields=fields, offset=offset, limit=limit, order=order, **read_kwargs
        )

    @api.model
    def onchange(self, values, field_name, field_onchange):
        result = super(CheckOutLineLayout, self._rpc_safe_bin_size()).onchange(
            values, field_name, field_onchange
        )
        # 雙保險：onchange 回傳值若含超大 base64，改成僅檔名提示
        value = result.get('value') or {}
        for key in ('layout_tiff',):
            raw = value.get(key)
            if isinstance(raw, (str, bytes)) and len(raw) > 512:
                value[key] = True
        return result

    def _resolve_roll_materials_for_layout(self):
        """序號追蹤的基礎扣料物視為捲料（全部回傳，支援多選門幅）。"""
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

    def _resolve_roll_material_for_layout(self):
        """相容舊呼叫：取第一筆捲材。"""
        return self._resolve_roll_materials_for_layout()[:1]

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
    def _compute_is_roll_material(self):
        for rec in self:
            mats = rec._resolve_roll_materials_for_layout()
            rec.layout_material_ids = mats
            rec.layout_material_id = mats[:1]
            rec.is_roll_material = bool(mats)

    @api.model
    def _decode_layout_binary(self, data):
        if not data:
            return b''
        if isinstance(data, bytes):
            raw = data
        else:
            raw = data.encode('ascii') if isinstance(data, str) else bytes(data)
        # 已是 TIFF 原位元組時勿再當 base64 解（否則大檔白解且可能損壞）
        if len(raw) >= 4 and raw[:4] in (b'II*\x00', b'MM\x00*'):
            return raw
        try:
            return base64.b64decode(raw, validate=False)
        except Exception:
            return raw

    @api.model
    def _format_layout_cm(self, value):
        text = ('%.4f' % value).rstrip('0').rstrip('.')
        return text or '0'

    @api.model
    def _pil_resample(self):
        if hasattr(Image, 'Resampling'):
            return Image.Resampling.LANCZOS
        return Image.LANCZOS

    @api.model
    def _process_layout_tiff(self, binary_data, need_size=True, need_preview=True):
        """一次開啟 TIFF：可回傳出血尺寸與 JPEG 預覽（base64）。

        binary_data 可為 base64 字串／bytes，或直接 TIFF 原位元組。
        :return: dict keys: bleed_width, bleed_height, preview (均可缺)
        """
        if Image is None:
            raise UserError(_('伺服器未安裝 Pillow，無法處理 TIFF。'))
        raw = self._decode_layout_binary(binary_data)
        if not raw:
            return {}

        result = {}
        try:
            with Image.open(BytesIO(raw)) as img:
                width_px, height_px = img.size
                result['colorspace'] = self._layout_tiff_colorspace_label(img.mode)
                result['colorspace_mode'] = img.mode or ''

                if need_size:
                    xres = yres = None
                    unit = 2  # inch
                    tag = getattr(img, 'tag_v2', None)
                    if tag is not None:
                        try:
                            xres = float(tag[282])
                            yres = float(tag[283])
                        except Exception:
                            pass
                        try:
                            unit = int(tag[296])
                        except Exception:
                            unit = 2
                    if not xres or not yres:
                        dpi = img.info.get('dpi') or ()
                        if len(dpi) >= 2 and dpi[0] and dpi[1]:
                            xres, yres = float(dpi[0]), float(dpi[1])
                            unit = 2
                    if not xres or not yres:
                        raise UserError(
                            _('TIFF 缺少解析度（DPI）資訊，無法自動換算出血後寬高（像素：%sx%s）。'
                              '請手動填寫，或以含 DPI 的 TIFF 重新匯出。')
                            % (width_px, height_px)
                        )
                    if unit == 3:
                        width_cm = width_px / xres
                        height_cm = height_px / yres
                    else:
                        width_cm = (width_px / xres) * 2.54
                        height_cm = (height_px / yres) * 2.54
                    result['bleed_width'] = self._format_layout_cm(width_cm)
                    result['bleed_height'] = self._format_layout_cm(height_cm)

                if need_preview:
                    try:
                        result['preview'] = self._make_tiff_preview_b64(img)
                    except Exception as err:
                        # MemoryError 的 str() 常為空，必須帶例外類型
                        _logger.warning(
                            '產生 TIFF 預覽失敗: %s: %s',
                            type(err).__name__, err or '(no message)',
                            exc_info=True,
                        )
                        result['preview_error'] = '%s: %s' % (
                            type(err).__name__, err or '(no message)',
                        )
        except UserError:
            raise
        except Exception as err:
            _logger.warning('讀取 TIFF 失敗: %s', err)
            raise UserError(_('無法從 TIFF 讀取資訊：%s') % err)
        return result

    @api.model
    def _make_tiff_preview_b64(self, img):
        """低記憶體預覽：先整數降採樣／就地縮圖，再轉 RGB JPEG。

        禁止先 img.copy() 整張大 CMYK（常見 MemoryError，且 str 為空）。
        """
        try:
            img.draft(img.mode, (_LAYOUT_PREVIEW_MAX, _LAYOUT_PREVIEW_MAX))
        except Exception:
            pass

        w, h = img.size
        max_side = max(w, h) or 1
        factor = max(1, max_side // _LAYOUT_PREVIEW_MAX)
        work = img
        if factor > 1 and hasattr(img, 'reduce'):
            try:
                work = img.reduce(factor)
            except Exception as err:
                _logger.debug('TIFF reduce 預覽降採樣失敗，改 thumbnail: %s', err)
                work = img

        # 就地縮到預覽邊長，避免再複製一份全圖
        if work is img:
            work.thumbnail(
                (_LAYOUT_PREVIEW_MAX, _LAYOUT_PREVIEW_MAX),
                self._pil_resample(),
            )
            thumb = work
        else:
            thumb = work
            thumb.thumbnail(
                (_LAYOUT_PREVIEW_MAX, _LAYOUT_PREVIEW_MAX),
                self._pil_resample(),
            )

        if thumb.mode == 'RGBA':
            background = Image.new('RGB', thumb.size, (255, 255, 255))
            background.paste(thumb, mask=thumb.split()[-1])
            thumb = background
        elif thumb.mode == 'CMYK':
            # 預覽用；印刷原檔仍是 CMYK 附件
            thumb = thumb.convert('RGB')
        elif thumb.mode != 'RGB':
            thumb = thumb.convert('RGB')
        buf = BytesIO()
        thumb.save(buf, format='JPEG', quality=85, optimize=True)
        return base64.b64encode(buf.getvalue())

    @api.model
    def _apply_layout_tiff_vals(self, vals):
        """vals 含 layout_tiff（base64）時：自動寫入出血後寬高 + 預覽圖。

        大檔請走 multipart 控制器 `_store_layout_tiff_raw`，勿經前端 JSON-RPC。
        """
        data = vals.get('layout_tiff')
        if not data:
            if 'layout_tiff' in vals and not data:
                vals['layout_tiff_preview'] = False
                vals['layout_tiff_colorspace'] = False
            return
        # 已是「大小字串」(bin_size) 則略過，避免誤處理
        if isinstance(data, str) and _BIN_SIZE_RE.match(data.strip()):
            return
        info = self._process_layout_tiff(data, need_size=True, need_preview=True)
        if info.get('bleed_width'):
            vals['layout_bleed_width'] = info['bleed_width']
        if info.get('bleed_height'):
            vals['layout_bleed_height'] = info['bleed_height']
        if info.get('colorspace'):
            vals['layout_tiff_colorspace'] = info['colorspace']
        if info.get('preview'):
            vals['layout_tiff_preview'] = info['preview']

    @api.model
    def _assert_raw_is_tiff(self, raw):
        """拒絕 JPEG/假副檔名，避免印刷合成讀到預覽圖。"""
        if not raw or len(raw) < 4:
            raise UserError(_('檔案內容為空或過短。'))
        if raw[:2] == b'\xff\xd8':
            raise UserError(_(
                '檔案內容是 JPEG，不是 TIFF。印刷必須上傳原解析度 .tif/.tiff，'
                '請勿上傳預覽圖或改副檔名的 JPG。'
            ))
        if raw[:4] not in (b'II*\x00', b'MM\x00*'):
            raise UserError(_(
                '檔案不是有效的 TIFF（檔頭不符）。請重新匯出印刷用 TIFF 後再上傳。'
            ))

    def _store_layout_tiff_raw(self, raw, filename):
        """由 HTTP multipart 寫入 filestore，並回填出血尺寸 / 預覽。

        先解析再落盤：解析失敗時不會清掉舊檔或留下半成品附件。
        """
        self.ensure_one()
        self._validate_layout_tiff_filename(filename)
        self._assert_raw_is_tiff(raw)

        # 先解析（失敗直接拋錯；預覽失敗不阻斷上傳）
        # 直接傳原始 bytes，避免再 base64 膨脹佔記憶體
        info = self._process_layout_tiff(
            raw,
            need_size=True,
            need_preview=True,
        )
        if not info.get('bleed_width') or not info.get('bleed_height'):
            raise UserError(_('無法從 TIFF 取得出血後尺寸，請確認檔案含 DPI 資訊。'))

        # 必須跳過 base.image_autoresize：否則 TIFF 會被壓成 ≤1920 JPEG，印刷檔毀損
        Attachment = self.env['ir.attachment'].with_context(image_no_postprocess=True)
        old = Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_tiff'),
        ])
        old.unlink()
        Attachment.create({
            'name': filename,
            'res_model': self._name,
            'res_id': self.id,
            'res_field': 'layout_tiff',
            'type': 'binary',
            'raw': raw,
            'mimetype': 'image/tiff',
        })
        self.invalidate_recordset(['layout_tiff'])

        updates = {
            'layout_tiff_filename': filename,
            'layout_bleed_width': info['bleed_width'],
            'layout_bleed_height': info['bleed_height'],
            'layout_tiff_colorspace': info.get('colorspace') or False,
        }
        if info.get('preview'):
            updates['layout_tiff_preview'] = info['preview']
        else:
            updates['layout_tiff_preview'] = False
            _logger.warning(
                'line %s TIFF 預覽未產生%s',
                self.id,
                (': ' + info['preview_error']) if info.get('preview_error') else '',
            )
        models.Model.write(self, updates)

        preview = info.get('preview') or False
        if isinstance(preview, bytes):
            preview = preview.decode('ascii')

        return {
            'ok': True,
            'filename': filename,
            'bleed_width': updates.get('layout_bleed_width'),
            'bleed_height': updates.get('layout_bleed_height'),
            'colorspace': updates.get('layout_tiff_colorspace') or '',
            'preview': preview,
            'has_preview': bool(preview),
            'preview_error': info.get('preview_error') or '',
            'tiff_size': human_size(len(raw)),
        }

    def clear_layout_tiff(self):
        """清除 TIFF 附件與預覽（不經 Binary onchange）。"""
        Attachment = self.env['ir.attachment']
        for rec in self:
            Attachment.search([
                ('res_model', '=', rec._name),
                ('res_id', '=', rec.id),
                ('res_field', '=', 'layout_tiff'),
            ]).unlink()
            models.Model.write(rec, {
                'layout_tiff_filename': False,
                'layout_tiff_preview': False,
                'layout_tiff_colorspace': False,
            })
            rec.invalidate_recordset(['layout_tiff'])
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._validate_layout_tiff_filename(vals.get('layout_tiff_filename'))
            self._apply_layout_tiff_vals(vals)
            if not vals.get('layout_bleed_width'):
                vals['layout_bleed_width'] = vals.get('product_width') or '1'
            if not vals.get('layout_bleed_height'):
                vals['layout_bleed_height'] = vals.get('product_height') or '1'
        # 有 layout_tiff 時禁止圖片自動縮圖（否則 TIFF→JPEG 毀檔）
        create_self = self
        if any(v.get('layout_tiff') for v in vals_list):
            create_self = self.with_context(image_no_postprocess=True)
        return super(CheckOutLineLayout, create_self).create(vals_list)

    def write(self, vals):
        vals = dict(vals)
        if 'layout_tiff_filename' in vals:
            self._validate_layout_tiff_filename(vals.get('layout_tiff_filename'))
        if 'layout_tiff' in vals:
            # 清除
            if not vals.get('layout_tiff'):
                vals['layout_tiff_preview'] = False
                vals['layout_tiff_colorspace'] = False
            else:
                self._apply_layout_tiff_vals(vals)

        keys = set(vals) - {'__last_update'}
        layout_only = bool(keys) and keys <= self._LAYOUT_ONLY_FIELDS

        # 出血尺寸為空時，跟隨產品寬高預填（不覆蓋已手動填寫的值）
        sync_w = 'product_width' in vals and 'layout_bleed_width' not in vals
        sync_h = 'product_height' in vals and 'layout_bleed_height' not in vals

        bleed_touched = bool({'layout_bleed_width', 'layout_bleed_height'} & keys)

        write_self = self
        if vals.get('layout_tiff'):
            # 避免 Odoo 把印刷 TIFF 自動壓成 1920 JPEG
            write_self = self.with_context(image_no_postprocess=True)

        if layout_only:
            # 繞過 dtsc.checkoutline.write 的應收/出貨鎖（功能全在本模組）
            res = models.Model.write(write_self, vals)
        else:
            res = super(CheckOutLineLayout, write_self).write(vals)

        if sync_w or sync_h:
            for rec in self:
                updates = {}
                if sync_w and not (rec.layout_bleed_width or '').strip():
                    updates['layout_bleed_width'] = vals.get('product_width') or rec.product_width
                if sync_h and not (rec.layout_bleed_height or '').strip():
                    updates['layout_bleed_height'] = vals.get('product_height') or rec.product_height
                if updates:
                    models.Model.write(rec, updates)
                    bleed_touched = True

        if bleed_touched:
            self._sync_print_nesting_size_from_bleed()
        return res

    def _sync_print_nesting_size_from_bleed(self):
        """出血尺寸變更後，同步未印刷的印刷單圖塊尺寸並標記需重排。"""
        MakeInLine = self.env['dtsc.makeinline']
        OrderLine = self.env['dtsc.print.order.line']
        orders = self.env['dtsc.print.order']
        for cl in self:
            mls = MakeInLine.search([('checkout_line_id', '=', cl.id)])
            for ml in mls:
                w, h = ml._parse_size_cm()
                if not w or not h:
                    continue
                lines = OrderLine.search([
                    ('makeinline_id', '=', ml.id),
                    ('order_id.state', 'not in', ('done', 'cancel')),
                ])
                for line in lines:
                    printed = line.piece_ids.filtered(lambda p: p.lock_state == 'printed')
                    if printed:
                        continue
                    line.piece_w_mm = w
                    line.piece_h_mm = h
                    orders |= line.order_id
        if orders:
            orders.write({'need_renest': True})

    @api.model
    def _validate_layout_tiff_filename(self, filename):
        if not filename:
            return
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ('.tif', '.tiff'):
            raise UserError(_('自動排版僅允許上傳 TIFF 圖檔（.tif / .tiff），目前檔名：%s') % filename)
