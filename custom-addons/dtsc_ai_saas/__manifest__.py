{
    'name': 'DTS-C AI SaaS Adapter',
    'summary': 'Optional SaaS lifecycle integration for the shared AI components',
    'version': '16.0.1.0.0',
    'depends': ['dtsc_ai_assistant', 'dtsc_ai_gateway'],
    'data': ['views/ai_settings_views.xml'],
    'assets': {'web.assets_backend': ['dtsc_ai_saas/static/src/js/availability.js']},
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
