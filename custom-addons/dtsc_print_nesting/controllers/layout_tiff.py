# -*- coding: utf-8 -*-
import logging
import os

from odoo import http, _
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class LayoutTiffController(http.Controller):

    def _json_error(self, message):
        """錯誤回應前先 rollback，避免半成品附件被提交。"""
        try:
            request.env.cr.rollback()
        except Exception:
            pass
        return request.make_json_response({'error': message})

    @http.route(
        '/dtsc_print_nesting/layout_tiff/upload',
        type='http',
        auth='user',
        methods=['POST'],
        csrf=True,
    )
    def upload_layout_tiff(self, line_id=None, ufile=None, **kwargs):
        """multipart 上傳大 TIFF，避免前端 base64 + JSON.stringify 爆字串。"""
        try:
            line_id = int(line_id or 0)
            if not line_id:
                return self._json_error(_('缺少訂單行 ID，請先保存訂單。'))
            if not ufile:
                return self._json_error(_('未收到檔案。'))

            filename = ufile.filename or 'upload.tif'
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ('.tif', '.tiff'):
                return self._json_error(
                    _('僅允許上傳 TIFF（.tif / .tiff），目前檔名：%s') % filename
                )

            line = request.env['dtsc.checkoutline'].browse(line_id)
            if not line.exists():
                return self._json_error(_('訂單行不存在。'))
            line.check_access_rights('write')
            line.check_access_rule('write')

            raw = ufile.read()
            if not raw:
                return self._json_error(_('檔案內容為空。'))

            result = line._store_layout_tiff_raw(raw, filename)
            return request.make_json_response(result)
        except AccessError:
            return self._json_error(_('無權上傳此訂單行的 TIFF。'))
        except UserError as err:
            return self._json_error(err.args[0] if err.args else str(err))
        except Exception:
            _logger.exception('layout tiff upload failed')
            return self._json_error(_('上傳失敗，請稍後再試或聯絡管理員。'))

    @http.route(
        '/dtsc_print_nesting/layout_tiff/clear',
        type='json',
        auth='user',
    )
    def clear_layout_tiff(self, line_id=None):
        line = request.env['dtsc.checkoutline'].browse(int(line_id or 0))
        if not line.exists():
            return {'error': _('訂單行不存在。')}
        line.clear_layout_tiff()
        return {'ok': True}

    @http.route(
        '/dtsc_print_nesting/layout_ai/upload',
        type='http',
        auth='user',
        methods=['POST'],
        csrf=True,
    )
    def upload_layout_ai(self, line_id=None, ufile=None, **kwargs):
        """multipart 上傳 AI/PDF，並檢查 PDF 相容性。"""
        try:
            line_id = int(line_id or 0)
            if not line_id:
                return self._json_error(_('缺少訂單行 ID，請先保存訂單。'))
            if not ufile:
                return self._json_error(_('未收到檔案。'))

            filename = ufile.filename or 'upload.ai'
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ('.ai', '.pdf'):
                return self._json_error(
                    _('僅允許上傳 AI / PDF（.ai / .pdf），目前檔名：%s') % filename
                )

            line = request.env['dtsc.checkoutline'].browse(line_id)
            if not line.exists():
                return self._json_error(_('訂單行不存在。'))
            line.check_access_rights('write')
            line.check_access_rule('write')

            raw = ufile.read()
            if not raw:
                return self._json_error(_('檔案內容為空。'))

            result = line._store_layout_ai_raw(raw, filename)
            return request.make_json_response(result)
        except AccessError:
            return self._json_error(_('無權上傳此訂單行的 AI 檔。'))
        except UserError as err:
            return self._json_error(err.args[0] if err.args else str(err))
        except Exception:
            _logger.exception('layout ai upload failed')
            return self._json_error(_('上傳失敗，請稍後再試或聯絡管理員。'))

    @http.route(
        '/dtsc_print_nesting/layout_ai/clear',
        type='json',
        auth='user',
    )
    def clear_layout_ai(self, line_id=None):
        line = request.env['dtsc.checkoutline'].browse(int(line_id or 0))
        if not line.exists():
            return {'error': _('訂單行不存在。')}
        line.clear_layout_ai()
        return {'ok': True}
