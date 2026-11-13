import hmac

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class VatLogin(models.Model):
    _inherit = 'dtsc.vatlogin'

    vat_sub_password_hash = fields.Char(
        '子密碼雜湊', copy=False, groups='dtsc.group_dtsc_gly',
    )
    vat_sub_password = fields.Char(
        '設定子密碼', compute='_compute_sub_password', inverse='_inverse_sub_password',
        copy=False, groups='dtsc.group_dtsc_gly',
        help='輸入新密碼後儲存即可啟用或重設子帳號；留空不變更。停用請使用「停用子帳號」。',
    )
    has_sub_password = fields.Boolean(
        '子帳號已啟用', compute='_compute_has_sub_password',
        groups='dtsc.group_dtsc_gly',
    )

    @api.depends('vat_sub_password_hash')
    def _compute_sub_password(self):
        # Never return the stored hash or plaintext to the backend form.
        for record in self:
            record.vat_sub_password = False

    def _inverse_sub_password(self):
        for record in self:
            if record.vat_sub_password:
                record.vat_sub_password_hash = record.env['res.users']._crypt_context().hash(
                    record.vat_sub_password,
                )
            record.invalidate_recordset(['vat_sub_password'])

    @api.depends('vat_sub_password_hash')
    def _compute_has_sub_password(self):
        for record in self:
            record.has_sub_password = bool(record.vat_sub_password_hash)

    def _matches_sub_password(self, password):
        self.ensure_one()
        return bool(password and self.vat_sub_password_hash and
                    self.env['res.users']._crypt_context().verify(password, self.vat_sub_password_hash))

    @api.constrains('vat', 'vat_password', 'vat_sub_password_hash')
    def _check_distinct_passwords(self):
        for record in self:
            if record._matches_sub_password(record.vat_password or record.vat):
                raise ValidationError('主密碼與子密碼不能相同，請使用不同密碼。')
            if record._matches_sub_password(record.vat):
                raise ValidationError('子密碼不能使用統編，請使用其他密碼。')

    def _get_password_role(self, password):
        """Resolve identity only; both roles retain the same customer and ACLs."""
        self.ensure_one()
        if not isinstance(password, str) or not password:
            return False
        main_password = self.vat_password or self.vat
        if main_password and hmac.compare_digest(password.encode('utf-8'), main_password.encode('utf-8')):
            return 'main'
        if self._matches_sub_password(password):
            return 'sub'
        return False

    def _change_login_password(self, old_password, new_password):
        self.ensure_one()
        role = self._get_password_role(old_password)
        if not role:
            raise ValidationError('舊密碼不正確，請重新輸入！')
        if not new_password or new_password == self.vat:
            raise ValidationError('新密碼不能為空或使用統編，請使用其他密碼。')
        other_role = self._get_password_role(new_password)
        if other_role and other_role != role:
            raise ValidationError('主密碼與子密碼不能相同，請使用不同密碼。')
        field = 'vat_password' if role == 'main' else 'vat_sub_password'
        self.write({field: new_password})
        return role

    def action_disable_sub_account(self):
        self.write({'vat_sub_password_hash': False})
        return {'type': 'ir.actions.client', 'tag': 'reload'}
