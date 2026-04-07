from odoo import models, fields,api
from odoo.tools.float_utils import float_round

class WizardMakeTypeSelection(models.TransientModel):
    _name = 'dtsc.maketypeselection'
    _description = "選擇後加工方式"

    product_id = fields.Many2one("product.template", string="產品", required=True)
    make_type_ids = fields.Many2many("dtsc.maketype", string="後加工方式")
    make_type_existing_ids = fields.Many2many("dtsc.maketype", compute="_compute_existing_make_types", store=False)

    @api.depends("product_id")
    def _compute_existing_make_types(self):
        """ 计算当前产品已经有的後加工方式 """
        for record in self:
            existing_make_types = self.env["product.maketype.rel"].search([
                ("product_id", "=", record.product_id.id)
            ]).mapped("make_type_id.id")
            record.make_type_existing_ids = [(6, 0, existing_make_types)]
            
    def action_confirm(self):
        """ 批量创建 product.maketype.rel 记录 """
        self.ensure_one()
        existing_make_type_ids = self.env['product.maketype.rel'].search([
            ('product_id', '=', self.product_id.id)
        ]).mapped('make_type_id.id')

        new_make_types = self.make_type_ids.filtered(lambda m: m.id not in existing_make_type_ids)

        # 批量创建 product.maketype.rel
        vals_list = [{
            'product_id': self.product_id.id,
            'make_type_id': make_type.id,
        } for make_type in new_make_types]

        if vals_list:
            self.env['product.maketype.rel'].create(vals_list)

        return {'type': 'ir.actions.act_window_close'}


class ProductCategory(models.Model):
    _inherit = "product.category"

    default_uom_id = fields.Many2one('uom.uom', string="預設單位")

class ResPartner(models.Model):
    _inherit = "product.template"
    
    unit_conversion_id = fields.Many2one("dtsc.unit_conversion" , string='單位轉換計算')
    
    product_liucheng = fields.Selection([
        ('1', '一次生產完成'),
        ('2', '委外後轉內部生產'),
    ], string='生產流程')
    
    uom_id = fields.Many2one("uom.uom" , string='單位')
    uom_po_id = fields.Many2one("uom.uom" , string='采購計量單位')
    price_fudong = fields.Float(string="浮動價格")
    is_add_mode = fields.Boolean(string="是否有多選屬性")
    make_ori_product_id = fields.Many2one("product.template",string="基礎扣料物",domain=[('purchase_ok',"=",True)],ondelete='cascade')
    
    # multiple_choice_ids = fields.One2many("dtsc.maketypeRel" , "product_id" ,string="後加工明細")
    make_type_ids = fields.One2many("product.maketype.rel" , "product_id" ,string="後加工明細")
    
    def action_open_make_type_selection(self):
        return {
            'name': '選擇後加工屬性',
            'type': 'ir.actions.act_window',
            'res_model': 'dtsc.maketypeselection',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_product_id': self.id},
        }
    
    
    @api.onchange('categ_id')
    def _onchange_categ_id(self):
        """ 当 `categ_id` 变化时，根据分类设置默认 `uom_id` """
        if self.categ_id and self.categ_id.default_uom_id:
            self.uom_id = self.categ_id.default_uom_id
        
        
class ProductMakeTypeRel(models.Model):
    _name='product.maketype.rel'
    sequence = fields.Integer("Sequence")
    product_id = fields.Many2one("product.template","產品")
    make_type_id = fields.Many2one("dtsc.maketype" , "後加工方式",ondelete='cascade')
    name = fields.Char(related="make_type_id.name",store=True,readonly=True)
    
    _sql_constraints = [
        ('product_make_type_unique', 'UNIQUE(product_id, make_type_id)', '同一產品不能選擇重複的後加工方式')
    ]
    
class ProductAttribute(models.Model):
    _inherit = "product.template.attribute.line"
    
    sequence = fields.Integer(string="Sequence", default=1)