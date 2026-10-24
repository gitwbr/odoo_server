# -*- coding: utf-8 -*-
import logging

from odoo import SUPERUSER_ID, api, fields, models

_logger = logging.getLogger(__name__)


class PrintComposeJob(models.TransientModel):
    _name = 'dtsc.print.compose.job'
    _description = '排版 TIFF 合成進度'

    key = fields.Char(required=True, index=True)
    percent = fields.Float(default=0.0)
    message = fields.Char()
    state = fields.Selection(
        [('running', '合成中'), ('done', '完成'), ('error', '失敗')],
        default='running',
    )

    @api.model
    def _report(self, key, **vals):
        """以獨立交易立即提交進度，合成主交易不碰這張表。"""
        if not key:
            return
        try:
            with self.pool.cursor() as cr:
                env = api.Environment(cr, SUPERUSER_ID, {})
                Job = env[self._name]
                job = Job.search([('key', '=', key)], limit=1)
                if job:
                    job.write(vals)
                else:
                    Job.create(dict(vals, key=key))
        except Exception as err:  # noqa: BLE001
            _logger.warning('排版 TIFF 合成進度寫入失敗：%s', err)

    @api.model
    def get_progress(self, key):
        job = self.sudo().search([('key', '=', key)], limit=1)
        if not job:
            return {'state': 'pending', 'percent': 0.0, 'message': '準備中…'}
        return {
            'state': job.state,
            'percent': job.percent,
            'message': job.message or '',
        }
