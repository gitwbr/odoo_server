# -*- coding: utf-8 -*-
{
    'name': 'DTSC 印刷單捲材排版',
    'version': '16.0.1.24.2',
    'category': 'Manufacturing',
    'summary': '印刷池可視化排版：舊料優先、新料預留、截斷鎖定成印刷單',
    'description': """
大圖訂單「自動排版」標籤：內部工單捲料項次上傳 TIFF、維護出血後尺寸；
功能開啟時，訂單確認轉工單前強制檢查。
大圖轉工單後，捲材項次進入印刷池。
左側選材料，右側長條可視化（舊料優先 + 新料預留），截斷鎖定生成印刷單；
並依排版座標合成整版 TIFF（含留白）掛在捲料上供下載印刷。
產品規格：寬度(cm)、長度(m)。
    """,
    'author': '大圖輸出',
    'depends': ['dtsc', 'stock', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/layout_tiff_check_data.xml',
        'views/product_template_views.xml',
        'views/product_template_make_ori_views.xml',
        'views/makeinline_views.xml',
        'views/checkout_layout_views.xml',
        'views/print_roll_views.xml',
        'views/print_order_views.xml',
        'views/stock_lot_views.xml',
        'views/lotmpr_views.xml',
        'views/print_pool_views.xml',
        'wizard/create_print_order_wizard_views.xml',
        'report/report_print_order.xml',
        'views/res_config_settings_views.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dtsc_print_nesting/static/src/css/print_nesting.css',
            'dtsc_print_nesting/static/src/xml/print_pool.xml',
            'dtsc_print_nesting/static/src/xml/layout_tiff_upload.xml',
            'dtsc_print_nesting/static/src/xml/compose_progress.xml',
            'dtsc_print_nesting/static/src/js/print_pool.js',
            'dtsc_print_nesting/static/src/js/layout_tiff_upload.js',
            'dtsc_print_nesting/static/src/js/download_url_action.js',
            'dtsc_print_nesting/static/src/js/compose_progress_action.js',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'external_dependencies': {
        'python': ['PIL'],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
