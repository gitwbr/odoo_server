# -*- coding: utf-8 -*-
import base64
import binascii
import json
import logging

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import Response, content_disposition, request

_logger = logging.getLogger(__name__)

ALLOWED_MIMETYPES = ('image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf')
MAX_FILE_BYTES = 10 * 1024 * 1024


class ExpenseController(http.Controller):

    def _json(self, **payload):
        return request.make_response(
            json.dumps(payload, ensure_ascii=False),
            headers=[('Content-Type', 'application/json; charset=utf-8')],
        )

    def _payload(self):
        try:
            return json.loads(request.httprequest.data or b'{}')
        except ValueError:
            return {}

    def _auth_worker(self, data):
        """以 LIFF ID Token 確認是本人，回傳 (員工, 錯誤訊息)。"""
        bot = request.env['dtsc.linebot'].sudo().search([('linebot_type', '=', 'for_worker')], limit=1)
        line_user_id = bot.verify_liff_id_token(data.get('id_token')) if bot else False
        if not line_user_id:
            return None, '身分驗證失敗，請關閉頁面後從 LINE 重新開啟'
        worker = request.env['dtsc.workqrcode'].sudo().search([('line_user_id', '=', line_user_id)], limit=1)
        if not worker:
            return None, '找不到您的綁定資料，請先在 LINE 輸入「綁定+員工姓名」'
        return worker, None

    def _approver_expense(self, data, worker):
        try:
            expense_id = int(data.get('expense_id') or 0)
        except (TypeError, ValueError):
            expense_id = 0
        expense = request.env['dtsc.expense'].sudo().browse(expense_id).exists()
        if not expense:
            return None, '找不到這張報支單'
        if not expense.is_approver(worker):
            return None, '您不是這張報支單的簽核人'
        return expense, None

    @http.route('/liff_app/api/expense/submit', type='http', auth='public', methods=['POST'], csrf=False)
    def expense_submit(self, **kw):
        data = self._payload()
        worker, error = self._auth_worker(data)
        if error:
            return self._json(success=False, message=error)
        if worker.out_company_date:
            return self._json(success=False, message='您已離職，無法申請報支')

        Expense = request.env['dtsc.expense'].sudo()
        category = data.get('category')
        if category not in dict(Expense.CATEGORY_SELECTION):
            return self._json(success=False, message='請選擇類別')
        try:
            amount = int(str(data.get('amount') or '').replace(',', ''))
        except ValueError:
            amount = 0
        if amount <= 0:
            return self._json(success=False, message='請輸入正確金額（整數）')
        try:
            expense_date = fields.Date.to_date(data.get('expense_date'))
        except ValueError:
            expense_date = None
        if not expense_date:
            return self._json(success=False, message='請選擇日期')

        files = data.get('files') or []
        if len(files) > Expense.MAX_ATTACHMENTS:
            return self._json(success=False, message=f'附件最多 {Expense.MAX_ATTACHMENTS} 個')
        attachment_vals = []
        for item in files:
            name = (item.get('name') or 'attachment').strip()
            mimetype = (item.get('type') or '').lower()
            if mimetype not in ALLOWED_MIMETYPES:
                return self._json(success=False, message=f'{name} 不是圖片或 PDF')
            try:
                raw = base64.b64decode(item.get('data') or '', validate=True)
            except (binascii.Error, ValueError):
                raw = b''
            if not raw:
                return self._json(success=False, message=f'{name} 讀取失敗，請重新選擇')
            if len(raw) > MAX_FILE_BYTES:
                return self._json(success=False, message=f'{name} 超過 10MB')
            attachment_vals.append({'name': name, 'raw': raw, 'mimetype': mimetype})

        expense = Expense.create({
            'employee_id': worker.id,
            'line_user_id': worker.line_user_id,
            'expense_date': expense_date,
            'category': category,
            'amount': amount,
            'description': (data.get('description') or '').strip(),
        })
        if attachment_vals:
            attachments = request.env['ir.attachment'].sudo().create([
                dict(vals, res_model='dtsc.expense', res_id=expense.id) for vals in attachment_vals
            ])
            expense.write({'attachment_ids': [(6, 0, attachments.ids)]})

        pushed = expense.notify_approvers(f"https://{request.httprequest.host}")
        if pushed:
            message = f'✅ 報支單 {expense.name} 已送出，等待主管簽核'
        else:
            message = f'報支單 {expense.name} 已送出，但找不到可通知的簽核主管，請聯絡管理員'
        return self._json(success=True, message=message, name=expense.name)

    @http.route('/liff_app/api/expense/list', type='http', auth='public', methods=['POST'], csrf=False)
    def expense_list(self, **kw):
        worker, error = self._auth_worker(self._payload())
        if error:
            return self._json(success=False, message=error)
        expenses = request.env['dtsc.expense'].sudo().search([('employee_id', '=', worker.id)], limit=20)
        rows = [{
            'name': e.name,
            'date': fields.Date.to_string(e.expense_date),
            'category': e._category_label(),
            'amount': e._amount_display(),
            'description': e.description or '',
            'state': e.state,
            'state_label': e._state_label(),
            'payment_method': e._payment_label(),
            'reject_reason': e.reject_reason or '',
        } for e in expenses]
        return self._json(success=True, data=rows)

    @http.route('/liff_app/api/expense/detail', type='http', auth='public', methods=['POST'], csrf=False)
    def expense_detail(self, **kw):
        data = self._payload()
        worker, error = self._auth_worker(data)
        if error:
            return self._json(success=False, message=error)
        expense, error = self._approver_expense(data, worker)
        if error:
            return self._json(success=False, message=error)
        return self._json(success=True, data={
            'name': expense.name,
            'employee': expense.employee_id.name,
            'date': fields.Date.to_string(expense.expense_date),
            'category': expense._category_label(),
            'amount': expense._amount_display(),
            'description': expense.description or '',
            'state': expense.state,
            'state_label': expense._state_label(),
        })

    @http.route('/liff_app/api/expense/reject', type='http', auth='public', methods=['POST'], csrf=False)
    def expense_reject(self, **kw):
        data = self._payload()
        worker, error = self._auth_worker(data)
        if error:
            return self._json(success=False, message=error)
        expense, error = self._approver_expense(data, worker)
        if error:
            return self._json(success=False, message=error)
        try:
            with request.env.cr.savepoint():
                expense.action_reject(data.get('reason'), worker)
        except UserError as e:
            return self._json(success=False, message=e.args[0])
        return self._json(success=True, message=f'已拒絕 {expense.employee_id.name} 的報支單 {expense.name}')

    def _check_view_access(self, expense_id, token):
        expense = request.env['dtsc.expense'].sudo().browse(expense_id).exists()
        if expense and expense._verify_view_token(token):
            return expense
        return None

    @http.route('/expense/view/<int:expense_id>', type='http', auth='public', methods=['GET'])
    def expense_view(self, expense_id, token=None, **kw):
        expense = self._check_view_access(expense_id, token)
        if not expense:
            return Response('連結無效或已過期', status=403, content_type='text/plain; charset=utf-8')
        rows = [
            ('申請人', expense.employee_id.name),
            ('日期', fields.Date.to_string(expense.expense_date)),
            ('類別', expense._category_label()),
            ('金額', expense._amount_display()),
            ('說明', expense.description or '（無）'),
            ('狀態', expense._state_label()),
        ]
        if expense.payment_method:
            rows.append(('付款方式', expense._payment_label()))
        if expense.approver_id:
            rows.append(('簽核人', expense.approver_id.name))
        if expense.reject_reason:
            rows.append(('拒絕理由', expense.reject_reason))
        files = [{
            'name': att.name,
            'url': f"/expense/file/{expense.id}/{att.id}?token={token}",
            'is_image': (att.mimetype or '').startswith('image/'),
        } for att in expense.attachment_ids]
        return request.render('dtsc.expense_view_page', {
            'title': f"報支單 {expense.name}",
            'rows': rows,
            'files': files,
        })

    @http.route('/expense/file/<int:expense_id>/<int:attachment_id>', type='http', auth='public', methods=['GET'])
    def expense_file(self, expense_id, attachment_id, token=None, **kw):
        expense = self._check_view_access(expense_id, token)
        if not expense:
            return Response('連結無效或已過期', status=403, content_type='text/plain; charset=utf-8')
        attachment = expense.attachment_ids.filtered(lambda a: a.id == attachment_id)
        if not attachment:
            return request.not_found()
        raw = attachment.raw or b''
        mimetype = attachment.mimetype if attachment.mimetype in ALLOWED_MIMETYPES else 'application/octet-stream'
        disposition = content_disposition(attachment.name)
        if mimetype != 'application/octet-stream':
            disposition = disposition.replace('attachment;', 'inline;', 1)
        return request.make_response(raw, headers=[
            ('Content-Type', mimetype),
            ('Content-Length', str(len(raw))),
            ('Content-Disposition', disposition),
            ('X-Content-Type-Options', 'nosniff'),
            ('Cache-Control', 'private, max-age=300'),
        ])
