# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PrintRollSegment(models.Model):
    """印刷捲出圖分段：同一張印刷單按自訂長度切成多個檔案。"""
    _name = 'dtsc.print.roll.segment'
    _description = '印刷捲出圖分段'
    _order = 'roll_id, sequence, id'

    roll_id = fields.Many2one(
        'dtsc.print.roll', string='印刷捲', required=True, ondelete='cascade', index=True,
    )
    order_id = fields.Many2one(
        related='roll_id.order_id', store=True, index=True, readonly=True,
    )
    sequence = fields.Integer(string='段序', default=1)
    start_mm = fields.Integer(string='起點(mm)', help='相對本捲內容起點（整毫米）')
    end_mm = fields.Integer(string='終點(mm)', help='相對本捲內容起點（整毫米，不含）')
    length_mm = fields.Integer(string='本段長(mm)', compute='_compute_length_mm')

    layout_tiff = fields.Binary(string='分段 TIFF', attachment=True, copy=False)
    layout_tiff_filename = fields.Char(string='TIFF 檔名', copy=False)
    layout_pdf = fields.Binary(string='分段 PDF', attachment=True, copy=False)
    layout_pdf_filename = fields.Char(string='PDF 檔名', copy=False)
    note = fields.Char(string='說明', copy=False)

    @api.depends('start_mm', 'end_mm')
    def _compute_length_mm(self):
        for rec in self:
            rec.length_mm = max(int(rec.end_mm or 0) - int(rec.start_mm or 0), 0)

    def _has_layout_tiff_file(self):
        self.ensure_one()
        if self.layout_tiff_filename:
            return True
        Att = self.env['ir.attachment'].sudo()
        return bool(Att.search_count([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_tiff'),
        ]))

    def _has_layout_pdf_file(self):
        self.ensure_one()
        if self.layout_pdf_filename:
            return True
        Att = self.env['ir.attachment'].sudo()
        return bool(Att.search_count([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('res_field', '=', 'layout_pdf'),
        ]))

    def _layout_tiff_download_url(self):
        self.ensure_one()
        return (
            '/web/content?model=dtsc.print.roll.segment&id=%s'
            '&field=layout_tiff&filename_field=layout_tiff_filename&download=true'
        ) % self.id

    def _layout_pdf_download_url(self):
        self.ensure_one()
        return (
            '/web/content?model=dtsc.print.roll.segment&id=%s'
            '&field=layout_pdf&filename_field=layout_pdf_filename&download=true'
        ) % self.id

    def action_download_layout_tiff(self):
        self.ensure_one()
        if not self._has_layout_tiff_file():
            raise UserError(_('此段尚無 TIFF。'))
        return {
            'type': 'ir.actions.client',
            'tag': 'dtsc_print_nesting.download_urls',
            'params': {'urls': [self._layout_tiff_download_url()]},
        }

    def action_download_layout_pdf(self):
        self.ensure_one()
        if not self._has_layout_pdf_file():
            raise UserError(_('此段尚無 PDF。'))
        return {
            'type': 'ir.actions.client',
            'tag': 'dtsc_print_nesting.download_urls',
            'params': {'urls': [self._layout_pdf_download_url()]},
        }
