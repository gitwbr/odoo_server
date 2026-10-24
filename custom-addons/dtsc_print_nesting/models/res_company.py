# -*- coding: utf-8 -*-
import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    print_cmyk_icc = fields.Binary(string='印刷 CMYK ICC 描述檔', attachment=True)
    print_cmyk_icc_filename = fields.Char(string='ICC 檔名')

    @api.constrains('print_cmyk_icc')
    def _check_print_cmyk_icc(self):
        for rec in self:
            data = rec.with_context(bin_size=False).print_cmyk_icc
            if not data:
                continue
            try:
                from PIL import ImageCms
                prof = ImageCms.ImageCmsProfile(io.BytesIO(base64.b64decode(data)))
                space = (prof.profile.xcolor_space or '').strip().upper()
            except Exception as err:  # noqa: BLE001
                raise ValidationError(_('無法讀取 ICC 描述檔：%s') % err) from err
            if space != 'CMYK':
                raise ValidationError(_(
                    '上傳的 ICC 色彩空間是 %s，不是 CMYK。請上傳印刷機/RIP 的 CMYK 輸出描述檔。'
                ) % (space or '?'))
