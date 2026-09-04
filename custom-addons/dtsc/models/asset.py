# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

import pytz

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class DtscAssetCategory(models.Model):
    _name = 'dtsc.asset.category'
    _description = '資產類別'
    _order = 'sequence, id'

    name = fields.Char('類別名稱', required=True)
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('啟用', default=True)
    note = fields.Text('備註')
    asset_ids = fields.One2many('dtsc.asset', 'category_id', string='資產')
    asset_count = fields.Integer('資產數', compute='_compute_asset_count')

    @api.depends('asset_ids')
    def _compute_asset_count(self):
        for rec in self:
            rec.asset_count = len(rec.asset_ids)


class DtscAsset(models.Model):
    _name = 'dtsc.asset'
    _description = '資產'
    _order = 'sequence, id'

    name = fields.Char('資產名稱', required=True)
    code = fields.Char('資產編號')
    category_id = fields.Many2one(
        'dtsc.asset.category',
        string='類別',
        required=True,
        ondelete='restrict',
        index=True,
    )
    sequence = fields.Integer('排序', default=10)
    active = fields.Boolean('啟用', default=True)
    note = fields.Text('備註')
    usage_ids = fields.One2many('dtsc.asset.usage', 'asset_id', string='使用記錄')
    usage_state = fields.Selection(
        [
            ('idle', '空閑中'),
            ('using', '使用中'),
        ],
        string='使用狀態',
        compute='_compute_usage_state',
        store=False,
    )
    current_user_name = fields.Char('當前使用人', compute='_compute_usage_state')
    current_usage_id = fields.Many2one(
        'dtsc.asset.usage',
        string='當前使用記錄',
        compute='_compute_usage_state',
    )

    @api.constrains('code')
    def _check_code_uniq(self):
        for rec in self:
            if not rec.code:
                continue
            dup = self.search([
                ('code', '=', rec.code),
                ('id', '!=', rec.id),
            ], limit=1)
            if dup:
                raise ValidationError('資產編號不可重複：%s' % rec.code)

    @api.depends('usage_ids', 'usage_ids.state', 'usage_ids.employee_id')
    def _compute_usage_state(self):
        Usage = self.env['dtsc.asset.usage']
        for rec in self:
            if not rec.id:
                rec.usage_state = 'idle'
                rec.current_user_name = False
                rec.current_usage_id = False
                continue
            current = Usage.search([
                ('asset_id', '=', rec.id),
                ('state', '=', 'using'),
            ], limit=1)
            if current:
                rec.usage_state = 'using'
                rec.current_user_name = current.employee_id.name or current.line_user_id or ''
                rec.current_usage_id = current
            else:
                rec.usage_state = 'idle'
                rec.current_user_name = False
                rec.current_usage_id = False


class DtscAssetUsage(models.Model):
    _name = 'dtsc.asset.usage'
    _description = '資產使用記錄'
    _order = 'start_time desc, id desc'

    name = fields.Char('單號', readonly=True, copy=False, default='/')
    asset_id = fields.Many2one(
        'dtsc.asset',
        string='資產',
        required=True,
        ondelete='restrict',
        index=True,
    )
    category_id = fields.Many2one(
        related='asset_id.category_id',
        string='類別',
        store=True,
        index=True,
    )
    employee_id = fields.Many2one(
        'dtsc.workqrcode',
        string='使用人',
        required=True,
        ondelete='restrict',
        index=True,
    )
    line_user_id = fields.Char('LINE ID', index=True)
    start_time = fields.Datetime('開始時間', required=True, default=fields.Datetime.now, index=True)
    end_time = fields.Datetime('結束時間')
    duration_hours = fields.Float('時長(小時)', digits=(16, 2), readonly=True)
    duration_display = fields.Char('時長', compute='_compute_duration_display')
    state = fields.Selection(
        [
            ('using', '使用中'),
            ('done', '已結束'),
        ],
        string='狀態',
        default='using',
        required=True,
        index=True,
    )
    note = fields.Text('備註')

    @api.depends('start_time', 'end_time', 'duration_hours', 'state')
    def _compute_duration_display(self):
        for rec in self:
            hours = rec.duration_hours
            if rec.state == 'using' and rec.start_time:
                delta = fields.Datetime.now() - rec.start_time
                hours = max(delta.total_seconds(), 0) / 3600.0
            if not hours:
                rec.duration_display = '0分'
                continue
            total_minutes = int(round(hours * 60))
            h, m = divmod(total_minutes, 60)
            if h and m:
                rec.duration_display = '%s小時%s分' % (h, m)
            elif h:
                rec.duration_display = '%s小時' % h
            else:
                rec.duration_display = '%s分' % m

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('dtsc.asset.usage') or '/'
        return super().create(vals)

    @api.constrains('asset_id', 'state')
    def _check_exclusive_using(self):
        for rec in self:
            if rec.state != 'using':
                continue
            dup = self.search([
                ('asset_id', '=', rec.asset_id.id),
                ('state', '=', 'using'),
                ('id', '!=', rec.id),
            ], limit=1)
            if dup:
                user_name = dup.employee_id.name or '他人'
                raise ValidationError('資產「%s」使用中（%s），不可同時開啟第二筆。' % (
                    rec.asset_id.display_name, user_name,
                ))

    def _calc_duration_hours(self, start_time, end_time):
        if not start_time or not end_time:
            return 0.0
        delta = end_time - start_time
        return max(delta.total_seconds(), 0) / 3600.0

    def action_end(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.state != 'using':
                raise UserError('記錄「%s」已結束。' % rec.display_name)
            rec.write({
                'end_time': now,
                'duration_hours': self._calc_duration_hours(rec.start_time, now),
                'state': 'done',
            })
        return True

    @api.model
    def start_usage(self, asset_id, employee_id, line_user_id=None):
        """供 LINE / 後台開啟使用。"""
        asset = self.env['dtsc.asset'].browse(asset_id)
        if not asset.exists() or not asset.active:
            raise UserError('資產不存在或已停用。')
        employee = self.env['dtsc.workqrcode'].browse(employee_id)
        if not employee.exists():
            raise UserError('員工不存在。')
        current = self.search([
            ('asset_id', '=', asset.id),
            ('state', '=', 'using'),
        ], limit=1)
        if current:
            raise UserError('資產「%s」使用中（%s），請稍後再試。' % (
                asset.display_name, current.employee_id.name or '他人',
            ))
        return self.create({
            'asset_id': asset.id,
            'employee_id': employee.id,
            'line_user_id': line_user_id or employee.line_user_id or False,
            'start_time': fields.Datetime.now(),
            'state': 'using',
        })

    @api.model
    def end_usage(self, asset_id, employee_id):
        """結束本人對該資產的使用中記錄。"""
        usage = self.search([
            ('asset_id', '=', asset_id),
            ('employee_id', '=', employee_id),
            ('state', '=', 'using'),
        ], limit=1)
        if not usage:
            raise UserError('沒有可結束的使用記錄（只能結束自己開啟的）。')
        usage.action_end()
        return usage

    @api.model
    def get_usage_stats(self, filters=None):
        """統計頁 RPC：左欄樹 + 明細 + 合計。"""
        filters = filters or {}
        category_id = int(filters.get('category_id') or 0)
        asset_id = int(filters.get('asset_id') or 0)
        date_from = filters.get('date_from') or ''
        date_to = filters.get('date_to') or ''

        tz_name = self.env.context.get('tz') or self.env.user.tz or 'Asia/Taipei'
        try:
            user_tz = pytz.timezone(tz_name)
        except Exception:
            user_tz = pytz.timezone('Asia/Taipei')

        # 未帶日期時預設當月
        if not date_from or not date_to:
            today_local = datetime.now(user_tz).date()
            month_start = today_local.replace(day=1)
            if today_local.month == 12:
                next_month = today_local.replace(year=today_local.year + 1, month=1, day=1)
            else:
                next_month = today_local.replace(month=today_local.month + 1, day=1)
            month_end = next_month - timedelta(days=1)
            if not date_from:
                date_from = month_start.strftime('%Y-%m-%d')
            if not date_to:
                date_to = month_end.strftime('%Y-%m-%d')

        domain = []
        if asset_id:
            domain.append(('asset_id', '=', asset_id))
        elif category_id:
            domain.append(('category_id', '=', category_id))

        if date_from:
            try:
                local_start = user_tz.localize(datetime.strptime(date_from, '%Y-%m-%d'))
                utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
                domain.append(('start_time', '>=', utc_start))
            except ValueError:
                pass
        if date_to:
            try:
                local_end = user_tz.localize(
                    datetime.combine(datetime.strptime(date_to, '%Y-%m-%d').date(), time(23, 59, 59))
                )
                utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
                domain.append(('start_time', '<=', utc_end))
            except ValueError:
                pass

        records = self.search(domain, order='start_time desc, id desc', limit=2000)
        rows = []
        total_hours = 0.0
        using_count = 0
        now = fields.Datetime.now()
        for rec in records:
            hours = rec.duration_hours
            if rec.state == 'using' and rec.start_time:
                hours = max((now - rec.start_time).total_seconds(), 0) / 3600.0
            total_hours += hours
            if rec.state == 'using':
                using_count += 1
            rows.append({
                'id': rec.id,
                'name': rec.name or '',
                'asset': rec.asset_id.display_name or '',
                'category': rec.category_id.display_name or '',
                'employee': rec.employee_id.name or '',
                'start_time': fields.Datetime.context_timestamp(
                    self, rec.start_time
                ).strftime('%Y-%m-%d %H:%M:%S') if rec.start_time else '',
                'end_time': fields.Datetime.context_timestamp(
                    self, rec.end_time
                ).strftime('%Y-%m-%d %H:%M:%S') if rec.end_time else '',
                'duration_display': rec.duration_display or '',
                'duration_hours': round(hours, 2),
                'state': rec.state,
                'state_label': '使用中' if rec.state == 'using' else '已結束',
            })

        categories = self.env['dtsc.asset.category'].search([('active', '=', True)])
        tree = [{
            'type': 'all',
            'id': 0,
            'name': '全部',
            'children': [],
        }]
        for cat in categories:
            children = [{
                'type': 'asset',
                'id': asset.id,
                'name': asset.display_name,
                'usage_state': asset.usage_state,
                'current_user_name': asset.current_user_name or '',
            } for asset in cat.asset_ids.filtered(lambda a: a.active)]
            tree.append({
                'type': 'category',
                'id': cat.id,
                'name': cat.name,
                'children': children,
            })

        return {
            'filters': {
                'category_id': category_id,
                'asset_id': asset_id,
                'date_from': date_from,
                'date_to': date_to,
            },
            'tree': tree,
            'rows': rows,
            'summary': {
                'count': len(rows),
                'using_count': using_count,
                'total_hours': round(total_hours, 2),
                'total_display': self._format_hours(total_hours),
            },
        }

    @api.model
    def _format_hours(self, hours):
        total_minutes = int(round((hours or 0) * 60))
        h, m = divmod(total_minutes, 60)
        if h and m:
            return '%s小時%s分' % (h, m)
        if h:
            return '%s小時' % h
        return '%s分' % m


class DtscAssetUsageDashboard(models.Model):
    _name = 'dtsc.asset.usage.dashboard'
    _description = '資產使用統計'

    name = fields.Char(default='資產使用統計', required=True)
