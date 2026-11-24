# -*- coding: utf-8 -*-
{
    'name': 'DTSC 金流管理',
    'version': '16.0.1.3.0',
    'category': 'Accounting',
    'summary': '公司銀行帳戶、金流水帳、應收已收 / 應付已付、零用金劃撥',
    'description': """
獨立金流台帳模組（不走完整會計核銷）。
僅大圖「管理部」「會計」權限可使用。
金流看板為純查詢 Client Action，不建立暫存單據。
付款條款到期且未結清時，每日 LINE 推送給會計與管理部。
    """,
    'author': '大圖輸出',
    'depends': ['dtsc', 'account', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_cash_overdue.xml',
        'views/cash_bank_views.xml',
        'views/cash_transaction_views.xml',
        'views/cash_dashboard_views.xml',
        'views/account_move_views.xml',
        'views/pettycash_views.xml',
        'wizard/cash_settle_wizard_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dtsc_cashflow/static/src/js/cash_dashboard.js',
            'dtsc_cashflow/static/src/xml/cash_dashboard.xml',
            'dtsc_cashflow/static/src/css/cash_dashboard.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
