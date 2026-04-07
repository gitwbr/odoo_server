# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': ' NewebPay(CREDIT)3.0',
    'version': '3.0',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "A payment provider for running fake payment flows for newebpay purposes.v3(CREDIT)",
    'depends': ['web','payment','account_payment'],
    'data': [
        'views/payment_newebpay_templates.xml',
        'views/payment_templates.xml',
        'views/payment_token_views.xml',
        'views/payment_transaction_views.xml',
        'views/payment_provider_views.xml',
        'data/payment_provider_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'assets': {
        'web.assets_frontend': [
            'payment_newebpay/static/src/js/**/*',
        ],
    },
    'license': 'LGPL-3',
}
