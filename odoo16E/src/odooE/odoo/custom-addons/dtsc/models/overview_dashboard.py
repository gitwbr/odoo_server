# -*- coding: utf-8 -*-

from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models


class DtscOverviewDashboard(models.Model):
    _name = 'dtsc.overview.dashboard'
    _description = 'DTSC Overview Dashboard'

    PERIOD_SELECTION = [
        ('last_7_days', '過去7天'),
        ('last_30_days', '過去30天'),
        ('last_90_days', '過去90天'),
        ('last_180_days', '過去180天'),
        ('last_365_days', '過去的365天內'),
        ('last_3_years', '過去3年'),
        ('custom', '自訂'),
    ]
    PERIOD_DAYS = {
        'last_7_days': 7,
        'last_30_days': 30,
        'last_90_days': 90,
        'last_180_days': 180,
        'last_365_days': 365,
        'last_3_years': 365 * 3,
    }
    FUNNEL_STATES = [
        ('draft', '草稿'),
        ('quoting', '做檔中'),
        ('producing', '生產中'),
        ('finished', '完成'),
        ('price_review_done', '價格已審'),
        ('receivable_assigned', '已轉應收'),
    ]
    CHECKOUT_MENU_DOMAIN = [
        ('is_invisible', '=', False),
        ('checkout_order_state', '!=', 'waiting_confirmation'),
    ]
    DASHBOARD_SECTION_ORDER = [
        'checkout',
        'workorder',
        'finance',
        'purchase',
        'product',
        'material',
        'people',
        'alert',
    ]

    name = fields.Char(default='概覽畫面', required=True)

    def _get_allowed_dashboard_sections(self):
        user = self.env.user
        if user.has_group('dtsc.group_dtsc_gly'):
            return list(self.DASHBOARD_SECTION_ORDER)

        sections = []
        if user.has_group('dtsc.group_dtsc_yw'):
            sections.append('checkout')
        if user.has_group('dtsc.group_dtsc_sc'):
            sections.extend(['workorder', 'material'])
        if user.has_group('dtsc.group_dtsc_kj'):
            sections.append('finance')
        if user.has_group('dtsc.group_dtsc_cg'):
            sections.append('purchase')

        section_set = set(sections)
        return [
            section for section in self.DASHBOARD_SECTION_ORDER
            if section in section_set
        ]

    @api.model
    def get_dashboard_metrics(self, filters=None):
        """Return dashboard metrics for each section's own filter state."""
        filters = self._normalize_dashboard_filters(filters)
        people_month = filters['people']['month']
        allowed_sections = self._get_allowed_dashboard_sections()
        checkout_salesperson = self._get_empty_checkout_salesperson_filter()
        if 'checkout' in allowed_sections:
            checkout_salesperson = self._get_checkout_salesperson_filter(filters['checkout'])
            filters['checkout']['salesperson_id'] = checkout_salesperson['selected_id']
        metric_tz = self.env.context.get('tz') or self.env.user.sudo().tz or 'UTC'
        metric_dashboard = self.sudo().with_context(tz=metric_tz)

        metrics = {
            'filters': filters,
            'allowed_sections': allowed_sections,
            'period': filters['checkout']['period'],
            'period_label': metric_dashboard._get_period_label(filters['checkout']),
            'checkout_period_label': metric_dashboard._get_period_label(filters['checkout']),
            'workorder_period_label': metric_dashboard._get_period_label(filters['workorder']),
            'finance_period_label': metric_dashboard._get_period_label(filters['finance']),
            'purchase_period_label': metric_dashboard._get_period_label(filters['purchase']),
            'product_period_label': metric_dashboard._get_period_label(filters['product']),
            'people_month_label': metric_dashboard._get_month_label(people_month),
            'checkout_salesperson_id': checkout_salesperson['selected_id'],
            'checkout_salesperson_label': checkout_salesperson['selected_label'],
            'checkout_salesperson_locked': checkout_salesperson['locked'],
            'checkout_salesperson_options': checkout_salesperson['options'],
        }

        checkout_needed = any(
            section in allowed_sections
            for section in ('checkout', 'workorder', 'product', 'alert')
        )
        Checkout = None
        base_domain = []
        if checkout_needed:
            Checkout = metric_dashboard.env['dtsc.checkout']
            base_domain = metric_dashboard._get_checkout_menu_domain()

        if 'checkout' in allowed_sections:
            checkout_base_domain = base_domain + checkout_salesperson['domain']
            today_domain = checkout_base_domain + metric_dashboard._get_date_domain('today')
            period_domain = checkout_base_domain + metric_dashboard._get_filter_field_date_domain(
                'create_date', filters['checkout']
            )
            sum_fields = [
                'record_price_and_construction_charge',
                'tax_of_price',
                'total_price_added_tax',
                'unit_all',
            ]
            period_sums = metric_dashboard._read_group_sums(Checkout, period_domain, sum_fields)
            state_items = metric_dashboard._read_group_items(
                Checkout, period_domain, 'checkout_order_state'
            )
            type_items = metric_dashboard._read_group_items(
                Checkout, period_domain, 'checkout_order_type'
            )
            today_count = Checkout.search_count(today_domain)
            period_count = Checkout.search_count(period_domain)
            period_records = Checkout.search(period_domain)
            trend_items = metric_dashboard._get_checkout_trend_items(period_records, filters['checkout'])
            risk_items = metric_dashboard._get_delivery_risk_items(Checkout, checkout_base_domain)
            funnel_items = metric_dashboard._get_state_funnel_items(state_items, period_domain)
            period_quantity = sum(period_records.mapped('quantity'))
            metrics.update({
                'checkout_today_count': metric_dashboard._format_number(today_count),
                'checkout_period_count': metric_dashboard._format_number(period_count),
                'checkout_period_untaxed': metric_dashboard._format_number(
                    period_sums.get('record_price_and_construction_charge', 0)
                ),
                'checkout_period_tax': metric_dashboard._format_number(
                    period_sums.get('tax_of_price', 0)
                ),
                'checkout_period_total': metric_dashboard._format_number(
                    period_sums.get('total_price_added_tax', 0)
                ),
                'checkout_period_quantity': metric_dashboard._format_number(period_quantity),
                'checkout_period_units': metric_dashboard._format_number(
                    period_sums.get('unit_all', 0)
                ),
                'checkout_today_domain': today_domain,
                'checkout_period_domain': period_domain,
                'checkout_state_summary': metric_dashboard._read_group_summary(
                    Checkout, period_domain, 'checkout_order_state'
                ),
                'checkout_type_summary': metric_dashboard._read_group_summary(
                    Checkout, period_domain, 'checkout_order_type'
                ),
                'checkout_state_items': state_items,
                'checkout_type_items': type_items,
                'checkout_trend_items': trend_items,
                'checkout_risk_items': risk_items,
                'checkout_overdue_delivery_count': metric_dashboard._format_number(risk_items[0]['value']),
                'checkout_today_delivery_due_count': metric_dashboard._format_number(risk_items[1]['value']),
                'checkout_next_three_days_delivery_due_count': metric_dashboard._format_number(risk_items[2]['value']),
                'checkout_funnel_items': funnel_items,
                **metric_dashboard._get_checkout_delivery_metrics(Checkout, period_domain),
            })

        if 'workorder' in allowed_sections:
            workorder_domain = base_domain + metric_dashboard._get_filter_field_date_domain(
                'create_date', filters['workorder']
            )
            workorder_records = Checkout.search(workorder_domain)
            metrics.update(metric_dashboard._get_checkout_conversion_metrics(workorder_records))

        if 'finance' in allowed_sections:
            metrics.update(metric_dashboard._get_finance_metrics(filters['finance']))

        if 'purchase' in allowed_sections:
            metrics.update(metric_dashboard._get_purchase_metrics(filters['purchase']))

        if 'product' in allowed_sections:
            product_domain = base_domain + metric_dashboard._get_filter_field_date_domain(
                'create_date', filters['product']
            )
            metrics.update(
                metric_dashboard._get_star_product_metrics(Checkout.search(product_domain))
            )

        material_metrics = {}
        if 'material' in allowed_sections or 'alert' in allowed_sections:
            material_metrics = metric_dashboard._get_material_consumption_metrics()
            if 'material' in allowed_sections:
                metrics.update(material_metrics)

        if 'people' in allowed_sections:
            metrics.update(metric_dashboard._get_people_admin_metrics(people_month))

        if 'alert' in allowed_sections:
            metrics.update(metric_dashboard._get_alert_metrics(material_metrics))

        return metrics

    def _normalize_dashboard_filters(self, filters):
        if isinstance(filters, str):
            filters = {
                'checkout': {'period': filters},
                'workorder': {'period': filters},
                'finance': {'period': filters},
                'purchase': {'period': filters},
                'product': {'period': filters},
            }
        elif not isinstance(filters, dict):
            filters = {}

        default_period = 'last_30_days'
        default_month = self._get_default_month_key()
        return {
            'checkout': self._normalize_section_period_filter(
                filters.get('checkout', {}), default_period
            ),
            'workorder': self._normalize_section_period_filter(
                filters.get('workorder', {}), default_period
            ),
            'finance': self._normalize_section_period_filter(
                filters.get('finance', {}), default_period
            ),
            'purchase': self._normalize_section_period_filter(
                filters.get('purchase', {}), default_period
            ),
            'product': self._normalize_section_period_filter(
                filters.get('product', {}), default_period
            ),
            'people': {
                'month': self._normalize_month_key(
                    filters.get('people', {}).get('month'), default_month
                ),
            },
        }

    def _normalize_filter_id(self, value):
        try:
            value = int(value or 0)
        except (TypeError, ValueError):
            value = 0
        return value if value > 0 else 0

    def _get_empty_checkout_salesperson_filter(self):
        return {
            'selected_id': 0,
            'selected_label': '全部業務',
            'locked': False,
            'options': [],
            'domain': [],
        }

    def _normalize_section_period_filter(self, section_filter, default_period='last_30_days'):
        if isinstance(section_filter, str):
            section_filter = {'period': section_filter}
        if not isinstance(section_filter, dict):
            section_filter = {}

        period = self._normalize_period(section_filter.get('period'), default_period)
        salesperson_id = self._normalize_filter_id(section_filter.get('salesperson_id'))
        if period == 'custom':
            date_from = self._parse_filter_date(section_filter.get('date_from'))
            date_to = self._parse_filter_date(section_filter.get('date_to'))
            if date_from and date_to:
                if date_from > date_to:
                    date_from, date_to = date_to, date_from
                return {
                    'period': 'custom',
                    'date_from': fields.Date.to_string(date_from),
                    'date_to': fields.Date.to_string(date_to),
                    'salesperson_id': salesperson_id,
                }
            period = default_period

        start_date, end_date = self._get_period_date_range(period)
        return {
            'period': period,
            'date_from': fields.Date.to_string(start_date),
            'date_to': fields.Date.to_string(end_date - timedelta(days=1)),
            'salesperson_id': salesperson_id,
        }

    def _get_checkout_salesperson_filter(self, checkout_filter):
        """Return the effective salesperson filter for the checkout section.

        Business users are always locked to their own sales orders. Management can
        inspect all salespeople or select a specific one.
        """
        user = self.env.user
        selected_id = self._normalize_filter_id(
            isinstance(checkout_filter, dict) and checkout_filter.get('salesperson_id')
        )
        locked = user.has_group('dtsc.group_dtsc_yw') and not user.has_group('dtsc.group_dtsc_gly')
        Users = self.env['res.users'].sudo()

        if locked:
            selected_id = user.id
            users = Users.browse(user.id)
            options = [{'id': user.id, 'label': user.name or user.login or '目前使用者'}]
        else:
            users = self._get_checkout_salesperson_users()
            if selected_id and selected_id not in users.ids:
                selected_id = 0
            options = [{'id': 0, 'label': '全部業務'}] + [
                {'id': salesperson.id, 'label': salesperson.name or salesperson.login}
                for salesperson in users
            ]

        selected_user = Users.browse(selected_id).exists() if selected_id else Users.browse()
        selected_label = (
            selected_user.name or selected_user.login
            if selected_user else '全部業務'
        )
        return {
            'selected_id': selected_id,
            'selected_label': selected_label,
            'locked': locked,
            'options': options,
            'domain': [('user_id', '=', selected_id)] if selected_id else [],
        }

    def _get_checkout_salesperson_users(self):
        group = self.env.ref('dtsc.group_dtsc_yw', raise_if_not_found=False)
        if not group:
            return self.env['res.users'].sudo().browse()
        return self.env['res.users'].sudo().search([
            ('groups_id', 'in', group.id),
            ('share', '=', False),
            ('active', '=', True),
        ], order='name, login, id')

    def _normalize_period(self, period, default_period='last_30_days'):
        return period if period in dict(self.PERIOD_SELECTION) else default_period

    def _get_period_label(self, period):
        if isinstance(period, dict):
            if period.get('period') == 'custom':
                date_from = period.get('date_from') or ''
                date_to = period.get('date_to') or ''
                if date_from and date_to:
                    return date_from if date_from == date_to else '%s 至 %s' % (date_from, date_to)
            period = period.get('period')
        return dict(self.PERIOD_SELECTION).get(period, dict(self.PERIOD_SELECTION)['last_30_days'])

    def _parse_filter_date(self, value):
        try:
            return fields.Date.to_date(value) if value else False
        except (TypeError, ValueError):
            return False

    def _get_default_month_key(self):
        return fields.Date.context_today(self).strftime('%Y-%m')

    def _normalize_month_key(self, month_key, default_month=None):
        default_month = default_month or self._get_default_month_key()
        try:
            datetime.strptime(month_key or '', '%Y-%m')
            return month_key
        except (TypeError, ValueError):
            return default_month

    def _get_month_label(self, month_key):
        month_key = self._normalize_month_key(month_key)
        year, month = month_key.split('-')
        return '%s年%s月' % (year, month)

    def _get_date_domain(self, period):
        return self._get_field_date_domain('create_date', period)

    def _get_field_date_domain(self, field_name, period):
        start_date, end_date = self._get_period_date_range(period)
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.min)
        return [
            (field_name, '>=', self._to_utc_datetime_string(start_datetime)),
            (field_name, '<', self._to_utc_datetime_string(end_datetime)),
        ]

    def _get_date_field_domain(self, field_name, period):
        start_date, end_date = self._get_period_date_range(period)
        return [
            (field_name, '>=', fields.Date.to_string(start_date)),
            (field_name, '<', fields.Date.to_string(end_date)),
        ]

    def _get_filter_field_date_domain(self, field_name, section_filter):
        start_date, end_date = self._get_period_filter_date_range(section_filter)
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.min)
        return [
            (field_name, '>=', self._to_utc_datetime_string(start_datetime)),
            (field_name, '<', self._to_utc_datetime_string(end_datetime)),
        ]

    def _get_filter_date_field_domain(self, field_name, section_filter):
        start_date, end_date = self._get_period_filter_date_range(section_filter)
        return [
            (field_name, '>=', fields.Date.to_string(start_date)),
            (field_name, '<', fields.Date.to_string(end_date)),
        ]

    def _get_checkout_menu_domain(self):
        """Keep dashboard metrics aligned with the main dtsc.checkout menu."""
        return list(self.CHECKOUT_MENU_DOMAIN)

    def _get_period_date_range(self, period):
        today = fields.Date.context_today(self)
        end_date = today + timedelta(days=1)
        if period == 'today':
            start_date = today
        else:
            days = self.PERIOD_DAYS.get(period, self.PERIOD_DAYS['last_30_days'])
            start_date = today - timedelta(days=days - 1)
        return start_date, end_date

    def _get_period_filter_date_range(self, section_filter):
        if isinstance(section_filter, dict) and section_filter.get('period') == 'custom':
            date_from = self._parse_filter_date(section_filter.get('date_from'))
            date_to = self._parse_filter_date(section_filter.get('date_to'))
            if date_from and date_to:
                if date_from > date_to:
                    date_from, date_to = date_to, date_from
                return date_from, date_to + timedelta(days=1)
        period = section_filter.get('period') if isinstance(section_filter, dict) else section_filter
        return self._get_period_date_range(period)

    def _to_utc_datetime_string(self, local_datetime):
        timezone_name = self.env.context.get('tz') or self.env.user.sudo().tz or 'UTC'
        timezone = pytz.timezone(timezone_name)
        localized = timezone.localize(local_datetime)
        utc_datetime = localized.astimezone(pytz.UTC).replace(tzinfo=None)
        return fields.Datetime.to_string(utc_datetime)

    def _format_number(self, value):
        return '{:,}'.format(int(value or 0))

    def _sum_money(self, records, field_name, absolute=True):
        total = 0
        for record in records:
            value = getattr(record, field_name, 0) or 0
            total += abs(value) if absolute else value
        return total

    def _read_group_sums(self, model, domain, field_names):
        valid_fields = [field_name for field_name in field_names if field_name in model._fields]
        if not valid_fields:
            return {}
        result = model.read_group(domain, valid_fields, [])
        return result[0] if result else {}

    def _read_group_summary(self, model, domain, field_name, limit=6):
        items = self._read_group_items(model, domain, field_name, limit=limit)
        if not items:
            return '暫無資料'
        return '\n'.join(
            '%s：%s' % (item['label'], self._format_number(item['value']))
            for item in items
        )

    def _read_group_items(self, model, domain, field_name, limit=6):
        if field_name not in model._fields:
            return []

        groups = model.read_group(domain, [field_name], [field_name], lazy=False)
        groups = sorted(groups, key=lambda group: group.get('__count', 0), reverse=True)
        labels = self._get_selection_labels(model, field_name)
        items = []
        for group in groups[:limit]:
            value = group.get(field_name)
            if isinstance(value, tuple):
                raw, label = value[0], value[1]
            else:
                raw, label = value, labels.get(value, value or '未設定')
            items.append({
                'label': label,
                'value': int(group.get('__count', 0) or 0),
                'raw': raw or '',
                'domain': list(domain) + [(field_name, '=', raw)],
            })
        return items

    def _read_group_sum_items(
        self, model, domain, group_field, sum_field, limit=6, untaxed_sum_field=None
    ):
        if group_field not in model._fields or sum_field not in model._fields:
            return []

        fields_to_sum = [group_field, sum_field]
        has_untaxed = bool(untaxed_sum_field and untaxed_sum_field in model._fields)
        if has_untaxed:
            fields_to_sum.append(untaxed_sum_field)

        groups = model.read_group(domain, fields_to_sum, [group_field], lazy=False)
        groups = sorted(groups, key=lambda group: group.get(sum_field, 0) or 0, reverse=True)
        labels = self._get_selection_labels(model, group_field)
        items = []
        for group in groups[:limit]:
            raw_value = group.get(group_field)
            if isinstance(raw_value, tuple):
                raw, label = raw_value[0], raw_value[1]
            else:
                raw, label = raw_value, labels.get(raw_value, raw_value or '未設定')
            items.append({
                'label': label or '未設定',
                'value': int(group.get(sum_field, 0) or 0),
                'untaxed_value': int(group.get(untaxed_sum_field, 0) or 0) if has_untaxed else False,
                'count': int(group.get('__count', 0) or 0),
                'raw': raw or '',
                'record_id': raw if isinstance(raw, int) else False,
                'domain': list(domain) + [(group_field, '=', raw if raw else False)],
            })
        return items

    def _get_checkout_trend_items(self, records, period, date_field='create_date'):
        mode = self._get_trend_mode(period)
        start_date, end_date = self._get_period_filter_date_range(period)
        buckets = self._build_trend_buckets(start_date, end_date, mode)

        for record in records:
            date_value = getattr(record, date_field, False)
            if not date_value:
                continue
            local_date = self._to_local_date(date_value)
            key, label = self._get_trend_bucket(local_date, mode)
            if key not in buckets:
                buckets[key] = {
                    'label': label,
                    'order_count': 0,
                    'total_amount': 0,
                    'untaxed_amount': 0,
                    'total_units': 0,
                }
            buckets[key]['order_count'] += 1
            buckets[key]['total_amount'] += int(record.total_price_added_tax or 0)
            buckets[key]['untaxed_amount'] += int(record.record_price_and_construction_charge or 0)
            buckets[key]['total_units'] += int(record.unit_all or 0)

        return list(buckets.values())

    def _to_local_date(self, date_value):
        if isinstance(date_value, datetime):
            return fields.Datetime.context_timestamp(self, date_value).date()
        return fields.Date.to_date(date_value)

    def _get_trend_mode(self, period):
        if isinstance(period, dict):
            start_date, end_date = self._get_period_filter_date_range(period)
            days = max((end_date - start_date).days, 1)
            if days <= 31:
                return 'day'
            if days <= 180:
                return 'week'
            return 'month'
        if period in ('last_7_days', 'last_30_days'):
            return 'day'
        if period in ('last_90_days', 'last_180_days'):
            return 'week'
        return 'month'

    def _build_trend_buckets(self, start_date, end_date, mode):
        buckets = {}
        current = self._normalize_bucket_start(start_date, mode)
        step = {'day': 1, 'week': 7}.get(mode)

        while current < end_date:
            key, label = self._get_trend_bucket(current, mode)
            buckets[key] = {
                'label': label,
                'order_count': 0,
                'total_amount': 0,
                'untaxed_amount': 0,
                'total_units': 0,
            }
            if mode == 'month':
                current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
            else:
                current += timedelta(days=step)
        return buckets

    def _normalize_bucket_start(self, date_value, mode):
        if mode == 'week':
            return date_value - timedelta(days=date_value.weekday())
        if mode == 'month':
            return date_value.replace(day=1)
        return date_value

    def _get_trend_bucket(self, date_value, mode):
        if mode == 'week':
            monday = date_value - timedelta(days=date_value.weekday())
            sunday = monday + timedelta(days=6)
            return monday.isoformat(), '%s/%s-%s/%s' % (
                monday.month, monday.day, sunday.month, sunday.day
            )
        if mode == 'month':
            month = date_value.replace(day=1)
            return month.strftime('%Y-%m'), '%s/%02d' % (month.year, month.month)
        return date_value.isoformat(), '%s/%s' % (date_value.month, date_value.day)

    def _get_delivery_risk_items(self, Checkout, scope_domain):
        now = fields.Datetime.now()
        today = fields.Date.context_today(self)
        active_domain = list(scope_domain) + [
            ('is_delivery', '=', False),
            ('checkout_order_state', 'not in', ['cancel', 'closed']),
        ]
        today_start = self._to_utc_datetime_string(datetime.combine(today, time.min))
        tomorrow_start = self._to_utc_datetime_string(datetime.combine(today + timedelta(days=1), time.min))
        next_four_days = self._to_utc_datetime_string(datetime.combine(today + timedelta(days=4), time.min))

        overdue_domain = active_domain + [
            ('estimated_date', '<', fields.Datetime.to_string(now)),
        ]
        today_delivery_domain = active_domain + [
            ('estimated_date', '>=', today_start),
            ('estimated_date', '<', tomorrow_start),
        ]
        next_three_days_domain = active_domain + [
            ('estimated_date', '>=', today_start),
            ('estimated_date', '<', next_four_days),
        ]

        return [
            {
                'label': '逾期未出貨',
                'value': Checkout.search_count(overdue_domain),
                'tone': 'danger',
                'domain': overdue_domain,
            },
            {
                'label': '今日需出貨',
                'value': Checkout.search_count(today_delivery_domain),
                'tone': 'warning',
                'domain': today_delivery_domain,
            },
            {
                'label': '3天內需出貨',
                'value': Checkout.search_count(next_three_days_domain),
                'tone': 'info',
                'domain': next_three_days_domain,
            },
        ]

    def _get_checkout_delivery_metrics(self, Checkout, period_domain):
        """Return delivery progress for checkout records selected by create_date.

        The period domain still describes the checkout intake period. Delivery risk itself is
        evaluated by estimated_date in _get_delivery_risk_items.
        """
        CheckoutLine = self.env['dtsc.checkoutline']
        delivered_domain = list(period_domain) + [('is_delivery', '=', True)]
        pending_domain = list(period_domain) + [
            ('is_delivery', '=', False),
            ('checkout_order_state', 'not in', ['cancel', 'closed']),
        ]
        delivered_records = Checkout.search(delivered_domain)
        pending_count = Checkout.search_count(pending_domain)
        delivered_count = len(delivered_records)
        line_domain = [('checkout_product_id', 'in', delivered_records.ids)] if delivered_records else [('id', '=', 0)]

        return {
            'checkout_delivered_count': self._format_number(delivered_count),
            'checkout_pending_delivery_count': self._format_number(pending_count),
            'checkout_delivery_progress_items': [
                {'label': '已轉出貨', 'value': delivered_count, 'domain': delivered_domain},
                {'label': '未轉出貨', 'value': pending_count, 'domain': pending_domain},
            ],
            'checkout_delivery_carrier_items': self._read_group_items(
                Checkout, delivered_domain, 'delivery_carrier', limit=6
            ),
            'checkout_delivery_machine_items': self._read_group_sum_items(
                CheckoutLine, line_domain, 'machine_id', 'total_units', limit=6
            ),
            'checkout_delivery_material_items': self._read_group_sum_items(
                CheckoutLine, line_domain, 'product_id', 'total_units', limit=6
            ),
        }

    def _get_checkout_conversion_metrics(self, checkout_records):
        """Return downstream B/C/G/T conversion metrics scoped by checkout records.

        The dashboard is centered on dtsc.checkout. Downstream orders are counted by their
        linked checkout_id so converted A/F/E/M/D work is still visible in the main block.
        """
        checkout_ids = checkout_records.ids
        if not checkout_ids:
            empty_items = [
                {'label': 'B 內製', 'value': 0, 'domain': [('id', '=', 0)]},
                {'label': 'C 委外', 'value': 0, 'domain': [('id', '=', 0)]},
                {'label': 'G 代工', 'value': 0, 'domain': [('id', '=', 0)]},
                {'label': 'T 施工', 'value': 0, 'domain': [('id', '=', 0)]},
            ]
            return {
                'checkout_workorder_need_total': self._format_number(0),
                'checkout_workorder_generated_total': self._format_number(0),
                'checkout_workorder_completed_total': self._format_number(0),
                'checkout_workorder_pending_convert_total': self._format_number(0),
                'checkout_workorder_pending_complete_total': self._format_number(0),
                'checkout_workorder_need_items': empty_items,
                'checkout_workorder_generated_items': empty_items,
                'checkout_workorder_completed_items': empty_items,
                'checkout_workorder_pending_convert_items': empty_items,
                'checkout_workorder_pending_complete_items': empty_items,
                'checkout_workorder_state_items': [],
            }

        CheckoutLine = self.env['dtsc.checkoutline']
        checkout_id_sets = {
            'make_in': self._get_line_checkout_ids(
                CheckoutLine, [('checkout_product_id', 'in', checkout_ids), ('is_purchse', 'in', ['make_in', 'make_om'])]
            ),
            'make_out': self._get_line_checkout_ids(
                CheckoutLine, [('checkout_product_id', 'in', checkout_ids), ('is_purchse', '=', 'make_out')]
            ),
            'make_om': self._get_line_checkout_ids(
                CheckoutLine, [('checkout_product_id', 'in', checkout_ids), ('is_purchse', '=', 'make_om')]
            ),
            'install': self._get_line_checkout_ids(
                CheckoutLine, [('checkout_product_id', 'in', checkout_ids), ('is_install', '=', True)]
            ),
        }

        conversions = [
            self._get_conversion_item(
                label='B 內製',
                model_name='dtsc.makein',
                checkout_ids=checkout_id_sets['make_in'],
                completed_states=['stock_in'],
            ),
            self._get_conversion_item(
                label='C 委外',
                model_name='dtsc.makeout',
                checkout_ids=checkout_id_sets['make_out'],
                completed_states=['succ'],
            ),
            self._get_conversion_item(
                label='G 代工',
                model_name='dtsc.makeom',
                checkout_ids=checkout_id_sets['make_om'],
                completed_states=['succ', 'stock_in'],
            ),
            self._get_conversion_item(
                label='T 施工',
                model_name='dtsc.installproduct',
                checkout_ids=checkout_id_sets['install'],
                completed_states=['succ'],
            ),
        ]
        pending_convert_items = [
            {
                'label': item['label'],
                'value': max(item['needed'] - item['generated'], 0),
                'domain': item['pending_convert_domain'],
            }
            for item in conversions
        ]
        pending_complete_items = [
            {
                'label': item['label'],
                'value': max(item['generated'] - item['completed'], 0),
                'domain': item['pending_complete_domain'],
            }
            for item in conversions
        ]

        return {
            'checkout_workorder_need_total': self._format_number(
                sum(item['needed'] for item in conversions)
            ),
            'checkout_workorder_generated_total': self._format_number(
                sum(item['generated'] for item in conversions)
            ),
            'checkout_workorder_completed_total': self._format_number(
                sum(item['completed'] for item in conversions)
            ),
            'checkout_workorder_pending_convert_total': self._format_number(
                sum(item['value'] for item in pending_convert_items)
            ),
            'checkout_workorder_pending_complete_total': self._format_number(
                sum(item['value'] for item in pending_complete_items)
            ),
            'checkout_workorder_need_items': [
                {'label': item['label'], 'value': item['needed'], 'domain': item['needed_domain']}
                for item in conversions
            ],
            'checkout_workorder_generated_items': [
                {'label': item['label'], 'value': item['generated'], 'domain': item['generated_domain']}
                for item in conversions
            ],
            'checkout_workorder_completed_items': [
                {'label': item['label'], 'value': item['completed'], 'domain': item['completed_domain']}
                for item in conversions
            ],
            'checkout_workorder_pending_convert_items': pending_convert_items,
            'checkout_workorder_pending_complete_items': pending_complete_items,
            'checkout_workorder_state_items': self._get_workorder_state_items(checkout_ids),
        }

    def _get_line_checkout_ids(self, CheckoutLine, domain):
        lines = CheckoutLine.search(domain)
        return set(lines.mapped('checkout_product_id').ids)

    def _get_conversion_item(self, label, model_name, checkout_ids, completed_states):
        model = self.env[model_name]
        checkout_ids = list(checkout_ids)
        empty_domain = [('id', '=', 0)]
        if not checkout_ids:
            return {
                'label': label,
                'needed': 0,
                'generated': 0,
                'completed': 0,
                'needed_domain': empty_domain,
                'generated_domain': empty_domain,
                'completed_domain': empty_domain,
                'pending_convert_domain': empty_domain,
                'pending_complete_domain': empty_domain,
            }

        active_domain = [
            ('checkout_id', 'in', checkout_ids),
            ('install_state', '!=', 'cancel'),
        ]
        completed_domain = active_domain + [('install_state', 'in', completed_states)]
        generated_records = model.search(active_domain)
        completed_records = model.search(completed_domain)
        generated_checkout_ids = set(generated_records.mapped('checkout_id').ids)
        completed_checkout_ids = set(completed_records.mapped('checkout_id').ids)
        needed_checkout_ids = set(checkout_ids)
        pending_convert_ids = needed_checkout_ids - generated_checkout_ids
        pending_complete_ids = generated_checkout_ids - completed_checkout_ids
        return {
            'label': label,
            'needed': len(needed_checkout_ids),
            'generated': len(generated_checkout_ids),
            'completed': len(completed_checkout_ids),
            'needed_domain': [('id', 'in', list(needed_checkout_ids))],
            'generated_domain': [('id', 'in', list(generated_checkout_ids))],
            'completed_domain': [('id', 'in', list(completed_checkout_ids))],
            'pending_convert_domain': [('id', 'in', list(pending_convert_ids))],
            'pending_complete_domain': [('id', 'in', list(pending_complete_ids))],
        }

    def _get_workorder_state_items(self, checkout_ids):
        state_labels = {
            'draft': '草稿',
            'imaged': '已審',
            'making': '製作中',
            'installing': '進行中',
            'stock_in': '完成',
            'succ': '完成',
        }
        model_configs = [
            ('dtsc.makein', 'B'),
            ('dtsc.makeout', 'C'),
            ('dtsc.makeom', 'G'),
            ('dtsc.installproduct', 'T'),
        ]
        domains = {}
        for model_name, prefix in model_configs:
            records = self.env[model_name].search([
                ('checkout_id', 'in', checkout_ids),
                ('install_state', '!=', 'cancel'),
            ])
            for record in records:
                state_label = state_labels.get(record.install_state, record.install_state or '未設定')
                label = '%s %s' % (prefix, state_label)
                key = (model_name, label)
                domains.setdefault(key, []).append(record.id)
        return [
            {
                'label': label,
                'value': value,
                'domain': [('id', 'in', domains.get((model_name, label), []))],
                'action_model': model_name,
            }
            for (model_name, label), record_ids in sorted(
                domains.items(), key=lambda item: len(item[1]), reverse=True
            )
            for value in [len(record_ids)]
        ]

    def _get_finance_metrics(self, period_filter):
        """Return receivable/payable metrics scoped by invoice date.

        Existing DTSC invoice reports use invoice_date and don't force account.move.state,
        so this dashboard follows that same operational reporting basis.
        """
        Move = self.env['account.move']
        invoice_date_domain = self._get_filter_date_field_domain('invoice_date', period_filter)
        receivable_domain = [('move_type', '=', 'out_invoice')] + invoice_date_domain
        payable_domain = [('move_type', '=', 'in_invoice')] + invoice_date_domain
        period_move_domain = [('move_type', 'in', ['out_invoice', 'in_invoice'])] + invoice_date_domain

        receivable_records = Move.search(receivable_domain)
        payable_records = Move.search(payable_domain)

        receivable_total = self._sum_move_total(receivable_records)
        payable_total = self._sum_move_total(payable_records)
        receivable_untaxed_total = self._sum_move_untaxed(receivable_records)
        payable_untaxed_total = self._sum_move_untaxed(payable_records)

        return {
            'finance_receivable_total': self._format_number(receivable_total),
            'finance_receivable_untaxed_total': self._format_number(receivable_untaxed_total),
            'finance_receivable_count': self._format_number(len(receivable_records)),
            'finance_payable_total': self._format_number(payable_total),
            'finance_payable_untaxed_total': self._format_number(payable_untaxed_total),
            'finance_payable_count': self._format_number(len(payable_records)),
            'finance_net_gap': self._format_number(receivable_total - payable_total),
            'finance_net_untaxed_gap': self._format_number(receivable_untaxed_total - payable_untaxed_total),
            'finance_receivable_domain': receivable_domain,
            'finance_payable_domain': payable_domain,
            'finance_period_move_domain': period_move_domain,
            'finance_cash_gap_items': [
                {
                    'label': '期間應收',
                    'value': int(receivable_total),
                    'untaxed_value': int(receivable_untaxed_total),
                    'domain': receivable_domain,
                },
                {
                    'label': '期間應付',
                    'value': int(payable_total),
                    'untaxed_value': int(payable_untaxed_total),
                    'domain': payable_domain,
                },
            ],
            'finance_receivable_trend_items': self._get_move_trend_items(
                receivable_records, period_filter, base_domain=receivable_domain
            ),
            'finance_payable_trend_items': self._get_move_trend_items(
                payable_records, period_filter, base_domain=payable_domain
            ),
            'finance_receivable_customer_items': self._get_partner_amount_items(
                receivable_records, 'total_price', base_domain=receivable_domain,
                untaxed_field='sale_price'
            ),
            'finance_payable_vendor_items': self._get_partner_amount_items(
                payable_records, 'total_price', base_domain=payable_domain,
                untaxed_field='sale_price'
            ),
        }

    def _get_purchase_metrics(self, period_filter):
        """Return purchase order metrics scoped by purchase order date.

        DTSC purchase uses a custom my_state workflow, so the dashboard follows that
        instead of only relying on Odoo's native state field.
        """
        Purchase = self.env['purchase.order']
        PurchaseLine = self.env['purchase.order.line']
        period_domain = self._get_filter_field_date_domain('date_order', period_filter)
        active_domain = period_domain + [('my_state', '!=', '5'), ('state', '!=', 'cancel')]
        purchase_records = Purchase.search(active_domain)
        purchase_ids = purchase_records.ids
        line_domain = [('order_id', 'in', purchase_ids)] if purchase_ids else [('id', '=', 0)]
        amount_field = self._get_purchase_amount_field(Purchase)

        state_items = self._get_purchase_state_items(Purchase, active_domain)
        supplier_items = self._get_partner_amount_items(
            purchase_records, 'amount_total', base_domain=active_domain,
            untaxed_field=amount_field
        )

        return {
            'purchase_period_count': self._format_number(len(purchase_records)),
            'purchase_period_total': self._format_number(
                self._sum_money(purchase_records, amount_field)
            ),
            'purchase_period_taxed_total': self._format_number(
                self._sum_money(purchase_records, 'amount_total')
            ),
            'purchase_wait_confirm_count': self._format_number(
                self._get_purchase_state_count(Purchase, active_domain, ['1'])
            ),
            'purchase_wait_receipt_count': self._format_number(
                self._get_purchase_state_count(Purchase, active_domain, ['2'])
            ),
            'purchase_received_count': self._format_number(
                self._get_purchase_state_count(Purchase, active_domain, ['3', '4'])
            ),
            'purchase_to_bill_count': self._format_number(
                self._get_purchase_state_count(Purchase, active_domain, ['3'])
            ),
            'purchase_billed_count': self._format_number(
                self._get_purchase_state_count(Purchase, active_domain, ['4'])
            ),
            'purchase_period_domain': active_domain,
            'purchase_wait_confirm_domain': self._get_purchase_state_domain(active_domain, ['1']),
            'purchase_wait_receipt_domain': self._get_purchase_state_domain(active_domain, ['2']),
            'purchase_received_domain': self._get_purchase_state_domain(active_domain, ['3', '4']),
            'purchase_to_bill_domain': self._get_purchase_state_domain(active_domain, ['3']),
            'purchase_billed_domain': self._get_purchase_state_domain(active_domain, ['4']),
            'purchase_state_items': state_items,
            'purchase_receipt_items': [
                {
                    'label': '待收貨',
                    'value': self._get_purchase_state_count(Purchase, active_domain, ['2']),
                    'domain': self._get_purchase_state_domain(active_domain, ['2']),
                },
                {
                    'label': '已收貨未轉應付',
                    'value': self._get_purchase_state_count(Purchase, active_domain, ['3']),
                    'domain': self._get_purchase_state_domain(active_domain, ['3']),
                },
                {
                    'label': '已轉應付',
                    'value': self._get_purchase_state_count(Purchase, active_domain, ['4']),
                    'domain': self._get_purchase_state_domain(active_domain, ['4']),
                },
            ],
            'purchase_supplier_items': supplier_items,
            'purchase_product_amount_items': self._read_group_sum_items(
                PurchaseLine, line_domain, 'product_id', 'price_total', limit=6,
                untaxed_sum_field='price_subtotal'
            ),
            'purchase_product_qty_items': self._read_group_sum_items(
                PurchaseLine, line_domain, 'product_id', 'product_qty', limit=6
            ),
            'purchase_trend_items': self._get_purchase_trend_items(
                purchase_records, period_filter, amount_field, 'amount_total',
                base_domain=active_domain
            ),
            'purchase_taxed_trend_items': self._get_purchase_trend_items(
                purchase_records, period_filter, amount_field, 'amount_total',
                base_domain=active_domain
            ),
        }

    def _get_purchase_amount_field(self, Purchase):
        if 'no_vat_price' in Purchase._fields:
            return 'no_vat_price'
        if 'amount_untaxed' in Purchase._fields:
            return 'amount_untaxed'
        return 'amount_total'

    def _get_purchase_state_items(self, Purchase, domain):
        expected_states = ['1', '2', '3', '4']
        grouped_items = {
            item.get('raw'): item
            for item in self._read_group_items(Purchase, domain, 'my_state', limit=10)
        }
        labels = self._get_selection_labels(Purchase, 'my_state')
        return [
            {
                'label': labels.get(state, state),
                'value': int(grouped_items.get(state, {}).get('value') or 0),
                'raw': state,
                'domain': grouped_items.get(state, {}).get('domain') or self._get_purchase_state_domain(domain, [state]),
            }
            for state in expected_states
        ]

    def _get_purchase_state_count(self, Purchase, base_domain, states):
        return Purchase.search_count(self._get_purchase_state_domain(base_domain, states))

    def _get_purchase_state_domain(self, base_domain, states):
        return list(base_domain) + [('my_state', 'in', states)]

    def _get_purchase_trend_items(self, records, period, untaxed_field, taxed_field=None, base_domain=None):
        mode = self._get_trend_mode(period)
        start_date, end_date = self._get_period_filter_date_range(period)
        buckets = self._build_purchase_trend_buckets(start_date, end_date, mode, base_domain=base_domain)
        taxed_field = taxed_field or untaxed_field

        for record in records:
            if not record.date_order:
                continue
            local_date = self._to_local_date(record.date_order)
            key, label = self._get_trend_bucket(local_date, mode)
            if key not in buckets:
                buckets[key] = {
                    'label': label,
                    'purchase_count': 0,
                    'total_amount': 0,
                    'untaxed_amount': 0,
                    'domain': self._get_bucket_datetime_domain(base_domain, 'date_order', local_date, mode),
                }
            buckets[key]['purchase_count'] += 1
            buckets[key]['total_amount'] += int(abs(getattr(record, taxed_field, 0) or 0))
            buckets[key]['untaxed_amount'] += int(abs(getattr(record, untaxed_field, 0) or 0))

        return list(buckets.values())

    def _build_purchase_trend_buckets(self, start_date, end_date, mode, base_domain=None):
        buckets = {}
        current = self._normalize_bucket_start(start_date, mode)
        step = {'day': 1, 'week': 7}.get(mode)

        while current < end_date:
            key, label = self._get_trend_bucket(current, mode)
            buckets[key] = {
                'label': label,
                'purchase_count': 0,
                'total_amount': 0,
                'untaxed_amount': 0,
                'domain': self._get_bucket_datetime_domain(base_domain, 'date_order', current, mode),
            }
            if mode == 'month':
                current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
            else:
                current += timedelta(days=step)
        return buckets

    def _get_alert_metrics(self, material_metrics=None):
        """Return current actionable exceptions for the alert workbench."""
        material_metrics = material_metrics or {}
        Checkout = self.env['dtsc.checkout']
        now = fields.Datetime.now()
        base_domain = self._get_checkout_menu_domain()
        active_checkout_domain = base_domain + [
            ('checkout_order_state', 'not in', ['cancel', 'closed']),
        ]

        overdue_checkout_domain = active_checkout_domain + [
            ('is_delivery', '=', False),
            ('estimated_date', '<', fields.Datetime.to_string(now)),
        ]
        overdue_checkout_records = Checkout.search(overdue_checkout_domain)
        overdue_checkout_ids = set(overdue_checkout_records.ids)
        price_review_domain = self._get_stale_price_review_domain(Checkout, base_domain)
        material_shortage_checkout_domain = material_metrics.get('material_shortage_checkout_domain') or [('id', '=', 0)]
        workorder_overdue = self._get_overdue_workorder_alert(now, overdue_checkout_ids)
        overdue_delivery_reason_items = self._get_overdue_delivery_reason_items(
            overdue_checkout_records, set(workorder_overdue['checkout_ids'])
        )

        alert_items = [
            {
                'label': '價格已審超過3天',
                'value': Checkout.search_count(price_review_domain),
                'badge': '固定規則',
                'tone': 'warning',
                'domain': price_review_domain,
                'action_model': 'dtsc.checkout',
            },
            {
                'label': '缺料訂單',
                'value': Checkout.search_count(material_shortage_checkout_domain),
                'badge': '目前',
                'tone': 'danger',
                'domain': material_shortage_checkout_domain,
                'action_model': 'dtsc.checkout',
            },
        ]
        return {
            'alert_risk_items': alert_items,
            'alert_total_count': self._format_number(sum(item['value'] for item in alert_items)),
            'alert_overdue_delivery_reason_items': overdue_delivery_reason_items,
            'alert_workorder_model_items': workorder_overdue['model_items'],
        }

    def _get_stale_price_review_domain(self, Checkout, base_domain, stale_days=3):
        cutoff = fields.Datetime.now() - timedelta(days=stale_days)
        price_review_records = Checkout.search(
            list(base_domain) + [('checkout_order_state', '=', 'price_review_done')]
        )
        stale_ids = []
        for checkout in price_review_records:
            histories = checkout.checkoutstatehistory_ids.filtered(
                lambda history: history.new_state in ('價格已審', 'price_review_done')
            ).sorted('change_date')
            if histories:
                if histories[-1].change_date and histories[-1].change_date < cutoff:
                    stale_ids.append(checkout.id)
            elif checkout.write_date and checkout.write_date < cutoff:
                stale_ids.append(checkout.id)
        return [('id', 'in', stale_ids)] if stale_ids else [('id', '=', 0)]

    def _get_overdue_delivery_reason_items(self, overdue_checkouts, workorder_checkout_ids):
        """Split overdue unshipped orders into mutually exclusive operational causes."""
        reason_ids = {
            'unconfirmed': set(),
            'workorder_pending': set(),
            'producing_followup': set(),
            'ready_to_delivery': set(),
            'post_flow_missing_delivery': set(),
            'other': set(),
        }
        early_states = {'draft', 'quoting', 'waiting_confirmation'}
        post_delivery_states = {'price_review_done', 'receivable_assigned'}

        for checkout in overdue_checkouts:
            if checkout.checkout_order_state in early_states:
                reason_ids['unconfirmed'].add(checkout.id)
            elif checkout.id in workorder_checkout_ids:
                reason_ids['workorder_pending'].add(checkout.id)
            elif checkout.checkout_order_state == 'producing':
                reason_ids['producing_followup'].add(checkout.id)
            elif checkout.checkout_order_state == 'finished':
                reason_ids['ready_to_delivery'].add(checkout.id)
            elif checkout.checkout_order_state in post_delivery_states:
                reason_ids['post_flow_missing_delivery'].add(checkout.id)
            else:
                reason_ids['other'].add(checkout.id)

        labels = [
            ('unconfirmed', '未確認訂單'),
            ('workorder_pending', '工單未完成'),
            ('producing_followup', '生產中待追蹤'),
            ('ready_to_delivery', '工單完成未轉出貨'),
            ('post_flow_missing_delivery', '已審價/應收未建出貨'),
            ('other', '其他未出貨'),
        ]
        return [
            {
                'label': label,
                'value': len(reason_ids[key]),
                'domain': [('id', 'in', list(reason_ids[key]))] if reason_ids[key] else [('id', '=', 0)],
                'action_model': 'dtsc.checkout',
            }
            for key, label in labels
        ]

    def _get_overdue_workorder_alert(self, now, overdue_checkout_ids=None):
        model_configs = [
            ('dtsc.makein', 'B 內製', ['stock_in']),
            ('dtsc.makeout', 'C 委外', ['succ']),
            ('dtsc.makeom', 'G 代工', ['succ', 'stock_in']),
            ('dtsc.installproduct', 'T 施工', ['succ']),
        ]
        overdue_checkout_ids = set(overdue_checkout_ids or [])
        checkout_ids = set()
        model_items = []
        for model_name, label, completed_states in model_configs:
            model = self.env[model_name]
            checkout_domain = [('checkout_id', 'in', list(overdue_checkout_ids))] if overdue_checkout_ids else [('checkout_id', '=', 0)]
            domain = checkout_domain + [
                ('install_state', 'not in', completed_states + ['cancel']),
                ('delivery_date', '<', fields.Datetime.to_string(now)),
            ]
            if 'delivery_date' not in model._fields:
                domain = checkout_domain + [
                    ('install_state', 'not in', completed_states + ['cancel']),
                    ('checkout_id.estimated_date', '<', fields.Datetime.to_string(now)),
                ]
            records = model.search(domain)
            checkout_ids.update(records.mapped('checkout_id').ids)
            model_items.append({
                'label': label,
                'value': len(records),
                'domain': [('id', 'in', records.ids)] if records else [('id', '=', 0)],
                'action_model': model_name,
            })
        checkout_domain = [('id', 'in', list(checkout_ids))] if checkout_ids else [('id', '=', 0)]
        return {
            'checkout_count': len(checkout_ids),
            'checkout_ids': list(checkout_ids),
            'checkout_domain': checkout_domain,
            'model_items': model_items,
        }

    def _get_bucket_datetime_domain(self, base_domain, field_name, bucket_date, mode):
        if mode == 'month':
            bucket_start = bucket_date.replace(day=1)
            bucket_end = (bucket_start + timedelta(days=32)).replace(day=1)
        elif mode == 'week':
            bucket_start = bucket_date - timedelta(days=bucket_date.weekday())
            bucket_end = bucket_start + timedelta(days=7)
        else:
            bucket_start = bucket_date
            bucket_end = bucket_start + timedelta(days=1)
        return list(base_domain or []) + [
            (field_name, '>=', self._to_utc_datetime_string(datetime.combine(bucket_start, time.min))),
            (field_name, '<', self._to_utc_datetime_string(datetime.combine(bucket_end, time.min))),
        ]

    def _get_star_product_metrics(self, checkout_records):
        """Return product ranking metrics based on checkout product lines."""
        CheckoutLine = self.env['dtsc.checkoutline']
        if not checkout_records:
            line_records = CheckoutLine.browse()
        else:
            line_records = CheckoutLine.search([
                ('checkout_product_id', 'in', checkout_records.ids),
                ('product_id', '!=', False),
                ('product_id.can_be_expensed', '!=', True),
            ])

        product_ids = list(set(line_records.mapped('product_id').ids))
        line_domain = [('id', 'in', line_records.ids)] if line_records else [('id', '=', 0)]
        product_domain = [('id', 'in', product_ids)] if product_ids else [('id', '=', 0)]
        untaxed_total = sum(line_records.mapped('price'))
        taxed_total = sum(self._get_checkout_line_taxed_amount(line) for line in line_records)

        return {
            'star_product_count': self._format_number(len(product_ids)),
            'star_product_line_count': self._format_number(len(line_records)),
            'star_product_amount_total': self._format_number(untaxed_total),
            'star_product_taxed_amount_total': self._format_number(taxed_total),
            'star_product_units_total': self._format_number(sum(line_records.mapped('total_units'))),
            'star_product_quantity_total': self._format_number(sum(line_records.mapped('quantity'))),
            'star_product_product_domain': product_domain,
            'star_product_line_domain': line_domain,
            'star_product_amount_items': self._get_product_amount_pair_items(line_records),
            'star_product_units_items': self._get_product_metric_items(
                line_records, lambda line: line.total_units
            ),
            'star_product_quantity_items': self._get_product_metric_items(
                line_records, lambda line: line.quantity
            ),
            'star_product_scatter_items': self._get_product_scatter_items(line_records),
        }

    def _get_product_scatter_items(self, line_records, limit=14):
        totals = {}
        labels = {}
        line_ids = {}
        for line in line_records:
            product = line.product_id
            if not product:
                continue
            product_id = product.id
            labels[product_id] = product.display_name
            line_ids.setdefault(product_id, []).append(line.id)
            if product_id not in totals:
                totals[product_id] = {
                    'amount': 0,
                    'untaxed_amount': 0,
                    'units': 0,
                    'quantity': 0,
                }
            totals[product_id]['amount'] += self._get_checkout_line_taxed_amount(line)
            totals[product_id]['untaxed_amount'] += line.price or 0
            totals[product_id]['units'] += line.total_units or 0
            totals[product_id]['quantity'] += line.quantity or 0

        ranked_items = sorted(
            totals.items(),
            key=lambda item: item[1]['amount'],
            reverse=True,
        )[:limit]
        return [
            {
                'label': labels.get(product_id, '未設定'),
                'amount': round(values['amount'] or 0, 2),
                'untaxed_amount': round(values['untaxed_amount'] or 0, 2),
                'units': round(values['units'] or 0, 2),
                'quantity': round(values['quantity'] or 0, 2),
                'record_id': product_id,
                'domain': [('id', 'in', line_ids.get(product_id, []))],
                'action_model': 'dtsc.checkoutline',
            }
            for product_id, values in ranked_items
            if values['amount'] or values['units'] or values['quantity']
        ]

    def _get_product_amount_pair_items(self, line_records, limit=8):
        taxed_values = {}
        untaxed_values = {}
        product_labels = {}
        line_ids = {}
        for line in line_records:
            product = line.product_id
            if not product:
                continue
            product_id = product.id
            untaxed_values[product_id] = untaxed_values.get(product_id, 0) + (line.price or 0)
            taxed_values[product_id] = taxed_values.get(product_id, 0) + self._get_checkout_line_taxed_amount(line)
            product_labels[product_id] = product.display_name
            line_ids.setdefault(product_id, []).append(line.id)

        ranked_items = sorted(
            taxed_values.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:limit]
        return [
            {
                'label': product_labels.get(product_id, '未設定'),
                'value': int(value or 0),
                'untaxed_value': int(untaxed_values.get(product_id, 0) or 0),
                'record_id': product_id,
                'domain': [('id', 'in', line_ids.get(product_id, []))],
                'action_model': 'dtsc.checkoutline',
            }
            for product_id, value in ranked_items
            if value or untaxed_values.get(product_id)
        ]

    def _get_checkout_line_taxed_amount(self, line):
        untaxed = line.price or 0
        checkout = line.checkout_product_id
        if not checkout:
            return untaxed
        checkout_untaxed = checkout.record_price_and_construction_charge or 0
        checkout_taxed = checkout.total_price_added_tax or 0
        if checkout_untaxed and checkout_taxed:
            return untaxed * checkout_taxed / checkout_untaxed
        return untaxed

    def _get_product_metric_items(self, line_records, value_getter, limit=8):
        product_values = {}
        product_labels = {}
        line_ids = {}
        for line in line_records:
            product = line.product_id
            if not product:
                continue
            value = value_getter(line) or 0
            product_values[product.id] = product_values.get(product.id, 0) + value
            product_labels[product.id] = product.display_name
            line_ids.setdefault(product.id, []).append(line.id)

        ranked_items = sorted(
            product_values.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:limit]
        return [
            {
                'label': product_labels.get(product_id, '未設定'),
                'value': int(value or 0),
                'record_id': product_id,
                'domain': [('id', 'in', line_ids.get(product_id, []))],
                'action_model': 'dtsc.checkoutline',
            }
            for product_id, value in ranked_items
            if value
        ]

    def _get_people_admin_metrics(self, month_key):
        """Return management-level staff, attendance, leave and salary summaries."""
        Employee = self.env['dtsc.workqrcode']
        Worktime = self.env['dtsc.worktime']
        Attendance = self.env['dtsc.attendance']
        Leave = self.env['dtsc.leave']

        month_key = self._normalize_month_key(month_key)
        active_employee_domain = [('out_company_date', '=', False)]
        active_employees = Employee.search(active_employee_domain)
        worktime_records = self._get_worktime_month_records(Worktime, month_key)
        attendance_domain = self._get_date_field_month_domain('work_date', month_key)
        leave_domain = self._get_period_datetime_overlap_domain(
            'start_time', 'end_time', month_key
        )
        leave_records = Leave.search(leave_domain)
        approved_leave_records = leave_records.filtered(lambda leave: leave.state == 'approved')

        late_domain = attendance_domain + [('in_status', '=', 'cd')]
        early_domain = attendance_domain + [('out_status', '=', 'zt')]
        missing_domain = attendance_domain + ['|', ('in_status', '=', 'qk'), ('out_status', '=', 'qk')]
        leave_attendance_domain = attendance_domain + ['|', ('in_status', '=', 'qj'), ('out_status', '=', 'qj')]
        out_of_range_domain = attendance_domain + ['|', ('is_in_place', '=', 'bzfw'), ('is_out_place', '=', 'bzfw')]
        pending_buka_domain = attendance_domain + ['|', ('is_buka_in', '=', 'bkz'), ('is_buka_out', '=', 'bkz')]

        worktime_hours_total = self._sum_worktime_hours(worktime_records)
        line_bound_domain = active_employee_domain + [('line_user_id', '!=', False)]
        department_ids = list(set(active_employees.mapped('department').ids))
        worktime_employee_ids = list(set(worktime_records.mapped('workqrcode_id').ids))
        attendance_count = Attendance.search_count(attendance_domain)
        late_count = Attendance.search_count(late_domain)
        early_count = Attendance.search_count(early_domain)
        missing_count = Attendance.search_count(missing_domain)
        attendance_leave_count = Attendance.search_count(leave_attendance_domain)
        out_of_range_count = Attendance.search_count(out_of_range_domain)
        pending_buka_count = Attendance.search_count(pending_buka_domain)
        pending_leave_records = leave_records.filtered(lambda leave: leave.state == 'to_approved')
        salary_metrics = self._get_salary_metrics(month_key)

        return {
            'people_active_employee_count': self._format_number(len(active_employees)),
            'people_line_bound_count': self._format_number(
                len(active_employees.filtered(lambda employee: employee.line_user_id))
            ),
            'people_department_count': self._format_number(
                len(set(active_employees.mapped('department').ids))
            ),
            'people_worktime_count': self._format_number(len(worktime_records)),
            'people_worktime_cai_total': self._format_decimal_number(
                sum(worktime_records.mapped('cai_done'))
            ),
            'people_worktime_hours_total': self._format_decimal_number(worktime_hours_total),
            'people_worktime_employee_count': self._format_number(
                len(set(worktime_records.mapped('workqrcode_id').ids))
            ),
            'people_attendance_count': self._format_number(attendance_count),
            'people_attendance_late_count': self._format_number(late_count),
            'people_attendance_early_count': self._format_number(early_count),
            'people_attendance_missing_count': self._format_number(missing_count),
            'people_attendance_leave_count': self._format_number(attendance_leave_count),
            'people_attendance_out_of_range_count': self._format_number(out_of_range_count),
            'people_attendance_pending_buka_count': self._format_number(pending_buka_count),
            'people_leave_pending_count': self._format_number(len(pending_leave_records)),
            'people_leave_approved_count': self._format_number(len(approved_leave_records)),
            'people_leave_approved_hours': self._format_decimal_number(
                sum(approved_leave_records.mapped('leave_hours'))
            ),
            'people_active_employee_domain': active_employee_domain,
            'people_line_bound_domain': line_bound_domain,
            'people_department_domain': [('id', 'in', department_ids)] if department_ids else [('id', '=', 0)],
            'people_worktime_employee_domain': [('id', 'in', worktime_employee_ids)] if worktime_employee_ids else [('id', '=', 0)],
            'people_worktime_domain': [('id', 'in', worktime_records.ids)] if worktime_records else [('id', '=', 0)],
            'people_attendance_domain': attendance_domain,
            'people_attendance_late_domain': late_domain,
            'people_attendance_early_domain': early_domain,
            'people_attendance_missing_domain': missing_domain,
            'people_leave_pending_domain': [('id', 'in', pending_leave_records.ids)] if pending_leave_records else [('id', '=', 0)],
            'people_leave_approved_domain': [('id', 'in', approved_leave_records.ids)] if approved_leave_records else [('id', '=', 0)],
            'people_worktime_employee_items': self._get_worktime_employee_items(
                worktime_records
            ),
            'people_worktype_items': self._get_worktype_items(worktime_records),
            'people_attendance_risk_items': [
                {
                    'label': '遲到',
                    'value': late_count,
                    'tone': 'warning',
                    'domain': late_domain,
                },
                {
                    'label': '早退',
                    'value': early_count,
                    'tone': 'warning',
                    'domain': early_domain,
                },
                {
                    'label': '缺卡',
                    'value': missing_count,
                    'tone': 'danger',
                    'domain': missing_domain,
                },
                {
                    'label': '不在範圍',
                    'value': out_of_range_count,
                    'tone': 'danger',
                    'domain': out_of_range_domain,
                },
                {
                    'label': '補卡待審',
                    'value': pending_buka_count,
                    'tone': 'info',
                    'domain': pending_buka_domain,
                },
            ],
            'people_department_items': self._get_department_employee_items(active_employees),
            'people_leave_type_items': self._get_leave_type_items(approved_leave_records),
            **salary_metrics,
        }

    def _get_worktime_month_records(self, Worktime, month_key):
        completed_domain = self._get_field_month_domain('end_time', month_key) + [
            ('end_time', '!=', False),
        ]
        open_domain = self._get_field_month_domain('start_time', month_key) + [
            ('end_time', '=', False),
            ('start_time', '!=', False),
        ]
        return Worktime.search(completed_domain) | Worktime.search(open_domain)

    def _get_period_datetime_overlap_domain(self, start_field, end_field, month_key):
        start_date, end_date = self._get_month_date_range(month_key)
        start_datetime = self._to_utc_datetime_string(datetime.combine(start_date, time.min))
        end_datetime = self._to_utc_datetime_string(datetime.combine(end_date, time.min))
        return [
            (start_field, '<', end_datetime),
            (end_field, '>=', start_datetime),
        ]

    def _get_field_month_domain(self, field_name, month_key):
        start_date, end_date = self._get_month_date_range(month_key)
        return [
            (field_name, '>=', self._to_utc_datetime_string(datetime.combine(start_date, time.min))),
            (field_name, '<', self._to_utc_datetime_string(datetime.combine(end_date, time.min))),
        ]

    def _get_date_field_month_domain(self, field_name, month_key):
        start_date, end_date = self._get_month_date_range(month_key)
        return [
            (field_name, '>=', fields.Date.to_string(start_date)),
            (field_name, '<', fields.Date.to_string(end_date)),
        ]

    def _get_month_date_range(self, month_key):
        month_key = self._normalize_month_key(month_key)
        start_date = datetime.strptime(month_key, '%Y-%m').date().replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1)
        return start_date, end_date

    def _sum_worktime_hours(self, worktime_records):
        total_hours = 0
        for record in worktime_records:
            if not record.start_time or not record.end_time:
                continue
            seconds = (record.end_time - record.start_time).total_seconds()
            total_hours += max(seconds, 0) / 3600
        return total_hours

    def _get_worktime_employee_items(self, worktime_records, limit=8):
        totals = {}
        labels = {}
        record_ids = {}
        for record in worktime_records:
            employee = record.workqrcode_id
            if not employee:
                continue
            totals[employee.id] = totals.get(employee.id, 0) + (record.cai_done or 0)
            labels[employee.id] = employee.name or employee.display_name
            record_ids.setdefault(employee.id, []).append(record.id)
        return [
            {
                'label': labels.get(employee_id, '未設定'),
                'value': round(value or 0, 2),
                'record_id': employee_id,
                'domain': [('id', 'in', record_ids.get(employee_id, []))],
                'action_model': 'dtsc.worktime',
            }
            for employee_id, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
            if value
        ]

    def _get_worktype_items(self, worktime_records):
        labels = self._get_selection_labels(self.env['dtsc.worktime'], 'work_type')
        totals = {}
        record_ids = {}
        for record in worktime_records:
            work_type = record.work_type or 'unset'
            totals[work_type] = totals.get(work_type, 0) + (record.cai_done or 0)
            record_ids.setdefault(work_type, []).append(record.id)
        return [
            {
                'label': labels.get(work_type, work_type or '未設定'),
                'value': round(value or 0, 2),
                'raw': work_type,
                'domain': [('id', 'in', record_ids.get(work_type, []))],
                'action_model': 'dtsc.worktime',
            }
            for work_type, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)
            if value
        ]

    def _get_department_employee_items(self, employees):
        totals = {}
        labels = {}
        employee_ids = {}
        for employee in employees:
            department = employee.department
            department_id = department.id if department else 0
            labels[department_id] = department.display_name if department else '未設定部門'
            totals[department_id] = totals.get(department_id, 0) + 1
            employee_ids.setdefault(department_id, []).append(employee.id)
        return [
            {
                'label': labels.get(department_id, '未設定部門'),
                'value': count,
                'record_id': department_id or False,
                'domain': [('id', 'in', employee_ids.get(department_id, []))],
                'action_model': 'dtsc.workqrcode',
            }
            for department_id, count in sorted(totals.items(), key=lambda item: item[1], reverse=True)
        ]

    def _get_leave_type_items(self, leave_records):
        labels = self._get_selection_labels(self.env['dtsc.leave'], 'leave_type')
        totals = {}
        record_ids = {}
        for leave in leave_records:
            leave_type = leave.leave_type or 'unset'
            totals[leave_type] = totals.get(leave_type, 0) + (leave.leave_hours or 0)
            record_ids.setdefault(leave_type, []).append(leave.id)
        return [
            {
                'label': labels.get(leave_type, leave_type or '未設定'),
                'value': round(hours or 0, 2),
                'raw': leave_type,
                'domain': [('id', 'in', record_ids.get(leave_type, []))],
                'action_model': 'dtsc.leave',
            }
            for leave_type, hours in sorted(totals.items(), key=lambda item: item[1], reverse=True)
            if hours
        ]

    def _get_salary_metrics(self, month_key):
        Performance = self.env['dtsc.performance']
        year, month = self._normalize_month_key(month_key).split('-')
        performance = Performance.search([
            ('report_year.name', '=', year),
            ('report_month.name', '=', month),
        ], order='id desc', limit=1)
        if not performance:
            month_label = self._get_month_label(month_key)
            return {
                'people_salary_latest_period': '%s 尚無薪資總表' % month_label,
                'people_salary_employee_count': self._format_number(0),
                'people_salary_net_total': self._format_number(0),
                'people_salary_deduction_total': self._format_number(0),
                'people_salary_deduction_abs_total': self._format_number(0),
                'people_salary_net_average': self._format_number(0),
                'people_salary_average_score': self._format_decimal_number(0),
                'people_salary_record_domain': [('id', '=', 0)],
                'people_salary_record_items': [],
            }

        lines = performance.performanceline_ids
        scores = [line.total_score for line in lines if line.total_score is not False]
        average_score = sum(scores) / len(scores) if scores else 0
        net_total = sum(lines.mapped('sfje'))
        deduction_total = sum(lines.mapped('ykxz'))
        net_average = net_total / len(lines) if lines else 0
        return {
            'people_salary_latest_period': performance.name or '最新薪資總表',
            'people_salary_employee_count': self._format_number(len(lines)),
            'people_salary_net_total': self._format_number(net_total),
            'people_salary_deduction_total': self._format_number(deduction_total),
            'people_salary_deduction_abs_total': self._format_number(abs(deduction_total)),
            'people_salary_net_average': self._format_number(net_average),
            'people_salary_average_score': self._format_decimal_number(average_score),
            'people_salary_record_domain': [('id', '=', performance.id)],
            'people_salary_record_items': [
                {
                    'label': performance.name or '最新薪資總表',
                    'value': int(net_total or 0),
                    'record_id': performance.id,
                    'domain': [('id', '=', performance.id)],
                    'action_model': 'dtsc.performance',
                }
            ] if net_total else [],
        }

    def _get_material_consumption_metrics(self):
        """Current扣料 risk uses only draft records from 廠內扣料表."""
        MprLine = self.env['dtsc.mprline']
        lines = MprLine.search([
            ('mpr_id.state', '=', 'draft'),
            ('product_product_id', '!=', False),
        ], order='mpr_id desc, id asc')
        checkout_map = self._get_mpr_checkout_map(lines.mapped('mpr_id'))
        table_items = []
        pending_order_ids = set()
        pending_line_ids = set()
        shortage_line_ids = set()
        affected_checkout_ids = set()
        shortage_checkout_ids = set()
        affected_order_names = set()
        shortage_order_names = set()
        immediate_shortage_total = 0
        immediate_shortage_count = 0
        pending_total = 0

        for line in lines:
            mpr = line.mpr_id
            product = line.product_product_id
            target_uom = line.uom_id or product.uom_id
            checkout = checkout_map.get(mpr.from_name or '')
            current_stock = self._get_mpr_line_stock_in_uom(line, target_uom)
            pending_qty = line.now_use or 0
            immediate_shortage = max(pending_qty - current_stock, 0)
            status, tone = self._get_material_risk_status(
                immediate_shortage, pending_qty, current_stock
            )
            source_order = mpr.from_name or ''

            pending_order_ids.add(mpr.id)
            pending_line_ids.add(line.id)
            if source_order:
                affected_order_names.add(source_order)
            if checkout:
                affected_checkout_ids.add(checkout.id)
            if immediate_shortage:
                immediate_shortage_count += 1
                shortage_line_ids.add(line.id)
                if source_order:
                    shortage_order_names.add(source_order)
                if checkout:
                    shortage_checkout_ids.add(checkout.id)

            pending_total += pending_qty
            immediate_shortage_total += immediate_shortage

            table_items.append({
                'label': self._get_product_material_label(product),
                'category': self._get_material_category_label(product),
                'deduction_order': mpr.name or '',
                'source_order': source_order,
                'delivery_method': checkout.delivery_carrier if checkout else '',
                'delivery_date': self._format_material_date(
                    checkout.estimated_date if checkout else False
                ),
                'customer': checkout.customer_id.display_name if checkout and checkout.customer_id else '',
                'project': checkout.project_name if checkout else '',
                'warehouse': line.stock_location_id.display_name if line.stock_location_id else '',
                'stock': self._format_decimal_number(current_stock),
                'stock_raw': round(current_stock or 0, 2),
                'pending': self._format_decimal_number(pending_qty),
                'pending_raw': round(pending_qty or 0, 2),
                'immediate_shortage': self._format_decimal_number(immediate_shortage),
                'immediate_shortage_raw': round(immediate_shortage or 0, 2),
                'uom': target_uom.name if target_uom else '',
                'status': status,
                'tone': tone,
                'record_id': mpr.id,
                'delivery_date_sort': checkout.estimated_date.isoformat() if checkout and checkout.estimated_date else '9999-12-31',
            })

        table_items = sorted(
            table_items,
            key=lambda item: (
                item['delivery_date_sort'],
                item['delivery_method'] or '',
                item['source_order'] or '',
                item['deduction_order'] or '',
                -item['immediate_shortage_raw'],
            ),
        )[:80]
        for item in table_items:
            item.pop('delivery_date_sort', None)

        return {
            'material_pending_order_count': self._format_number(len(pending_order_ids)),
            'material_affected_order_count': self._format_number(len(affected_order_names)),
            'material_shortage_order_count': self._format_number(len(shortage_order_names)),
            'material_stock_item_count': self._format_number(len(lines)),
            'material_stock_total': self._format_number(0),
            'material_pending_total': self._format_decimal_number(pending_total),
            'material_period_actual_total': self._format_number(0),
            'material_immediate_shortage_count': self._format_number(immediate_shortage_count),
            'material_immediate_shortage_total': self._format_decimal_number(immediate_shortage_total),
            'material_trend_shortage_count': self._format_number(0),
            'material_trend_shortage_total': self._format_number(0),
            'material_replenishment_count': self._format_number(immediate_shortage_count),
            'material_replenishment_total': self._format_decimal_number(immediate_shortage_total),
            'material_forecast_days': self._format_number(0),
            'material_period_days': '不適用',
            'material_replenishment_table_items': table_items,
            'material_pending_order_domain': [('id', 'in', list(pending_order_ids))] if pending_order_ids else [('id', '=', 0)],
            'material_pending_line_domain': [('id', 'in', list(pending_line_ids))] if pending_line_ids else [('id', '=', 0)],
            'material_affected_checkout_domain': [('id', 'in', list(affected_checkout_ids))] if affected_checkout_ids else [('id', '=', 0)],
            'material_shortage_line_domain': [('id', 'in', list(shortage_line_ids))] if shortage_line_ids else [('id', '=', 0)],
            'material_shortage_checkout_domain': [('id', 'in', list(shortage_checkout_ids))] if shortage_checkout_ids else [('id', '=', 0)],
            # Compatibility keys for older templates/assets during browser cache transitions.
            'material_stock_value_total': self._format_number(0),
            'material_stock_items': [],
            'material_stock_value_items': [],
            'material_stock_table_items': [],
            'material_stock_category_tables': [],
            'material_planned_total': self._format_decimal_number(pending_total),
            'material_actual_total': self._format_number(0),
            'material_lot_actual_total': self._format_number(0),
            'material_shortage_total': self._format_decimal_number(immediate_shortage_total),
            'material_consumption_items': [],
            'material_planned_items': [],
            'material_actual_items': [],
            'material_lot_actual_items': [],
            'material_shortage_items': [],
            'material_replenishment_items': [],
            'material_usage_total': self._format_number(0),
            'material_remaining_total': self._format_number(0),
            'material_usage_items': [],
            'material_units_items': [],
        }

    def _get_mpr_checkout_map(self, mpr_records):
        order_names = [name for name in mpr_records.mapped('from_name') if name]
        checkouts = self.env['dtsc.checkout'].search([('name', 'in', order_names)])
        return {checkout.name: checkout for checkout in checkouts}

    def _get_mpr_line_stock_in_uom(self, line, target_uom):
        product = line.product_product_id
        location = line.stock_location_id
        if not product or not location:
            return 0
        quant_domain = [
            ('product_id', '=', product.id),
            ('location_id', '=', location.id),
        ]
        if line.product_lot:
            quant_domain.append(('lot_id', '=', line.product_lot.id))
        stock_quantity = sum(self.env['stock.quant'].search(quant_domain).mapped('quantity'))
        return self._convert_material_qty(
            product,
            stock_quantity,
            product.uom_id,
            target_uom or product.uom_id,
        )

    def _convert_material_qty(self, product, quantity, source_uom, target_uom):
        if not quantity or not source_uom or not target_uom or source_uom.id == target_uom.id:
            return quantity or 0
        if target_uom.name == '才' and source_uom.name != '才':
            return (quantity or 0) * (target_uom.factor or 1)
        if source_uom.name == '才' and target_uom.name != '才':
            return (quantity or 0) / (source_uom.factor or 1)
        if source_uom.category_id and source_uom.category_id == target_uom.category_id:
            return source_uom._compute_quantity(quantity or 0, target_uom)
        return quantity or 0

    def _format_material_date(self, value):
        if not value:
            return ''
        if isinstance(value, datetime):
            return fields.Datetime.context_timestamp(self, value).strftime('%Y-%m-%d')
        return fields.Date.to_date(value).strftime('%Y-%m-%d')

    def _get_material_risk_status(self, immediate_shortage, pending_qty, current_stock):
        if immediate_shortage > 0:
            return '待扣料不足', 'danger'
        if pending_qty > 0 and current_stock <= pending_qty * 1.1:
            return '安全餘量低', 'watch'
        return '正常', 'safe'

    def _get_material_category_label(self, product):
        category = product.categ_id
        if not category:
            return '未分類'
        return category.name or category.display_name or '未分類'

    def _format_decimal_number(self, value):
        number = float(value or 0)
        if number.is_integer():
            return '{:,}'.format(int(number))
        return '{:,.2f}'.format(number).rstrip('0').rstrip('.')

    def _get_inventory_product_stock_values(self):
        Product = self.env['product.product']
        products = Product.search([('purchase_ok', '=', True)], order='name asc, id asc')
        stock_values = {}
        stock_value_amounts = {}
        material_labels = {}
        has_total_value = 'total_value' in Product._fields
        table_items = []
        category_map = {}
        for product in products:
            stock_quantity = product.qty_available or 0
            stock_value = (
                (product.total_value or 0)
                if has_total_value
                else stock_quantity * (product.standard_price or 0)
            )
            stock_values[product.id] = stock_quantity
            stock_value_amounts[product.id] = stock_value
            material_labels[product.id] = self._get_product_material_label(product)
            category = product.categ_id
            category_id = category.id if category else 0
            category_name = '未分類'
            if category:
                category_name = getattr(category, 'complete_name', False) or category.display_name
            if category_id not in category_map:
                category_map[category_id] = {
                    'label': category_name,
                    'product_count': 0,
                    'stock_total': 0,
                    'value_total': 0,
                    'rows': [],
                }
            row_item = {
                'label': product.display_name,
                'average_price': self._format_two_decimal(
                    getattr(product, 'average_price', 0) or 0
                ),
                'total_value': self._format_two_decimal(stock_value),
                'stock_quantity': self._format_decimal_number(stock_quantity),
                'stock_raw': round(stock_quantity or 0, 2),
                'value_raw': round(stock_value or 0, 2),
                'uom': product.uom_id.name if product.uom_id else '',
                'record_id': product.id,
            }
            category_map[category_id]['product_count'] += 1
            category_map[category_id]['stock_total'] += stock_quantity
            category_map[category_id]['value_total'] += stock_value
            category_map[category_id]['rows'].append(row_item)
            if len(table_items) < 80:
                table_items.append(row_item)

        category_tables = []
        for category in sorted(category_map.values(), key=lambda item: item['label']):
            rows = sorted(
                category['rows'],
                key=lambda row: (row['label'] or '').lower(),
            )[:8]
            category_tables.append({
                'label': category['label'],
                'product_count': self._format_number(category['product_count']),
                'stock_total': self._format_decimal_number(category['stock_total']),
                'value_total': self._format_two_decimal(category['value_total']),
                'rows': rows,
            })
        return stock_values, stock_value_amounts, material_labels, table_items, category_tables[:8]

    def _format_two_decimal(self, value):
        return '{:,.2f}'.format(float(value or 0))

    def _merge_material_values(self, *value_maps):
        merged_values = {}
        for value_map in value_maps:
            for material_id, value in value_map.items():
                merged_values[material_id] = merged_values.get(material_id, 0) + (value or 0)
        return merged_values

    def _get_stock_quant_material_values(self):
        StockQuant = self.env['stock.quant']
        domain = [
            ('location_id', 'in', [8, 20]),
            ('quantity', '!=', 0),
            ('product_id', '!=', False),
        ]
        stock_values = {}
        stock_value_amounts = {}
        material_labels = {}
        has_total_value = 'total_value' in StockQuant._fields
        for quant in StockQuant.search(domain):
            product = quant.product_id
            if not product:
                continue
            stock_values[product.id] = stock_values.get(product.id, 0) + (quant.quantity or 0)
            stock_value_amounts[product.id] = stock_value_amounts.get(product.id, 0) + (
                (quant.total_value or 0) if has_total_value else 0
            )
            material_labels[product.id] = self._get_product_material_label(product)
        return stock_values, stock_value_amounts, material_labels

    def _get_replenishment_material_values(self):
        Orderpoint = self.env['stock.warehouse.orderpoint']
        domain = [('trigger', '=', 'auto')]
        if 'qty_to_order' in Orderpoint._fields:
            domain.append(('qty_to_order', '>', 0))

        material_values = {}
        material_labels = {}
        for orderpoint in Orderpoint.search(domain):
            product = orderpoint.product_id
            if not product:
                continue
            value = (
                orderpoint.qty_to_order
                if 'qty_to_order' in orderpoint._fields
                else orderpoint.product_min_qty
            ) or 0
            material_values[product.id] = material_values.get(product.id, 0) + value
            material_labels[product.id] = self._get_product_material_label(product)
        return material_values, material_labels

    def _get_product_material_label(self, product):
        uom_name = product.uom_id.name if product.uom_id else ''
        if uom_name:
            return '%s (%s)' % (product.display_name, uom_name)
        return product.display_name

    def _get_material_metric_items(self, material_values, material_labels, limit=8):
        ranked_items = sorted(
            material_values.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:limit]
        return [
            {
                'label': material_labels.get(material_id, '未設定'),
                'value': round(value or 0, 2),
                'record_id': material_id,
            }
            for material_id, value in ranked_items
            if value
        ]

    def _sum_move_total(self, records):
        field_name = 'total_price' if 'total_price' in records._fields else 'amount_total_signed'
        return self._sum_money(records, field_name)

    def _sum_move_untaxed(self, records):
        field_name = 'sale_price' if 'sale_price' in records._fields else 'amount_untaxed_signed'
        return self._sum_money(records, field_name)

    def _filter_overdue_moves(self, records, due_field):
        today = fields.Date.context_today(self)
        return records.filtered(
            lambda record: (record.amount_residual or 0)
            and self._get_record_date(record, due_field)
            and self._get_record_date(record, due_field) < today
        )

    def _get_record_date(self, record, field_name):
        date_value = getattr(record, field_name, False)
        return fields.Date.to_date(date_value) if date_value else False

    def _get_move_trend_items(self, records, period, base_domain=None):
        mode = self._get_trend_mode(period)
        start_date, end_date = self._get_period_filter_date_range(period)
        buckets = self._build_move_trend_buckets(start_date, end_date, mode)

        for record in records:
            if not record.invoice_date:
                continue
            local_date = fields.Date.to_date(record.invoice_date)
            key, label = self._get_trend_bucket(local_date, mode)
            if key not in buckets:
                buckets[key] = {
                    'label': label,
                    'move_count': 0,
                    'total_amount': 0,
                    'untaxed_amount': 0,
                    'residual_amount': 0,
                }
            buckets[key]['move_count'] += 1
            buckets[key]['total_amount'] += int(self._sum_move_total(record))
            buckets[key]['untaxed_amount'] += int(self._sum_move_untaxed(record))
            buckets[key]['residual_amount'] += int(abs(record.amount_residual or 0))

        if base_domain is not None:
            for bucket in buckets.values():
                bucket['domain'] = list(base_domain) + [
                    ('invoice_date', '>=', bucket['date_from']),
                    ('invoice_date', '<', bucket['date_to']),
                ]

        return list(buckets.values())

    def _build_move_trend_buckets(self, start_date, end_date, mode):
        buckets = {}
        current = self._normalize_bucket_start(start_date, mode)
        step = {'day': 1, 'week': 7}.get(mode)

        while current < end_date:
            key, label = self._get_trend_bucket(current, mode)
            if mode == 'month':
                next_current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
            else:
                next_current = current + timedelta(days=step)
            bucket_start = max(current, start_date)
            bucket_end = min(next_current, end_date)
            buckets[key] = {
                'label': label,
                'move_count': 0,
                'total_amount': 0,
                'untaxed_amount': 0,
                'residual_amount': 0,
                'date_from': fields.Date.to_string(bucket_start),
                'date_to': fields.Date.to_string(bucket_end),
            }
            current = next_current
        return buckets

    def _get_payment_state_items(self, records):
        labels = self._get_selection_labels(self.env['account.move'], 'payment_state')
        counters = {}
        for record in records:
            raw = record.payment_state or 'unknown'
            label = labels.get(raw, raw or '未設定')
            counters[label] = counters.get(label, 0) + 1
        return [
            {'label': label, 'value': value}
            for label, value in sorted(counters.items(), key=lambda item: item[1], reverse=True)
        ]

    def _get_partner_amount_items(
        self, records, amount_field, limit=6, base_domain=None, untaxed_field=None
    ):
        totals = {}
        untaxed_totals = {}
        labels = {}
        domains = {}
        for record in records:
            partner = record.partner_id
            partner_key = partner.id if partner else 0
            labels[partner_key] = partner.display_name if partner else '未設定'
            domains[partner_key] = list(base_domain or []) + [
                ('partner_id', '=', partner.id if partner else False),
            ]
            totals[partner_key] = totals.get(partner_key, 0) + abs(
                getattr(record, amount_field, 0) or 0
            )
            if untaxed_field:
                untaxed_totals[partner_key] = untaxed_totals.get(partner_key, 0) + abs(
                    getattr(record, untaxed_field, 0) or 0
                )
        return [
            {
                'label': labels[partner_key],
                'value': int(value),
                'untaxed_value': int(untaxed_totals.get(partner_key, 0)) if untaxed_field else False,
                'partner_id': partner_key or False,
                'domain': domains[partner_key],
            }
            for partner_key, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
            if value
        ]

    def _get_delivery_metrics(self, period):
        Checkout = self.env['dtsc.checkout']
        DeliveryOrder = self.env['dtsc.deliveryorder']
        CheckoutLine = self.env['dtsc.checkoutline']

        base_domain = self._get_checkout_menu_domain()
        delivery_date_domain = self._get_field_date_domain('estimated_date', period)
        today_delivery_domain = self._get_field_date_domain('estimated_date', 'today')
        active_domain = base_domain + delivery_date_domain + [
            ('checkout_order_state', 'not in', ['cancel', 'closed']),
        ]
        delivered_domain = active_domain + [('is_delivery', '=', True)]
        pending_domain = active_domain + [('is_delivery', '=', False)]
        today_delivered_domain = base_domain + today_delivery_domain + [('is_delivery', '=', True)]

        delivered_records = Checkout.search(delivered_domain)
        delivery_order_domain = self._get_field_date_domain('delivery_date', period) + [
            ('install_state', '!=', 'cancel'),
        ]
        delivery_order_count = DeliveryOrder.search_count(delivery_order_domain)
        delivered_sums = self._read_group_sums(Checkout, delivered_domain, ['unit_all'])
        delivered_quantity = sum(delivered_records.mapped('quantity'))
        pending_count = Checkout.search_count(pending_domain)
        generated_count = Checkout.search_count(delivered_domain)
        today_count = Checkout.search_count(today_delivered_domain)
        line_domain = [('checkout_product_id', 'in', delivered_records.ids)] if delivered_records else [('id', '=', 0)]

        return {
            'delivery_today_count': self._format_number(today_count),
            'delivery_period_count': self._format_number(generated_count),
            'delivery_order_count': self._format_number(delivery_order_count),
            'delivery_pending_count': self._format_number(pending_count),
            'delivery_period_quantity': self._format_number(delivered_quantity),
            'delivery_period_units': self._format_number(delivered_sums.get('unit_all', 0)),
            'delivery_progress_items': [
                {'label': '已生成出貨單', 'value': generated_count},
                {'label': '未生成出貨單', 'value': pending_count},
            ],
            'delivery_trend_items': self._get_checkout_trend_items(
                delivered_records, period, date_field='estimated_date'
            ),
            'delivery_units_trend_items': self._get_checkout_trend_items(
                delivered_records, period, date_field='estimated_date'
            ),
            'delivery_risk_items': self._get_delivery_risk_items(Checkout, active_domain),
            'delivery_carrier_items': self._read_group_items(
                Checkout, delivered_domain, 'delivery_carrier', limit=6
            ),
            'delivery_salesperson_items': self._read_group_items(
                Checkout, delivered_domain, 'user_id', limit=6
            ),
            'delivery_machine_items': self._read_group_sum_items(
                CheckoutLine, line_domain, 'machine_id', 'total_units', limit=6
            ),
            'delivery_material_items': self._read_group_sum_items(
                CheckoutLine, line_domain, 'product_id', 'total_units', limit=6
            ),
        }

    def _get_state_funnel_items(self, state_items, scope_domain=None):
        scope_domain = list(scope_domain or [])
        state_map = {
            item.get('raw'): int(item.get('value') or 0)
            for item in state_items
        }
        return [
            {
                'label': label,
                'value': state_map.get(state, 0),
                'raw': state,
                'domain': scope_domain + [('checkout_order_state', '=', state)],
            }
            for state, label in self.FUNNEL_STATES
        ]

    def _get_selection_labels(self, model, field_name):
        field = model._fields.get(field_name)
        selection = getattr(field, 'selection', None)
        if isinstance(selection, str):
            selection = getattr(model, selection)()
        elif callable(selection):
            selection = selection(model)
        return dict(selection or [])
