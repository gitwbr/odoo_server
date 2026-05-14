# -*- coding: utf-8 -*-
{
    'name': 'DTS-C AI Assistant',
    'summary': 'Odoo business assistant for DTS-C queries',
    'description': 'Odoo 16 Enterprise AI assistant business layer using DTS-C AI Gateway.',
    'author': '大圖輸出',
    'website': 'https://www.dtsc.com',
    'category': 'Productivity',
    'version': '16.0.1.0.0',
    'depends': ['base', 'web', 'website', 'dtsc', 'dtsc_ai_gateway'],
    'data': [
        'security/ir.model.access.csv',
        'views/ai_assistant_templates.xml',
        'views/ai_assistant_settings_views.xml',
        'views/ai_assistant_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dtsc_ai_assistant/static/src/js/ai_assistant.js',
            'dtsc_ai_assistant/static/src/css/ai_assistant.css',
        ],
        'web.assets_frontend': [
            'dtsc_ai_assistant/static/src/js/ai_assistant.js',
            'dtsc_ai_assistant/static/src/css/ai_assistant.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
