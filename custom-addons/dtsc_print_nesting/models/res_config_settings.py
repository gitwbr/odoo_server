# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    enable_layout_tiff_check = fields.Boolean(
        string='轉工單強制檢查捲料 TIFF',
        config_parameter='dtsc_print_nesting.enable_layout_tiff_check',
        default=True,
        help='開啟後：訂單確認時，製作方式為內部工單/代工且原料為捲料的項次，'
             '必須已上傳 TIFF 並填寫出血後寬高，否則無法轉工單。',
    )
    print_pool_allow_rotate = fields.Boolean(
        string='印刷池允許90°旋轉排版',
        config_parameter='dtsc_print_nesting.print_pool_allow_rotate',
        default=True,
        help='印刷池自動排版時，是否允許圖塊橫豎互換以省料。預設開啟。',
    )
    print_pool_gap_cm = fields.Float(
        string='一般圖間距(cm)',
        config_parameter='dtsc_print_nesting.print_pool_gap_cm',
        default=0.5,
        help='印刷池排版時，同膜（或無膜差異）圖塊之間的最小間距。預設 0.5cm。',
    )
    print_pool_gap_diff_film_cm = fields.Float(
        string='異膜圖間距(cm)',
        config_parameter='dtsc_print_nesting.print_pool_gap_diff_film_cm',
        default=5.0,
        help='冷裱屬性不同（如亮膜與霧膜）的兩張圖之間最小間距。預設 5cm。',
    )
    print_pool_margin_cm = fields.Float(
        string='捲材邊距(cm)',
        config_parameter='dtsc_print_nesting.print_pool_margin_cm',
        default=0.0,
        help='印刷池排版時，捲材四邊（門幅兩側與起止方向）留白。0 表示貼邊不留空。',
    )
    print_cmyk_icc = fields.Binary(
        related='company_id.print_cmyk_icc', readonly=False,
    )
    print_cmyk_icc_filename = fields.Char(
        related='company_id.print_cmyk_icc_filename', readonly=False,
    )
    print_cmyk_intent = fields.Selection(
        [
            ('0', '感知（照片、漸層）'),
            ('1', '相對比色（純色、LOGO）'),
        ],
        string='RGB 轉 CMYK 意圖',
        config_parameter='dtsc_print_nesting.print_cmyk_intent',
        default='0',
    )
