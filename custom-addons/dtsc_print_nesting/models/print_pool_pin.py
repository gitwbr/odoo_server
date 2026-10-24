# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PrintPoolPin(models.Model):
    """印刷池圖塊釘選 / 門幅手動指定。

    - pinned=True：座標固定，新單進來重排時不可移動
    - material_id：此塊指定的捲材門幅（拖到其他規格時寫入）
    """
    _name = 'dtsc.print.pool.pin'
    _description = '印刷池圖塊釘選'
    _order = 'makeinline_id, piece_idx'

    makeinline_id = fields.Many2one(
        'dtsc.makeinline',
        string='工單項次',
        required=True,
        ondelete='cascade',
        index=True,
    )
    piece_idx = fields.Integer(string='圖塊序', required=True, default=0)
    material_id = fields.Many2one(
        'product.template',
        string='指定捲材',
        required=True,
        ondelete='restrict',
        index=True,
    )
    pinned = fields.Boolean(
        string='位置釘選',
        default=False,
        help='勾選後重排不會移動此圖塊座標。',
    )
    strip_key = fields.Char(string='長條鍵')
    lot_id = fields.Many2one('stock.lot', string='實體捲', ondelete='set null')
    x_mm = fields.Float(string='X(mm)')
    y_mm = fields.Float(string='Y(mm)')
    width_mm = fields.Float(string='寬(mm)')
    height_mm = fields.Float(string='高(mm)')
    rotated = fields.Boolean(string='已旋轉')
    rotation = fields.Integer(
        string='旋轉角度',
        default=0,
        help='0 / 90 / 180 / 270。與 rotated 同步：90、270 時 rotated=True。',
    )
    flip_h = fields.Boolean(
        string='水平翻轉',
        default=False,
        help='合成 TIFF 時水平鏡像。',
    )

    _sql_constraints = [
        (
            'uniq_makeinline_piece',
            'unique(makeinline_id, piece_idx)',
            '同一項次圖塊序只能有一筆釘選記錄。',
        ),
    ]

    @api.model
    def _pin_key(self, makeinline_id, piece_idx):
        return (int(makeinline_id), int(piece_idx))
