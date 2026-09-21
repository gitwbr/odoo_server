from odoo import models, fields
from datetime import datetime, timedelta, date
from odoo import _

class DtscCalendar(models.Model):
    _name = 'dtsc.calendar'
    _description = 'Meeting'

    name = fields.Char('事件')
    start_date = fields.Datetime('Start Date')
    end_date = fields.Datetime('End Date')
    all_day = fields.Boolean('全天事件', default=False)
    event_type = fields.Selection([
        ('personal', '事假'),
        ('sick', '病假'),
        ('annual', '年假'),
        ('late', '遲到'),
        ('early', '早退'),
        ('overtime', '加班'),
    ], string='事件類型')
    employee_id = fields.Many2one('dtsc.workqrcode', string="員工")