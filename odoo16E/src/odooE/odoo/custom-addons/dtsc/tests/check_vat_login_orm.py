"""Execute inside `odoo-bin shell` after upgrading dtsc.

Uses synthetic VAT-login records only, then rolls the entire transaction back.
Never changes existing customer credentials or commits test records.
"""
from uuid import uuid4

from lxml import etree
from odoo.exceptions import ValidationError


def check(env):
    accounts = env['dtsc.vatlogin'].sudo()
    vat = 'VAT-REGRESSION-' + uuid4().hex
    assertions = 0

    def expect(condition):
        nonlocal assertions
        assert condition
        assertions += 1

    def rejected(operation):
        try:
            with env.cr.savepoint():
                operation()
        except ValidationError:
            expect(True)
        else:
            raise AssertionError('Invalid credential change was accepted')

    try:
        account = accounts.create({
            'vat': vat, 'vat_password': 'Regression-main',
            'partner_id': env.company.partner_id.id,
            'vat_sub_password': 'Regression-sub',
        })
        expect(account._get_password_role('Regression-main') == 'main')
        expect(account._get_password_role('Regression-sub') == 'sub')
        expect(account.has_sub_password)
        expect(not account.read(['vat_sub_password'])[0]['vat_sub_password'])
        expect('Regression-sub' not in account.vat_sub_password_hash)
        expect('Regression-sub' not in account.search_line)

        rejected(lambda: account.write({'vat_sub_password': 'Regression-main'}))
        rejected(lambda: account.write({'vat_password': 'Regression-sub'}))
        rejected(lambda: account.write({'vat_sub_password': vat}))
        rejected(lambda: account._change_login_password('wrong', 'Unexpected'))
        expect(account._get_password_role('Regression-main') == 'main')
        expect(account._get_password_role('Regression-sub') == 'sub')

        account._change_login_password('Regression-sub', 'Regression-sub-new')
        expect(account._get_password_role('Regression-main') == 'main')
        expect(account._get_password_role('Regression-sub-new') == 'sub')
        expect(not account._get_password_role('Regression-sub'))
        account._change_login_password('Regression-main', 'Regression-main-new')
        expect(account._get_password_role('Regression-main-new') == 'main')
        expect(account._get_password_role('Regression-sub-new') == 'sub')
        account.write({'vat_sub_password': False})
        expect(account._get_password_role('Regression-sub-new') == 'sub')
        account.action_disable_sub_account()
        expect(not account.has_sub_password)
        expect(not account._get_password_role('Regression-sub-new'))
        expect(account._get_password_role('Regression-main-new') == 'main')

        account.write({'vat_password': False})
        expect(account._get_password_role(vat) == 'main')
        rejected(lambda: account._change_login_password('arbitrary-old', 'Unexpected'))
        account._change_login_password(vat, 'Regression-first-login')
        expect(account._get_password_role('Regression-first-login') == 'main')

        # Rendering honours group membership even in a sudo environment.
        manager = env['res.users'].search([
            ('groups_id', 'in', [env.ref('dtsc.group_dtsc_gly').id]),
        ], limit=1)
        expect(bool(manager))
        form = accounts.with_user(manager).get_view(env.ref('dtsc.view_vatlogin_form').id, 'form')
        arch = etree.fromstring(form['arch'].encode())
        expect(bool(arch.xpath('//field[@name="vat_sub_password"]')))
        expect(bool(arch.xpath('//button[@name="action_disable_sub_account"]')))
        for role, label in [('main', '主帳號'), ('sub', '子帳號')]:
            rendered = env['ir.qweb']._render('dtsc.frontend_customer_login_label', {
                'is_custom_login': True, 'custom_login_role': role,
                'partner': env.company.partner_id,
            })
            expect(label in str(rendered))
        print('VAT ORM and QWeb checks passed:', assertions)
    finally:
        env.cr.rollback()
    assert not accounts.search_count([('vat', '=', vat)])
    print('All synthetic test records rolled back; existing customer credentials untouched.')


check(env)
