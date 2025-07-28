# -*- coding: utf-8 -*-
{
    'name': "dtsc",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

    'author': "大圖輸出",
    'website': "https://www.dtsc.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','base_import', 'product','mrp','web','sale','stock','website_sale','account','purchase','delivery','crm','note','hr_expense','hr_holidays','hr_attendance'],  # Add 'product' here
	'qweb': [ 
        'static/src/xml/res_partner.xml',
        'static/src/xml/chattemplate.xml',
    ],
	 'css': [
        'static/src/css/checkout.css',
    ],
    # always loaded
    'data': [
        'views/stock_lot.xml',
        'security/res_group.xml',
        'security/ir.model.access.csv',
		'views/product_attribute_value_views.xml',        
        'views/test.xml',
        'views/unit_conversion.xml',
        'views/templates.xml',
        'views/checkout.xml',
        'views/order.xml',
        'views/public_web_order.xml',
        'views/customclass.xml',
        'views/statement.xml',
        'views/res_partner_templates.xml',
        'views/machineprice.xml', 
        'views/make_type.xml', 
        'views/product_price_table.xml', 
        'views/product_price_calculator.xml', 
        'views/product_templates.xml',         
        'views/checkout_back.xml',
        'views/make_in.xml',
        'views/make_out.xml',
        'views/installproduct.xml',
        'views/report_makeout.xml',
        'views/report_makein.xml',
        'views/report_installproduct.xml',
        'views/report_stock_lot_barcodes.xml',
        'views/report_deliveryorder.xml',
        'views/stock.xml',        
        'views/work_list.xml',        
        'views/account_move.xml',        
        'views/deliveryorder.xml',        
        'views/report_invoice.xml',        
        'views/report_purchase_order.xml',        
        'views/remove_report.xml',        
        'views/purchase_order.xml',        
        'views/billinvoice.xml',        
        'views/store.xml',        
        'views/product_attribute_del.xml',        
        'views/checkoutreport.xml',        
        'views/sale_order.xml',    
        'views/report_stock_quant.xml',    
        'views/stock_quant.xml',    
        # 'data/spreadsheet.xml',         
        'views/lotmpr.xml',        
        'views/machine_cai.xml',
        'views/checkout_template.xml',         
        'views/website_sale_views.xml',         
        'views/chattemplate.xml',   
        'views/worker_qrcode.xml',   
        'views/report_qrcode.xml',   
        'views/crm.xml',   
        'views/work_manager.xml',   
        'views/order_preview.xml',   
        'views/report_crm_checkout.xml',   
        'views/linebot.xml',   
        'views/pettycash.xml',  
        'views/calendar.xml', 
        'views/performance.xml',  
        'views/views.xml',
    ],
	'assets': {
        'web.assets_backend': [        
            'dtsc/static/src/js/float_field_custom.js',
            'dtsc/static/src/js/custom_filter.js',
            'dtsc/static/src/js/custom_action.js',
            'dtsc/static/src/js/res_partner.js',  
            'dtsc/static/src/js/makein.js',  
            'dtsc/static/src/js/checkoutline.js',  
            'dtsc/static/src/js/chat_template.js', 
            'dtsc/static/src/js/html5-qrcode.min.js',
            # 'dtsc/static/src/js/work_sign.js',
            'dtsc/static/src/js/qrcode_scan.js',   
            'dtsc/static/src/css/dtsc.css', 
            'dtsc/static/src/js/geolocation_widget.js',
            'dtsc/static/src/xml/geolocation_widget.xml',
            'dtsc/static/src/js/tree_button.js', 
            'dtsc/static/src/xml/tree_button.xml',  
            'dtsc/static/src/js/stock_color.js',  
            'dtsc/static/src/js/inventory_report_list_controller.js',  
            'dtsc/static/src/js/inventory_report_list_model.js',  
        ],
        'web.assets_frontend': [
            'dtsc/static/src/js/checkout.js',
            'dtsc/static/src/js/order.js',
            'dtsc/static/src/js/public_web_order.js',
            'dtsc/static/src/js/checkout_view.js', 
            'dtsc/static/src/css/custom_styles.css',
            'dtsc/static/src/js/website_custom.js',
            'dtsc/static/src/js/html5-qrcode.min.js',
        ]
    },
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    "license": "LGPL-3",
    'post_init_hook': 'post_init_hook',
}
