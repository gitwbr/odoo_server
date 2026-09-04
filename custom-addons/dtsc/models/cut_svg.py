# -*- coding: utf-8 -*-
import base64
import logging
import threading

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules.registry import Registry

from odoo.addons.dtsc.utils.cut_svg import gpt_client, pipeline

_logger = logging.getLogger(__name__)


class CheckoutCutSvg(models.Model):
    _inherit = 'dtsc.checkout'

    # Same inverse as product_ids so both show the same lines, but keep a
    # separate field name so the notebook page does not override 產品清單 views.
    cut_svg_line_ids = fields.One2many(
        'dtsc.checkoutline',
        'checkout_product_id',
        string='刀模生成項次',
    )


class CheckOutLineCutSvg(models.Model):
    _inherit = 'dtsc.checkoutline'

    cut_source_image = fields.Binary(string='刀模參考圖', attachment=True)
    cut_svg_file = fields.Binary(string='刀模 SVG', attachment=True)
    cut_svg_filename = fields.Char(string='SVG 檔名')
    cut_svg_preview_html = fields.Html(string='刀模預覽', sanitize=False)
    cut_svg_json = fields.Text(string='刀模解析 JSON')
    cut_svg_gpt_raw = fields.Text(string='GPT 原始回覆', copy=False)
    cut_svg_debug = fields.Text(string='刀模調試資訊', copy=False)
    cut_svg_state = fields.Selection(
        [
            ('draft', '未生成'),
            ('pending', '生成中'),
            ('done', '已完成'),
            ('error', '失敗'),
        ],
        string='刀模狀態',
        default='draft',
        copy=False,
    )
    cut_svg_error = fields.Text(string='刀模錯誤', copy=False)
    cut_svg_generated_at = fields.Datetime(string='刀模生成時間', copy=False)
    cut_svg_mode = fields.Char(
        string='生成模式',
        copy=False,
        help='gpt / fallback / fallback_after_gpt_error / no_api_key',
    )
    cut_svg_model = fields.Char(string='使用模型', copy=False)

    def action_generate_cut_svg(self):
        """Queue cut-SVG generation in a background thread; return immediately."""
        self.ensure_one()
        if not self.cut_source_image:
            raise UserError(_('請先上傳刀模參考圖。'))

        api_key = gpt_client.get_api_key(self.env)
        # 先清空舊結果，避免畫面仍顯示上一次 SVG / JSON，誤以為沒有重跑
        self.write({
            'cut_svg_state': 'pending',
            'cut_svg_error': False,
            'cut_svg_preview_html': False,
            'cut_svg_file': False,
            'cut_svg_filename': False,
            'cut_svg_json': False,
            'cut_svg_gpt_raw': False,
            'cut_svg_debug': False,
            'cut_svg_mode': False,
            'cut_svg_model': False,
            'cut_svg_generated_at': False,
        })
        # Commit so UI can see pending/cleared state before the worker thread starts.
        self.env.cr.commit()

        db_name = self.env.cr.dbname
        uid = self.env.uid
        line_id = self.id
        ctx = dict(self.env.context)
        has_key = bool(api_key)

        def _run():
            try:
                registry = Registry(db_name)
                with registry.cursor() as cr:
                    env = api.Environment(cr, uid, ctx)
                    line = env['dtsc.checkoutline'].browse(line_id)
                    if not line.exists():
                        return
                    line._generate_cut_svg_job(use_gpt=has_key)
                    cr.commit()
            except Exception as exc:
                _logger.exception('cut svg thread failed line_id=%s', line_id)
                try:
                    registry = Registry(db_name)
                    with registry.cursor() as cr:
                        env = api.Environment(cr, uid, ctx)
                        line = env['dtsc.checkoutline'].browse(line_id)
                        if line.exists():
                            line.write({
                                'cut_svg_state': 'error',
                                'cut_svg_error': str(exc),
                            })
                            cr.commit()
                except Exception:
                    _logger.exception('cut svg failed to persist error state')

        threading.Thread(
            target=_run,
            name=f'dtsc-cut-svg-{line_id}',
            daemon=True,
        ).start()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('已重新開始生成'),
                'message': _('已清空舊結果，刀模生成中，頁面將重新整理。'),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                },
            },
        }

    def _build_cut_context(self):
        self.ensure_one()
        attrs = ', '.join(
            f'{att.attribute_id.name}:{att.name}'
            for att in self.product_atts
            if att.attribute_id and att.name
        )
        return {
            'filename': self.project_product_name or '',
            'width': self.product_width or '',
            'height': self.product_height or '',
            'aftermake': self.multi_chose_ids or '',
            'product_name': self.product_id.display_name if self.product_id else '',
            'attrs': attrs,
            'comment': self.comment or '',
        }

    def _generate_cut_svg_job(self, use_gpt=True):
        self.ensure_one()
        api_key = gpt_client.get_api_key(self.env) if use_gpt else None
        image_b64 = self.cut_source_image
        if isinstance(image_b64, bytes):
            image_b64 = image_b64.decode('ascii')
        context = self._build_cut_context()
        result = pipeline.run_pipeline(
            image_b64,
            context,
            api_key=api_key,
            use_gpt=bool(api_key),
        )
        svg_text = result['svg_text']
        filename = f"{(self.make_orderid or self.sequence or self.id)}_cut.svg"
        svg_preview = svg_text.replace(
            '<svg ',
            '<svg style="max-width:100%;height:auto;background:#fff;" ',
            1,
        )
        preview = (
            '<div style="max-width:100%;overflow:auto;border:1px solid #ddd;'
            'padding:8px;background:#fafafa;">'
            f'{svg_preview}'
            '</div>'
        )
        self.write({
            'cut_svg_file': base64.b64encode(svg_text.encode('utf-8')),
            'cut_svg_filename': filename,
            'cut_svg_preview_html': preview,
            'cut_svg_json': result['json_text'],
            'cut_svg_gpt_raw': result.get('gpt_raw') or '',
            'cut_svg_debug': result.get('debug_text') or '',
            'cut_svg_state': 'done',
            'cut_svg_error': result.get('gpt_error') or False,
            'cut_svg_generated_at': fields.Datetime.now(),
            'cut_svg_mode': result.get('mode') or '',
            'cut_svg_model': result.get('gpt_model') or '',
        })
