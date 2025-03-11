{
    'name': 'dtsc_custom',
    'version': '16.0.1.0.0',
    'category': 'Custom',
    'summary': '客戶端特定的定制功能',
    'description': """
        此模組包含特定客戶端的定制功能：
        * 菜單定制
        * 視圖定制
        * 功能定制
    """,
    'author': '大圖輸出',
    'depends': ['base', 'dtsc'],
    'data': [
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
} 