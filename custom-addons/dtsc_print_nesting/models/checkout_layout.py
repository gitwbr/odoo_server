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
# 上傳後統一轉成印刷 TIFF 再進印刷池
_LAYOUT_SOURCE_EXTS = (
    '.tif', '.tiff',
    '.jpg', '.jpeg',
    '.png',
    '.pdf', '.ai',
)
_LAYOUT_RASTER_EXTS = ('.jpg', '.jpeg', '.png')
_LAYOUT_VECTOR_EXTS = ('.pdf', '.ai')
_LAYOUT_FALLBACK_DPI = 150.0


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
                    _('自動排版：以下內部工單捲料項次尚未上傳印刷圖檔，無法轉工單。'
                      '請至「自動排版」上傳 TIFF／PDF／AI／JPG／PNG（會自動轉成印刷 TIFF）後再確認：%s')
                    % seqs
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
        'layout_tiff_preview', 'layout_tiff_colorspace',
        'layout_source_pdf', 'layout_source_pdf_filename', 'layout_pass_count',
        'layout_ai', 'layout_ai_filename',
        'layout_ai_pdf_compatible', 'layout_ai_page_count',
        'layout_ai_width_cm', 'layout_ai_height_cm', 'layout_ai_message',
        'layout_prepress_state', 'layout_prepress_message',
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
    layout_tiff_filename = fields.Char(string='印刷圖檔', copy=False)
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
    # 多面打印：保留上傳的完整 PDF／相容 AI，供印刷單按遍數整合导出
    layout_source_pdf = fields.Binary(
        string='多面源 PDF', attachment=True, copy=False,
    )
    layout_source_pdf_filename = fields.Char(string='多面源檔名', copy=False)
    layout_pass_count = fields.Integer(
        string='打印遍數', default=1, copy=False,
        help='源 PDF 頁數。>1 時可選多面打印，印刷池仍只顯示一塊。',
    )

    # ---- AI 來源檔（印前處理後寫入 layout_tiff；也可不經 AI 直接上傳 TIFF）----
    layout_ai = fields.Binary(string='排版 AI', attachment=True, copy=False)
    layout_ai_filename = fields.Char(string='AI 檔名', copy=False)
    layout_ai_pdf_compatible = fields.Boolean(
        string='PDF 相容', copy=False, readonly=True,
        help='是否含 PDF 相容內容，可被伺服器直接轉 TIFF。',
    )
    layout_ai_page_count = fields.Integer(string='AI 頁數', copy=False, readonly=True)
    layout_ai_width_cm = fields.Char(string='AI 寬(cm)', copy=False, readonly=True)
    layout_ai_height_cm = fields.Char(string='AI 高(cm)', copy=False, readonly=True)
    layout_ai_message = fields.Char(string='AI 檢查訊息', copy=False, readonly=True)
    layout_prepress_state = fields.Selection(
        [
            ('none', '未處理'),
            ('ready', '可處理'),
            ('done', '已生成 TIFF'),
            ('error', '失敗'),
        ],
        string='印前狀態',
        default='none',
        copy=False,
        readonly=True,
    )
    layout_prepress_message = fields.Char(string='印前訊息', copy=False, readonly=True)

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

    def onchange(self, values, field_name, field_onchange):
        # 不可加 @api.model：Odoo 前端 onchange 會帶 ids，由 _call_kw_multi 解析
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

    def _store_layout_tiff_raw(self, raw, filename, need_preview=True):
        """multipart 上傳任意支援圖檔 → 統一轉印刷 TIFF → 寫入 filestore／尺寸／預覽。

        先轉換與解析再落盤：失敗時不會清掉舊檔或留下半成品附件。
        need_preview=False 對應印前「不拍縮圖」。
        """
        self.ensure_one()
        converted = self._convert_upload_to_print_tiff(raw, filename)
        tiff_raw = converted['tiff_bytes']
        store_name = converted['store_filename']

        # 先解析（失敗直接拋錯；預覽失敗不阻斷上傳）
        info = self._process_layout_tiff(
            tiff_raw,
            need_size=True,
            need_preview=bool(need_preview),
        )
        if not info.get('bleed_width') or not info.get('bleed_height'):
            # 轉換階段已盡力寫入 DPI；仍失敗則用轉換 meta／訂單尺寸補
            bw, bh = converted.get('bleed_width'), converted.get('bleed_height')
            if bw and bh:
                info['bleed_width'] = bw
                info['bleed_height'] = bh
            else:
                raise UserError(_('無法取得出血後尺寸，請確認檔案含 DPI，或先填寫產品寬高。'))

        # 必須跳過 base.image_autoresize：否則 TIFF 會被壓成 ≤1920 JPEG，印刷檔毀損
        Attachment = self.env['ir.attachment'].with_context(image_no_postprocess=True)
        old = Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_tiff'),
        ])
        old.unlink()
        Attachment.create({
            'name': store_name,
            'res_model': self._name,
            'res_id': self.id,
            'res_field': 'layout_tiff',
            'type': 'binary',
            'raw': tiff_raw,
            'mimetype': 'image/tiff',
        })
        self.invalidate_recordset(['layout_tiff'])

        updates = {
            'layout_tiff_filename': store_name,
            'layout_bleed_width': info['bleed_width'],
            'layout_bleed_height': info['bleed_height'],
            'layout_tiff_colorspace': info.get('colorspace') or False,
            'layout_pass_count': int(converted.get('pass_count') or 1) or 1,
        }
        if info.get('preview'):
            updates['layout_tiff_preview'] = info['preview']
        else:
            updates['layout_tiff_preview'] = False
            if need_preview:
                _logger.warning(
                    'line %s TIFF 預覽未產生%s',
                    self.id,
                    (': ' + info['preview_error']) if info.get('preview_error') else '',
                )
        models.Model.write(self, updates)

        # 多面源：保留完整 PDF／相容 AI，供多面印刷單按遍數整合
        src_ext = self._layout_source_ext(filename)
        if src_ext in _LAYOUT_VECTOR_EXTS and converted.get('pass_count', 1) >= 1:
            self._store_layout_source_pdf_raw(raw, filename)
        else:
            self._clear_layout_source_pdf()

        preview = info.get('preview') or False
        if isinstance(preview, bytes):
            preview = preview.decode('ascii')

        return {
            'ok': True,
            'filename': store_name,
            'source_filename': filename,
            'converted': converted.get('converted', False),
            'convert_note': converted.get('note') or '',
            'pass_count': updates['layout_pass_count'],
            'bleed_width': updates.get('layout_bleed_width'),
            'bleed_height': updates.get('layout_bleed_height'),
            'colorspace': updates.get('layout_tiff_colorspace') or '',
            'preview': preview,
            'has_preview': bool(preview),
            'preview_error': info.get('preview_error') or '',
            'tiff_size': human_size(len(tiff_raw)),
        }

    # ------------------------------------------------------------------
    # 多格式 → 印刷 TIFF
    # ------------------------------------------------------------------
    @api.model
    def _layout_source_ext(self, filename):
        return os.path.splitext(filename or '')[1].lower()

    @api.model
    def _layout_store_tiff_name(self, filename):
        stem = os.path.splitext(filename or 'upload')[0] or 'upload'
        return '%s.tif' % stem

    def _line_fallback_size_cm(self):
        """無 DPI 時：優先已填出血，其次產品寬高。"""
        self.ensure_one()

        def _to_float(val):
            try:
                return float(str(val).strip().replace(',', '.'))
            except (TypeError, ValueError):
                return 0.0

        w = _to_float(self.layout_bleed_width) or _to_float(self.product_width)
        h = _to_float(self.layout_bleed_height) or _to_float(self.product_height)
        return w, h

    def _convert_upload_to_print_tiff(self, raw, filename):
        """任意支援格式 → CMYK(或原樣) 印刷 TIFF bytes。

        :return: dict tiff_bytes / store_filename / converted / note / bleed_*
        """
        self.ensure_one()
        if not raw:
            raise UserError(_('檔案內容為空。'))
        ext = self._layout_source_ext(filename)
        if ext not in _LAYOUT_SOURCE_EXTS:
            raise UserError(_(
                '不支援的檔案類型「%s」。請上傳 TIFF／PDF／AI／JPG／PNG。'
            ) % (filename or ext or '?'))

        store_name = self._layout_store_tiff_name(filename)
        if ext in ('.tif', '.tiff'):
            self._assert_raw_is_tiff(raw)
            return {
                'tiff_bytes': raw,
                'store_filename': filename if ext in ('.tif', '.tiff') else store_name,
                'converted': False,
                'note': '',
                'pass_count': 1,
            }

        if ext in _LAYOUT_RASTER_EXTS:
            return self._convert_raster_to_print_tiff(raw, filename, store_name)

        if ext in _LAYOUT_VECTOR_EXTS:
            return self._convert_vector_to_print_tiff(raw, filename, store_name)

        raise UserError(_('不支援的檔案類型「%s」。') % filename)

    def _read_raster_dpi(self, img):
        """從 Pillow 圖讀 DPI；讀不到回 None。"""
        dpi_info = img.info.get('dpi') or ()
        if len(dpi_info) >= 1 and dpi_info[0]:
            try:
                val = float(dpi_info[0])
                if val > 1:
                    return val
            except (TypeError, ValueError):
                pass
        # JPEG EXIF resolution
        try:
            exif = img.getexif()
            if exif:
                # 282=XResolution, 283=YResolution, 296=ResolutionUnit
                xres = exif.get(282)
                unit = exif.get(296) or 2
                if xres:
                    num = float(xres[0]) if isinstance(xres, tuple) else float(xres)
                    den = float(xres[1]) if isinstance(xres, tuple) and len(xres) > 1 else 1.0
                    val = num / (den or 1.0)
                    if unit == 3:  # cm
                        val = val * 2.54
                    if val > 1:
                        return val
        except Exception:
            pass
        return None

    def _pil_image_to_cmyk(self, img):
        """位圖轉 CMYK；透明貼白底。"""
        if Image is None:
            raise UserError(_('伺服器未安裝 Pillow，無法處理圖檔。'))
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
        return img.convert('CMYK')

    def _convert_raster_to_print_tiff(self, raw, filename, store_name):
        if Image is None:
            raise UserError(_('伺服器未安裝 Pillow，無法處理 JPG／PNG。'))
        notes = []
        try:
            img = Image.open(BytesIO(raw))
            img.load()
        except Exception as err:
            raise UserError(_('無法開啟圖檔「%s」：%s') % (filename, err)) from err

        width_px, height_px = img.size
        if width_px <= 0 or height_px <= 0:
            raise UserError(_('圖檔「%s」尺寸無效。') % filename)

        dpi = self._read_raster_dpi(img)
        bleed_w = bleed_h = None
        if dpi:
            bleed_w = self._format_layout_cm((width_px / dpi) * 2.54)
            bleed_h = self._format_layout_cm((height_px / dpi) * 2.54)
            notes.append(_('依檔案 DPI %.0f 換算尺寸') % dpi)
        else:
            fw, fh = self._line_fallback_size_cm()
            if fw > 0 and fh > 0:
                # 用訂單／出血尺寸反推 DPI（取寬向）
                dpi = width_px / (fw / 2.54)
                bleed_w = self._format_layout_cm(fw)
                bleed_h = self._format_layout_cm(fh)
                notes.append(_('檔案無 DPI，依產品／出血尺寸 %s×%s cm 反推') % (bleed_w, bleed_h))
            else:
                dpi = _LAYOUT_FALLBACK_DPI
                bleed_w = self._format_layout_cm((width_px / dpi) * 2.54)
                bleed_h = self._format_layout_cm((height_px / dpi) * 2.54)
                notes.append(_(
                    '檔案無 DPI 且無產品寬高，暫用 DPI %.0f 估算尺寸；請核對出血後寬高'
                ) % dpi)

        try:
            cmyk = self._pil_image_to_cmyk(img)
            buf = BytesIO()
            cmyk.save(
                buf,
                format='TIFF',
                compression='tiff_lzw',
                dpi=(dpi, dpi),
            )
            tiff_bytes = buf.getvalue()
        except Exception as err:
            raise UserError(_('JPG／PNG 轉 TIFF 失敗：%s') % err) from err
        finally:
            try:
                img.close()
            except Exception:
                pass

        return {
            'tiff_bytes': tiff_bytes,
            'store_filename': store_name,
            'converted': True,
            'note': '；'.join(str(n) for n in notes),
            'bleed_width': bleed_w,
            'bleed_height': bleed_h,
            'pass_count': 1,
        }

    def _convert_vector_to_print_tiff(self, raw, filename, store_name):
        from odoo.addons.dtsc_print_nesting.utils import ai_to_tiff

        info = ai_to_tiff.inspect_ai_bytes(raw)
        if not info.pdf_compatible:
            raise UserError(_(
                '「%s」不是 PDF 相容檔，伺服器無法直接轉 TIFF。'
                '請另存為 PDF，或在 Illustrator 勾選「建立 PDF 相容檔」後再上傳。\n%s'
            ) % (filename, info.message or ''))
        try:
            tiff_bytes, meta = ai_to_tiff.convert_ai_to_tiff_bytes(raw)
        except Exception as err:
            _logger.exception('vector to tiff failed: %s', filename)
            raise UserError(_('PDF／AI 轉 TIFF 失敗：%s') % err) from err

        bleed_w = self._format_layout_cm(meta.get('width_cm') or 0) if meta.get('width_cm') else False
        bleed_h = self._format_layout_cm(meta.get('height_cm') or 0) if meta.get('height_cm') else False
        pass_count = max(int(info.page_count or 1), 1)
        note = _('已由 PDF／AI 轉成 CMYK TIFF（DPI %.0f）') % (meta.get('dpi') or 0)
        if pass_count > 1:
            note = note + _(
                '；檔案共 %s 頁（印刷池顯示第 1 面；多面打印時按遍數整合导出）'
            ) % pass_count
        return {
            'tiff_bytes': tiff_bytes,
            'store_filename': store_name,
            'converted': True,
            'note': note,
            'bleed_width': bleed_w,
            'bleed_height': bleed_h,
            'pass_count': pass_count,
        }

    def _has_layout_source_pdf(self):
        self.ensure_one()
        if self.layout_source_pdf_filename:
            return True
        return bool(self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_source_pdf'),
            ('file_size', '>', 0),
        ], limit=1))

    def _read_layout_source_pdf_raw(self):
        self.ensure_one()
        att = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_source_pdf'),
        ], limit=1)
        if not att or not att.raw:
            raise UserError(_('項次缺少多面源 PDF，無法做多面整合。'))
        return att.raw

    def _store_layout_source_pdf_raw(self, raw, filename):
        self.ensure_one()
        Attachment = self.env['ir.attachment'].with_context(image_no_postprocess=True)
        old = Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_source_pdf'),
        ])
        old.unlink()
        ext = self._layout_source_ext(filename)
        mimetype = 'application/pdf' if ext == '.pdf' else 'application/postscript'
        Attachment.create({
            'name': filename,
            'res_model': self._name,
            'res_id': self.id,
            'res_field': 'layout_source_pdf',
            'type': 'binary',
            'raw': raw,
            'mimetype': mimetype,
        })
        self.invalidate_recordset(['layout_source_pdf'])
        models.Model.write(self, {
            'layout_source_pdf_filename': filename,
        })

    def _clear_layout_source_pdf(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            Attachment.search([
                ('res_model', '=', rec._name),
                ('res_id', '=', rec.id),
                ('res_field', '=', 'layout_source_pdf'),
            ]).unlink()
            models.Model.write(rec, {
                'layout_source_pdf_filename': False,
                'layout_pass_count': 1,
            })
            rec.invalidate_recordset(['layout_source_pdf'])

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
            rec._clear_layout_source_pdf()
        return True

    # ------------------------------------------------------------------
    # AI 來源檔
    # ------------------------------------------------------------------
    def _has_layout_ai_file(self):
        self.ensure_one()
        if self.layout_ai_filename:
            return True
        return bool(self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_ai'),
            ('file_size', '>', 0),
        ], limit=1))

    def _read_layout_ai_raw(self):
        """讀取 AI/PDF 原位元組（不經 base64 膨脹）。"""
        self.ensure_one()
        att = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_ai'),
        ], limit=1)
        if not att:
            raise UserError(_('尚未上傳 AI / PDF 檔案。'))
        raw = att.raw
        if not raw:
            raise UserError(_('AI 檔案內容為空。'))
        return raw

    @api.model
    def _validate_layout_ai_filename(self, filename):
        if not filename:
            return
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ('.ai', '.pdf'):
            raise UserError(
                _('印前處理僅允許上傳 AI / PDF（.ai / .pdf），目前檔名：%s') % filename
            )

    def _store_layout_ai_raw(self, raw, filename):
        """multipart 寫入 AI/PDF，並檢查 PDF 相容性。"""
        self.ensure_one()
        self._validate_layout_ai_filename(filename)
        if not raw:
            raise UserError(_('檔案內容為空。'))

        from odoo.addons.dtsc_print_nesting.utils import ai_to_tiff
        info = ai_to_tiff.inspect_ai_bytes(raw)

        Attachment = self.env['ir.attachment'].with_context(image_no_postprocess=True)
        old = Attachment.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_ai'),
        ])
        old.unlink()
        ext = os.path.splitext(filename)[1].lower()
        mimetype = 'application/pdf' if ext == '.pdf' else 'application/postscript'
        Attachment.create({
            'name': filename,
            'res_model': self._name,
            'res_id': self.id,
            'res_field': 'layout_ai',
            'type': 'binary',
            'raw': raw,
            'mimetype': mimetype,
        })
        self.invalidate_recordset(['layout_ai'])

        updates = {
            'layout_ai_filename': filename,
            'layout_ai_pdf_compatible': bool(info.pdf_compatible),
            'layout_ai_page_count': info.page_count or 0,
            'layout_ai_width_cm': self._format_layout_cm(info.width_cm) if info.width_cm else False,
            'layout_ai_height_cm': self._format_layout_cm(info.height_cm) if info.height_cm else False,
            'layout_ai_message': info.message or False,
            'layout_prepress_state': 'ready' if info.pdf_compatible else 'error',
            'layout_prepress_message': info.message or False,
        }
        models.Model.write(self, updates)
        return {
            'ok': True,
            'filename': filename,
            'pdf_compatible': bool(info.pdf_compatible),
            'page_count': info.page_count or 0,
            'width_cm': updates.get('layout_ai_width_cm') or '',
            'height_cm': updates.get('layout_ai_height_cm') or '',
            'message': info.message or '',
            'prepress_state': updates['layout_prepress_state'],
            'ai_size': human_size(len(raw)),
        }

    def clear_layout_ai(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            Attachment.search([
                ('res_model', '=', rec._name),
                ('res_id', '=', rec.id),
                ('res_field', '=', 'layout_ai'),
            ]).unlink()
            models.Model.write(rec, {
                'layout_ai_filename': False,
                'layout_ai_pdf_compatible': False,
                'layout_ai_page_count': 0,
                'layout_ai_width_cm': False,
                'layout_ai_height_cm': False,
                'layout_ai_message': False,
                'layout_prepress_state': 'none',
                'layout_prepress_message': False,
            })
            rec.invalidate_recordset(['layout_ai'])
        return True

    def action_open_prepress_wizard(self):
        """打開印前處理選項視窗（先建立 wizard 再開，避免前端載入失敗）。"""
        self.ensure_one()
        if not self._has_layout_ai_file():
            raise UserError(_('請先上傳 AI / PDF 檔案。'))
        wiz = self.env['dtsc.prepress.wizard'].with_context(
            default_line_id=self.id,
            active_id=self.id,
            active_model=self._name,
        ).create({'line_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('印前處理'),
            'res_model': 'dtsc.prepress.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_line_id': self.id,
                'active_id': self.id,
                'active_model': self._name,
            },
        }

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
        """相容舊呼叫：現改為允許多格式來源（最終仍存印刷 TIFF）。"""
        if not filename:
            return
        ext = os.path.splitext(filename)[1].lower()
        if ext not in _LAYOUT_SOURCE_EXTS:
            raise UserError(_(
                '自動排版僅允許上傳 TIFF／PDF／AI／JPG／PNG，目前檔名：%s'
            ) % filename)
