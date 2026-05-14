# -*- coding: utf-8 -*-
{
    'name': 'DTS-C AI Gateway',
    'summary': 'Reusable AI gateway for Odoo assistants',
    'description': 'Reusable LangChain-ready AI gateway layer for DTS-C Odoo modules.',
    'author': '大圖輸出',
    'website': 'https://www.dtsc.com',
    'category': 'Technical',
    'version': '16.0.1.0.0',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'views/ai_gateway_log_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

