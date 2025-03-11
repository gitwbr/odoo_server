from odoo import http

class TestController(http.Controller):
    @http.route('/test', type='http', auth="public")
    def test_route(self):
        return "Test route is working"