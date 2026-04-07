from odoo import http

class MyCustomPageController(http.Controller):
    @http.route('/my_custom_page', type='http', auth='public')
    def my_custom_page(self, **kwargs):
        return http.request.render('dtsc.my_custom_page_template')