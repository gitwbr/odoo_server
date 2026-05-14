# -*- coding: utf-8 -*-

from odoo import fields, models


class AiAssistantSession(models.Model):
    _name = 'dtsc.ai.assistant.session'
    _description = 'DTS-C AI Assistant Session'
    _order = 'create_date desc, id desc'

    name = fields.Char(string='摘要', readonly=True)
    user_id = fields.Many2one('res.users', string='使用者', readonly=True)
    partner_id = fields.Many2one('res.partner', string='客戶/會員', readonly=True)
    actor_type = fields.Char(string='身份類型', readonly=True)
    question = fields.Text(string='問題', readonly=True)
    answer = fields.Text(string='回答', readonly=True)
    status = fields.Selection([
        ('success', '成功'),
        ('no_data', '無資料'),
        ('configuration_missing', '缺少 AI 配置'),
        ('missing_dependency', '缺少 AI 套件'),
        ('error', '錯誤'),
    ], string='狀態', readonly=True)
    result_json = fields.Text(string='查詢資料', readonly=True)
    thread_id = fields.Many2one('dtsc.ai.assistant.thread', string='Thread', readonly=True)
    gateway_log_id = fields.Many2one('dtsc.ai.gateway.log', string='Gateway Log', readonly=True)
