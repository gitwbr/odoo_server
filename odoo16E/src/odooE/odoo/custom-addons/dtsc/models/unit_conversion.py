from odoo import models, fields

# class UnitConversion(models.Model):
    # _name = 'dtsc.unit_conversion'
    # _description = 'Unit Conversion'

    # name = fields.Char(string='Name')
    # value = fields.Float(string='Value')
class UnitConversion(models.Model):
    _name = 'dtsc.unit_conversion'
    _description = '單位換算'

    name = fields.Char('名稱')
    parameter_length = fields.Selection([
        ('1', '1'),
        ('2', '2'),
        ('3', '3'),
    ], string='單位轉換計算參數長度')
    first_unit = fields.Char('第一參數單位')
    second_unit = fields.Char('第二參數單位')
    third_unit = fields.Char('第三參數單位')
    rounding_method = fields.Selection([
    ('round', '四捨五入'),
    ('up', '無條条件進位'),
    ('down', '無條件捨去'),
], string='捨去方法', default='round')
    decimal_places = fields.Integer('小數點位數', default=0)
    conversion_formula = fields.Text('單位轉換計算公式')
    converted_unit_name = fields.Char('轉換後單位名稱')

