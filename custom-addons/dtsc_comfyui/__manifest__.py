# -*- coding: utf-8 -*-
{
    'name': 'AI 出圖',
    'summary': '文生圖 / 圖生圖，調用本機 ComfyUI',
    'description': '獨立出圖工作台：文生圖與圖生圖兩個頁籤，後端調用 Windows ComfyUI 工作流。',
    'author': '大圖輸出',
    'website': 'https://www.dtsc.com',
    'category': 'Productivity',
    'version': '16.0.1.0.11',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/studio_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dtsc_comfyui/static/src/xml/live_status.xml',
            'dtsc_comfyui/static/src/js/poll_action.js',
            'dtsc_comfyui/static/src/css/studio.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
