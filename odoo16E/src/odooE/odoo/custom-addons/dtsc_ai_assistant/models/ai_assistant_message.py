# -*- coding: utf-8 -*-

from odoo import fields, models


class AiAssistantMessage(models.Model):
    _name = 'dtsc.ai.assistant.message'
    _description = 'DTS-C AI Assistant Message'
    _order = 'create_date asc, id asc'

    thread_id = fields.Many2one(
        'dtsc.ai.assistant.thread',
        string='Thread',
        required=True,
        ondelete='cascade',
        readonly=True,
    )
    role = fields.Selection([
        ('user', '使用者'),
        ('assistant', 'AI 助手'),
    ], string='角色', required=True, readonly=True)
    content = fields.Text(string='內容', readonly=True)
    result_json = fields.Text(string='查詢資料', readonly=True)
    gateway_log_id = fields.Many2one('dtsc.ai.gateway.log', string='Gateway Log', readonly=True)

    def serialize(self):
        self.ensure_one()
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content or '',
            'create_date': str(self.create_date or ''),
            'result_json': self.result_json or '',
            'gateway_log_id': self.gateway_log_id.id if self.gateway_log_id else False,
        }

