# -*- coding: utf-8 -*-

from odoo import fields, models


class AiGatewayLog(models.Model):
    _name = 'dtsc.ai.gateway.log'
    _description = 'AI Gateway Log'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='摘要', readonly=True)
    user_id = fields.Many2one('res.users', string='使用者', readonly=True)
    partner_id = fields.Many2one('res.partner', string='會員/客戶', readonly=True)
    provider = fields.Char(string='Provider', readonly=True)
    model_name = fields.Char(string='模型', readonly=True)
    status = fields.Selection([
        ('success', '成功'),
        ('local_only', '本地查詢'),
        ('configuration_missing', '配置缺失'),
        ('missing_dependency', '缺少依賴'),
        ('error', '錯誤'),
    ], string='狀態', readonly=True)
    request_text = fields.Text(string='請求', readonly=True)
    response_text = fields.Text(string='回覆', readonly=True)
    tool_names = fields.Char(string='工具', readonly=True)
    duration_ms = fields.Integer(string='耗時(ms)', readonly=True)
    error_message = fields.Text(string='錯誤', readonly=True)

