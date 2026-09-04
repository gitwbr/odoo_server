from odoo import http
from odoo.http import request

class UserInfoController(http.Controller):
    def _partner_contact_address_complete(self, partner):
        """兼容社区版：web_map 提供的 contact_address_complete 在社区版不存在。"""
        if 'contact_address_complete' in partner._fields:
            return partner.contact_address_complete or ''
        parts = []
        if partner.street:
            parts.append(partner.street)
        if partner.street2:
            parts.append(partner.street2)
        city_line = ' '.join(p for p in [partner.zip or '', partner.city or ''] if p).strip()
        if city_line:
            parts.append(city_line)
        if partner.state_id:
            parts.append(partner.state_id.name)
        if partner.country_id:
            parts.append(partner.country_id.name)
        if parts:
            return ', '.join(parts)
        return (partner.contact_address or '').strip()

    @http.route('/my/user_info', type='json', auth="user")
    def user_info(self):
        user = request.env.user
        partner = user.partner_id
        user_info = {
            'id': partner.id,
            'name': user.name,
            'mobile': user.mobile,
            'phone': user.phone,
            'email': user.email,
            'custom_init_name': partner.custom_init_name,
            'contact_address_complete': self._partner_contact_address_complete(partner),
            'customclass_id': partner.customclass_id.id if partner.customclass_id else False,
        }

        return user_info

    @http.route('/my/user_info_client', type='json', auth="public", website=True)
    def user_info_client(self):
        partner = request.env['res.partner']
        is_internal_user = False

        partner_id = request.session.get('partner_id')
        if partner_id:
            partner = request.env['res.partner'].sudo().browse(partner_id)
        elif not request.website.is_public_user() and request.env.user.partner_id:
            partner = request.env.user.partner_id.sudo()
            is_internal_user = request.env.user.has_group('base.group_user')

        if not partner or not partner.exists():
            return {'error': 'No available frontend partner'}

        user_info_client = {
            'id': partner.id,
            'name': partner.name,
            'mobile': partner.mobile,
            'phone': partner.phone,
            'email': partner.email,
            'custom_init_name': partner.custom_init_name,
            'contact_address_complete': self._partner_contact_address_complete(partner),
            'customclass_id': partner.customclass_id.id if partner.customclass_id else False,
            'nop': partner.nop,
            'is_internal_user': is_internal_user,
        }

        return user_info_client


    def _can_public_web_order_search_customers(self):
        if request.website.is_public_user():
            return False
        return any(
            request.env.user.has_group(group_xmlid)
            for group_xmlid in (
                'base.group_user',
                'dtsc.group_dtsc_bs',
                'dtsc.group_dtsc_yw',
                'dtsc.group_dtsc_mg',
                'dtsc.group_dtsc_sc',
                'dtsc.group_dtsc_kj',
                'dtsc.group_dtsc_cg',
                'dtsc.group_dtsc_ck',
                'dtsc.group_dtsc_gly',
            )
        )

    @http.route('/dtsc/public_web_order/customer_search', type='json', auth="public", website=True)
    def public_web_order_customer_search(self, keyword='', limit=10):
        if not self._can_public_web_order_search_customers():
            return []

        keyword = (keyword or '').strip()
        if not keyword:
            return []

        try:
            limit = max(1, min(int(limit or 10), 30))
        except (TypeError, ValueError):
            limit = 10

        partners = request.env['res.partner'].sudo().search([
            ('customer_rank', '>', 0),
            ('coin_can_cust', '=', True),
            '|', '|',
            ('name', 'ilike', keyword),
            ('mobile', 'ilike', keyword),
            ('phone', 'ilike', keyword),
        ], limit=limit)

        return [{
            'id': partner.id,
            'name': partner.name,
            'mobile': partner.mobile,
            'phone': partner.phone,
            'email': partner.email,
            'street': partner.street,
            'customclass_id': (
                [partner.customclass_id.id, partner.customclass_id.display_name]
                if partner.customclass_id else False
            ),
            'custom_init_name': partner.custom_init_name,
            'nop': partner.nop,
        } for partner in partners]
