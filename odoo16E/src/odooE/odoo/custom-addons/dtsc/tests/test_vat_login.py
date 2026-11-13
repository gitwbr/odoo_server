"""Run with Odoo's Python and PYTHONPATH; no database or network is used."""
import ast
from contextlib import nullcontext
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lxml import etree
from odoo.exceptions import ValidationError
from passlib.context import CryptContext


ADDON = Path(__file__).resolve().parents[1]


def load_module(relative):
    path = ADDON / relative
    name = 'odoo.addons.dtsc.' + relative.replace('/', '.').removesuffix('.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODEL = load_module('models/vat_login.py').VatLogin
MAIN = load_module('controllers/main.py')
GETUSER = load_module('models/getuser.py')
CRYPT = CryptContext(['pbkdf2_sha512'], pbkdf2_sha512__rounds=1000)


class Account:
    _get_password_role = MODEL._get_password_role
    _matches_sub_password = MODEL._matches_sub_password
    _change_login_password = MODEL._change_login_password
    _check_distinct_passwords = MODEL._check_distinct_passwords
    _inverse_sub_password = MODEL._inverse_sub_password
    _compute_sub_password = MODEL._compute_sub_password
    action_disable_sub_account = MODEL.action_disable_sub_account

    def __init__(self, main='Main-password', sub='Sub-password', partner_id=42):
        self.id = 17
        self.vat = '12345678'
        self.vat_password = main
        self.vat_sub_password = False
        self.vat_sub_password_hash = CRYPT.hash(sub) if sub else False
        self.partner_id = SimpleNamespace(id=partner_id)
        self.env = {'res.users': SimpleNamespace(_crypt_context=lambda: CRYPT)}

    def __iter__(self):
        return iter([self])

    def ensure_one(self):
        return self

    def invalidate_recordset(self, fields):
        assert fields == ['vat_sub_password']
        self._compute_sub_password()

    def write(self, values):
        before = dict(self.__dict__)
        try:
            self.__dict__.update(values)
            if 'vat_sub_password' in values:
                self._inverse_sub_password()
            self._check_distinct_passwords()
        except Exception:
            self.__dict__.update(before)
            raise


class Session(dict):
    uid = None

    def __init__(self):
        super().__init__()
        self.authenticate = Mock(side_effect=self._authenticate)

    def _authenticate(self, db, login, password):
        self.clear()  # Identity must survive authentication resetting the session.
        self.uid = 7
        return self.uid

    def logout(self, keep_db=False):
        self.clear()
        self.uid = None


class Env(dict):
    cr = SimpleNamespace(dbname='test', savepoint=nullcontext)


def make_request(account):
    partner = SimpleNamespace(
        id=42, name='Customer', mobile='', phone='', email='', custom_init_name='',
        contact_address_complete='', customclass_id=SimpleNamespace(id=8),
        nop=False, coin_can_cust=True, exists=lambda: True,
    )
    partner.sudo = lambda: partner
    partners = Mock()
    partners.sudo.return_value.browse.return_value = partner
    accounts = Mock()
    accounts.sudo.return_value.search.side_effect = (
        lambda domain, limit=1: account if domain == [('vat', '=', account.vat)] else False
    )
    orders = Mock()
    orders.sudo.return_value.search.return_value = []
    env = Env({'res.partner': partners, 'dtsc.vatlogin': accounts, 'dtsc.checkout': orders})
    return SimpleNamespace(
        env=env, session=Session(),
        render=lambda template, values: {'template': template, 'values': values},
        redirect=lambda url: {'redirect': url},
        website=SimpleNamespace(is_public_user=lambda: False),
    )


class PasswordTests(unittest.TestCase):
    def test_main_and_sub_are_distinct_and_invalid_password_is_rejected(self):
        account = Account()
        self.assertEqual(account._get_password_role('Main-password'), 'main')
        self.assertEqual(account._get_password_role('Sub-password'), 'sub')
        for password in ('wrong', '', None, False):
            self.assertFalse(account._get_password_role(password))

    def test_legacy_blank_password_still_requires_vat(self):
        account = Account(main=False, sub=None)
        self.assertEqual(account._get_password_role(account.vat), 'main')
        with self.assertRaisesRegex(ValidationError, '舊密碼'):
            account._change_login_password('anything', 'New-password')
        self.assertFalse(account.vat_password)
        account._change_login_password(account.vat, 'New-password')
        self.assertEqual(account._get_password_role('New-password'), 'main')

    def test_change_main_preserves_sub_and_change_sub_preserves_main(self):
        account = Account()
        account._change_login_password('Main-password', 'New-main')
        self.assertEqual(account._get_password_role('Sub-password'), 'sub')
        self.assertFalse(account._get_password_role('Main-password'))
        account._change_login_password('Sub-password', 'New-sub')
        self.assertEqual(account._get_password_role('New-main'), 'main')
        self.assertEqual(account._get_password_role('New-sub'), 'sub')
        self.assertFalse(account._get_password_role('Sub-password'))

    def test_conflicts_and_public_default_rejected_for_both_change_paths(self):
        account = Account()
        for old, new in [('Main-password', 'Sub-password'), ('Sub-password', 'Main-password'),
                         ('Main-password', ''), ('Sub-password', account.vat)]:
            with self.assertRaises(ValidationError):
                account._change_login_password(old, new)
        for values in ({'vat_password': 'Sub-password'}, {'vat_sub_password': 'Main-password'},
                       {'vat_sub_password': account.vat}, {'vat': 'Sub-password'}):
            with self.assertRaises(ValidationError):
                account.write(values)
        self.assertEqual(account._get_password_role('Main-password'), 'main')
        self.assertEqual(account._get_password_role('Sub-password'), 'sub')

    def test_sub_password_is_write_only_hashed_and_can_be_disabled(self):
        account = Account(sub=None)
        self.assertFalse(account._get_password_role('Sub-password'))
        account.write({'vat_sub_password': '中文子密碼'})
        self.assertNotIn('中文子密碼', account.vat_sub_password_hash)
        self.assertFalse(account.vat_sub_password)
        self.assertEqual(account._get_password_role('中文子密碼'), 'sub')
        account.write({'vat_sub_password': False})
        self.assertEqual(account._get_password_role('中文子密碼'), 'sub')
        account.action_disable_sub_account()
        self.assertFalse(account._get_password_role('中文子密碼'))
        self.assertEqual(account._get_password_role('Main-password'), 'main')

    def test_unicode_main_password(self):
        self.assertEqual(Account(main='中文主密碼')._get_password_role('中文主密碼'), 'main')


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.account = Account()
        self.request = make_request(self.account)
        self.patch = patch.object(MAIN, 'request', self.request)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        response_patch = patch('odoo.http.Response.load', side_effect=lambda result: result)
        response_patch.start()
        self.addCleanup(response_patch.stop)
        self.login = MAIN.MakeInController()
        self.checkout = MAIN.Checkout()

    def login_as(self, password, **kwargs):
        return self.login.custom_login(login=self.account.vat, password=password, **kwargs)

    def test_same_customer_odoo_user_and_business_data_for_both_roles(self):
        states, auth_calls, cards, profiles, domains = [], [], [], [], []
        for password in ('Main-password', 'Sub-password'):
            result = self.login_as(password)
            self.assertEqual(result, {'redirect': '/my/checkout-orders'})
            states.append((self.request.session.uid, dict(self.request.session)))
            auth_calls.append(self.request.session.authenticate.call_args)
            page = self.checkout.my_checkout_orders()
            cards.append(page['values']['order_cards'])
            self.assertEqual(page['values']['partner'].id, 42)
            self.assertEqual(page['values']['custom_login_role'], self.request.session['vat_login_role'])
            domain = self.request.env['dtsc.checkout'].sudo.return_value.search.call_args.args[0]
            domains.append(domain)
            self.assertIn(('customer_id', '=', 42), domain)
            with patch.object(GETUSER, 'request', self.request):
                profiles.append(GETUSER.UserInfoController().user_info_client())
            self.assertEqual(self.checkout._public_web_order_customer_class_id(8), 8)
            self.assertFalse(self.checkout._public_web_order_customer_class_id(99))
        self.assertEqual([state[0] for state in states], [7, 7])
        for key in ('partner_id', 'vat_login_id'):
            self.assertEqual(states[0][1][key], states[1][1][key])
        self.assertEqual([state[1]['vat_login_role'] for state in states], ['main', 'sub'])
        self.assertEqual(auth_calls[0], auth_calls[1])
        self.assertEqual(cards[0], cards[1])
        self.assertEqual([profile.pop('is_sub_account') for profile in profiles], [False, True])
        self.assertEqual(profiles[0], profiles[1])
        # Time cutoff differs by microseconds; all other predicates are identical.
        self.assertEqual(domains[0][:-1], domains[1][:-1])

    def test_client_cannot_choose_role_and_account_switch_overwrites_role(self):
        self.login_as('Sub-password', vat_login_role='main', partner_id=999)
        self.assertEqual(self.request.session['vat_login_role'], 'sub')
        self.assertEqual(self.request.session['partner_id'], 42)
        self.login_as('Main-password')
        self.assertEqual(self.request.session['vat_login_role'], 'main')

    def test_failed_password_clears_previous_custom_identity(self):
        self.login_as('Sub-password')
        self.assertIn('error', self.login_as('wrong')['values'])
        self.assertFalse(self.request.session)

    def test_shared_user_failure_or_mfa_leaves_no_customer_identity(self):
        for effect in (RuntimeError('unavailable'), lambda *args: False, lambda *args: 7):
            self.request.session.uid = None
            self.request.session.authenticate.side_effect = effect
            result = self.login_as('Sub-password')
            self.assertIn('error', result['values'])
            self.assertFalse(self.request.session.get('partner_id'))
            self.assertFalse(self.request.session.get('vat_login_role'))

    def test_first_main_login_requires_password_change(self):
        self.account.vat_password = False
        result = self.login_as(self.account.vat)
        self.assertEqual(result['template'], 'dtsc.reset_password_page')
        self.request.session.authenticate.assert_not_called()
        self.assertFalse(self.request.session)

    def test_missing_customer_cannot_establish_session(self):
        self.account.partner_id.id = False
        self.assertIn('error', self.login_as('Sub-password')['values'])
        self.request.session.authenticate.assert_not_called()
        self.assertFalse(self.request.session)

    def test_logout_clears_identity_and_legacy_sessions_are_main(self):
        self.request.session['partner_id'] = 42
        self.assertEqual(self.checkout._get_custom_login_role(), 'main')
        self.login_as('Sub-password')
        self.checkout.custom_logout()
        self.assertFalse(self.request.session)
        self.assertFalse(self.checkout._get_custom_login_role())

    def test_other_customer_order_rejected_for_both_roles(self):
        other_order = SimpleNamespace(customer_id=SimpleNamespace(id=99))
        self.request.env['dtsc.checkout'].sudo.return_value.search.return_value = other_order
        for password in ('Main-password', 'Sub-password'):
            self.login_as(password)
            self.assertEqual(self.checkout.my_checkout_order_detail(900), {'redirect': '/my/checkout-entry'})
            self.assertEqual(self.login.show_order(900), {'redirect': '/custom/login'})

    def test_other_customer_file_check_rejected_for_both_roles(self):
        tree = ast.parse((ADDON / 'controllers/upload_ftp.py').read_text())
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'ai_member_check_item')
        method.decorator_list = []
        namespace = {'request': self.request}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<file check>', 'exec'), namespace)
        lines = Mock()
        lines.sudo.return_value.search.return_value = SimpleNamespace(
            checkout_product_id=SimpleNamespace(customer_id=SimpleNamespace(id=99), name='A900'),
        )
        self.request.env['dtsc.checkoutline'] = lines
        self.request.params = {'line_id': '900'}
        self.request.httprequest = SimpleNamespace(files={'custom_file': object()})
        controller = SimpleNamespace(_json_response=lambda values, status: (status, values))
        for password in ('Main-password', 'Sub-password'):
            self.login_as(password)
            status, body = namespace['ai_member_check_item'](controller)
            self.assertEqual(status, 403)
            self.assertFalse(body['success'])

    def test_reset_controller_updates_only_verified_credential(self):
        for old, new, role in [('Sub-password', 'New-sub', 'sub'), ('Main-password', 'New-main', 'main')]:
            result = self.login.reset_password_confirm(account=self.account.vat, old_password=old,
                                                      new_password=new, confirm_password=new, role='forged')
            self.assertIn('success', result['values'])
            self.assertEqual(self.account._get_password_role(new), role)
        result = self.login.reset_password_confirm(account=self.account.vat, old_password='wrong',
                                                  new_password='Bad-change', confirm_password='Bad-change')
        self.assertIn('error', result['values'])
        self.assertEqual(self.account._get_password_role('New-sub'), 'sub')
        self.assertEqual(self.account._get_password_role('New-main'), 'main')

    def test_reset_mismatch_or_missing_values_does_not_change_passwords(self):
        for new, confirm in [('New-sub', 'different'), ('', '')]:
            result = self.login.reset_password_confirm(account=self.account.vat, old_password='Sub-password',
                                                      new_password=new, confirm_password=confirm)
            self.assertIn('error', result['values'])
            self.assertEqual(self.account._get_password_role('Sub-password'), 'sub')

    def test_login_and_reset_forms_keep_csrf_enabled(self):
        root = etree.parse(str(ADDON / 'views/worker_qrcode.xml'))
        for route, handler in [('/custom/loginconfirm', self.login.custom_login),
                               ('/reset/passwordconfirm', self.login.reset_password_confirm)]:
            self.assertTrue(handler.original_routing.get('csrf', True))
            form = root.xpath('//form[@action="%s"]' % route)[0]
            self.assertTrue(form.xpath('./input[@name="csrf_token"]'))


if __name__ == '__main__':
    unittest.main()
