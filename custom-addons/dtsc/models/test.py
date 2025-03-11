from odoo import http
from odoo.http import request

class UserInfoController(http.Controller):
    @http.route('/my/user_info', type='json', auth="user")
    def user_info(self):
        user = request.env.user
        user_info = {
            'id': user.partner_id.id,
            'name': user.name,
            'mobile': user.mobile,
            'phone': user.phone,
            'email': user.email,
            'contact_address_complete': user.contact_address_complete,
            'customclass_id': user.customclass_id.id if user.customclass_id else False,
        }

        return user_info