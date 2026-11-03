# -*- coding: utf-8 -*-
"""公司行事曆：放假日／補班日，並提供統一的工作日判斷。"""

import logging
from datetime import date, datetime

import pytz
import requests
from workalendar.asia import Taiwan

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class DtscHoliday(models.Model):
    _name = 'dtsc.holiday'
    _description = '公司行事曆（放假日／補班日）'
    _order = 'day_date'

    # 逐日行事曆資料源：date=YYYYMMDD、isHoliday、description
    HOLIDAY_JSON_URL = 'https://cdn.jsdelivr.net/gh/ruyut/TaiwanCalendar/data/%s.json'

    # 公司固定每年都放的日子（行事曆表無資料時的回退判斷）
    FIXED_EXTRA_OFF_DAYS = {
        (5, 1),    # 勞動節
        (9, 28),   # 教師節
        (10, 25),  # 光復節
        (12, 25),  # 行憲紀念日
    }

    # 每年不同、需逐年列出的放假日（如小年夜）
    EXTRA_OFF_DATES = {
        date(2026, 2, 15),
        date(2027, 2, 4),
        date(2028, 1, 24),
        date(2029, 2, 11),
        date(2030, 2, 1),
        date(2031, 1, 21),
        date(2032, 2, 11),
        date(2033, 1, 29),
        date(2034, 2, 17),
        date(2035, 2, 6),
        date(2036, 1, 26),
        date(2037, 2, 13),
    }

    day_date = fields.Date('日期', required=True, index=True)
    year = fields.Integer('年份', compute='_compute_year', store=True, index=True)
    is_working = fields.Boolean('需上班', default=True)
    description = fields.Char('說明')
    source = fields.Selection([
        ('api', '政府行事曆'),
        ('manual', '手動'),
    ], string='來源', default='api', required=True)

    _sql_constraints = [
        ('day_date_uniq', 'unique(day_date)', '日期不可重複'),
    ]

    @api.depends('day_date')
    def _compute_year(self):
        for rec in self:
            rec.year = rec.day_date.year if rec.day_date else False

    # ------------------------------------------------------------------
    # 統一判斷
    # ------------------------------------------------------------------
    @api.model
    def is_working_day(self, target_date):
        """回傳該日是否需上班：先查行事曆表，查無資料時回退內建日曆。"""
        if not target_date:
            return True
        if isinstance(target_date, str):
            try:
                target_date = datetime.strptime(target_date[:10], '%Y-%m-%d').date()
            except ValueError:
                _logger.warning('無法解析日期: %s', target_date)
                return True
        if isinstance(target_date, datetime):
            target_date = target_date.date()

        rec = self.sudo().search([('day_date', '=', target_date)], limit=1)
        if rec:
            return bool(rec.is_working)
        return self._fallback_is_working_day(target_date)

    @api.model
    def _fallback_is_working_day(self, target_date):
        """內建台灣日曆 + 公司固定假；與舊邏輯一致。"""
        if (target_date.month, target_date.day) in self.FIXED_EXTRA_OFF_DAYS:
            return False
        if target_date in self.EXTRA_OFF_DATES:
            return False
        try:
            return Taiwan().is_working_day(target_date)
        except Exception as e:
            _logger.warning('內建日曆判斷失敗 %s: %s', target_date, e)
            return True

    # ------------------------------------------------------------------
    # 同步
    # ------------------------------------------------------------------
    @api.model
    def _fetch_year_rows(self, year):
        """抓取指定年度資料；該年度尚未發布時回傳 None。"""
        url = self.HOLIDAY_JSON_URL % year
        try:
            resp = requests.get(url, timeout=15)
        except Exception as e:
            _logger.warning('行事曆下載失敗 year=%s: %s', year, e)
            return None
        if resp.status_code == 404:
            _logger.info('行事曆尚未發布 year=%s', year)
            return None
        if resp.status_code != 200:
            _logger.warning('行事曆下載異常 year=%s status=%s', year, resp.status_code)
            return None
        try:
            data = resp.json()
        except Exception as e:
            _logger.warning('行事曆解析失敗 year=%s: %s', year, e)
            return None
        if not isinstance(data, list) or not data:
            _logger.warning('行事曆格式不符 year=%s', year)
            return None
        return data

    @api.model
    def _sync_year(self, year):
        """同步指定年度，回傳寫入/更新的天數；手動維護的資料不覆蓋。"""
        rows = self._fetch_year_rows(year)
        if not rows:
            return 0

        Holiday = self.sudo()
        count = 0
        for row in rows:
            try:
                day = datetime.strptime(str(row.get('date')), '%Y%m%d').date()
            except (TypeError, ValueError):
                continue
            if day.year != year:
                continue

            vals = {
                'is_working': not bool(row.get('isHoliday')),
                'description': row.get('description') or '',
            }
            rec = Holiday.search([('day_date', '=', day)], limit=1)
            if rec:
                if rec.source == 'manual':
                    continue
                rec.write(vals)
                count += 1
            else:
                vals.update({'day_date': day, 'source': 'api'})
                Holiday.create(vals)
                count += 1
        _logger.info('行事曆同步完成 year=%s 筆數=%s', year, count)
        return count

    @api.model
    def _cron_sync_holidays(self):
        """排程：同步當年與次年；次年尚未發布時跳過。"""
        today = fields.Date.today()
        for year in (today.year, today.year + 1):
            try:
                self._sync_year(year)
            except Exception as e:
                _logger.warning('行事曆排程同步失敗 year=%s: %s', year, e)
        return True

    def action_sync_now(self):
        """後台按鈕：立即同步當年與次年。"""
        today = fields.Date.today()
        total = 0
        for year in (today.year, today.year + 1):
            total += self._sync_year(year)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '行事曆同步完成',
                'message': f'本次處理 {total} 筆（{today.year}、{today.year + 1} 年）',
                'type': 'success',
                'sticky': False,
            },
        }
