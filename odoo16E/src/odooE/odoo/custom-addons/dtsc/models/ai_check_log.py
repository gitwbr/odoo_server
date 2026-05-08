# -*- coding: utf-8 -*-

from odoo import fields, models


class AiCheckLog(models.Model):
    _name = 'dtsc.ai.check.log'
    _description = 'AI 檢測日誌'
    _order = 'create_date desc, id desc'

    user_id = fields.Many2one('res.users', string='使用者', readonly=True)
    partner_id = fields.Many2one('res.partner', string='會員', readonly=True)
    website_id = fields.Many2one('website', string='網站', readonly=True)
    customer_name = fields.Char(string='頁面名稱', readonly=True)
    original_filename = fields.Char(string='原始檔名', readonly=True)
    checked_filename = fields.Char(string='檢測檔名', readonly=True)
    input_width = fields.Char(string='輸入寬度', readonly=True)
    input_height = fields.Char(string='輸入高度', readonly=True)
    actual_width_mm = fields.Float(string='實際寬度(mm)', readonly=True)
    actual_height_mm = fields.Float(string='實際高度(mm)', readonly=True)
    status = fields.Selection(
        [('success', '通過'), ('failed', '失敗')],
        string='結果',
        readonly=True,
    )
    message = fields.Text(string='訊息', readonly=True)
    ip_address = fields.Char(string='IP', readonly=True)
