# -*- coding: utf-8 -*-
{
    'name': 'DTSC 印刷單捲材排版',
    'version': '16.0.1.6.0',
    'category': 'Manufacturing',
    'summary': '印刷池可視化排版：舊料優先、新料預留、截斷鎖定成印刷單',
    'description': """
大圖轉工單後，捲材項次進入印刷池。
左側選材料，右側長條可視化（舊料優先 + 新料預留），截斷鎖定生成印刷單。
產品規格：寬度(cm)、長度(m)。
    """,
    'author': '大圖輸出',
    'depends': ['dtsc', 'stock', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'views/product_template_views.xml',
        'views/makeinline_views.xml',
        'views/print_roll_views.xml',
        'views/print_order_views.xml',
        'views/stock_lot_views.xml',
        'views/print_pool_views.xml',
        'wizard/create_print_order_wizard_views.xml',
        'report/report_print_order.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dtsc_print_nesting/static/src/css/print_nesting.css',
            'dtsc_print_nesting/static/src/xml/print_pool.xml',
            'dtsc_print_nesting/static/src/js/print_pool.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
