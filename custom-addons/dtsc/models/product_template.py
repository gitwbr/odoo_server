from odoo import models, fields, api
from odoo.tools.float_utils import float_round
import logging
from odoo.http import request
_logger = logging.getLogger(__name__)
# from odoo.addons.website.models.mixin import WebsitePublishedMixin
# from odoo.addons.website.models.mixins import WebsitePublishedMixin
from odoo.http import request
from odoo import api
from odoo.tools import config
# class Website(models.Model):

    # _inherit = "website"
    # def get_client_action(self, url, mode_edit=False, website_id=False):
        # self.ensure_one()

        # if url.startswith('/'):
            # base_url = request.httprequest.url_root.replace("http://", "https://")
            # url = url_join(base_url, url)
        # elif url.startswith('http://'):
            # url = url.replace("http://", "https://")

        # _logger.info(f"🔐 重寫 get_client_action：網址 = {url}")

        # action = self.env["ir.actions.actions"]._for_xml_id("website.website_preview")
        # action['context'] = {
            # 'params': {
                # 'path': url,
                # 'enable_editor': mode_edit,
                # 'website_id': website_id,
            # }
        # }
        # return action

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
    
    # def open_website_url(self):
        # self.ensure_one()
        # base_url = request.httprequest.url_root.replace("http://", "https://")
        # full_url = base_url.rstrip('/') + self.website_url

        # _logger.info(f"================{full_url}========")
        # website = self.env['website'].get_current_website()
        # return website.get_client_action(full_url)
    is_open_full_checkoutorder = fields.Boolean(string="簡易流程",compute="_compute_is_open_full_checkoutorder")
    
    @api.depends()
    def _compute_is_open_full_checkoutorder(self):
        for record in self:
            record.is_open_full_checkoutorder = config.get('is_open_full_checkoutorder')
    
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

# class Website(models.Model):

    # _inherit = "website"

    
class ProductProduct(models.Model):
    _inherit = "product.product"
    
    # def open_website_url(self):
        # self.ensure_one()
        # res = self.product_tmpl_id.open_website_url()
        # res['url'] = self.website_url.replace("http:","https:")
        # _logger.info(f"---------{self.website_url}========")
        # _logger.info(f"---------{res['url']}========")
        # return res
        
    def _compute_quantities_dict(self, lot_id, owner_id, package_id, from_date=False, to_date=False):
        domain_quant_loc, domain_move_in_loc, domain_move_out_loc = self._get_domain_locations()
        #bryant add 新增查找数据范围 为物理位置
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        # domain_quant_loc = [('location_id', 'in', [8, 20])]
        domain_quant_loc = [('location_id', 'in', internal_locations.ids)]
        
        
        domain_quant = [('product_id', 'in', self.ids)] + domain_quant_loc
        dates_in_the_past = False
        # only to_date as to_date will correspond to qty_available
        to_date = fields.Datetime.to_datetime(to_date)
        if to_date and to_date < fields.Datetime.now():
            dates_in_the_past = True

        domain_move_in = [('product_id', 'in', self.ids)] + domain_move_in_loc
        domain_move_out = [('product_id', 'in', self.ids)] + domain_move_out_loc
        if lot_id is not None:
            domain_quant += [('lot_id', '=', lot_id)]
        if owner_id is not None:
            domain_quant += [('owner_id', '=', owner_id)]
            domain_move_in += [('restrict_partner_id', '=', owner_id)]
            domain_move_out += [('restrict_partner_id', '=', owner_id)]
        if package_id is not None:
            domain_quant += [('package_id', '=', package_id)]
        if dates_in_the_past:
            domain_move_in_done = list(domain_move_in)
            domain_move_out_done = list(domain_move_out)
        if from_date:
            date_date_expected_domain_from = [('date', '>=', from_date)]
            domain_move_in += date_date_expected_domain_from
            domain_move_out += date_date_expected_domain_from
        if to_date:
            date_date_expected_domain_to = [('date', '<=', to_date)]
            domain_move_in += date_date_expected_domain_to
            domain_move_out += date_date_expected_domain_to

        Move = self.env['stock.move'].with_context(active_test=False)
        Quant = self.env['stock.quant'].with_context(active_test=False)
        domain_move_in_todo = [('state', 'in', ('waiting', 'confirmed', 'assigned', 'partially_available'))] + domain_move_in
        domain_move_out_todo = [('state', 'in', ('waiting', 'confirmed', 'assigned', 'partially_available'))] + domain_move_out
        moves_in_res = dict((item['product_id'][0], item['product_qty']) for item in Move._read_group(domain_move_in_todo, ['product_id', 'product_qty'], ['product_id'], orderby='id'))
        moves_out_res = dict((item['product_id'][0], item['product_qty']) for item in Move._read_group(domain_move_out_todo, ['product_id', 'product_qty'], ['product_id'], orderby='id'))
        quants_res = dict((item['product_id'][0], (item['quantity'], item['reserved_quantity'])) for item in Quant._read_group(domain_quant, ['product_id', 'quantity', 'reserved_quantity'], ['product_id'], orderby='id'))
        if dates_in_the_past:
            # Calculate the moves that were done before now to calculate back in time (as most questions will be recent ones)
            domain_move_in_done = [('state', '=', 'done'), ('date', '>', to_date)] + domain_move_in_done
            domain_move_out_done = [('state', '=', 'done'), ('date', '>', to_date)] + domain_move_out_done
            moves_in_res_past = dict((item['product_id'][0], item['product_qty']) for item in Move._read_group(domain_move_in_done, ['product_id', 'product_qty'], ['product_id'], orderby='id'))
            moves_out_res_past = dict((item['product_id'][0], item['product_qty']) for item in Move._read_group(domain_move_out_done, ['product_id', 'product_qty'], ['product_id'], orderby='id'))

        res = dict()
        for product in self.with_context(prefetch_fields=False):
            origin_product_id = product._origin.id
            product_id = product.id
            if not origin_product_id:
                res[product_id] = dict.fromkeys(
                    ['qty_available', 'free_qty', 'incoming_qty', 'outgoing_qty', 'virtual_available'],
                    0.0,
                )
                continue
            rounding = product.uom_id.rounding
            res[product_id] = {}
            if dates_in_the_past:
                qty_available = quants_res.get(origin_product_id, [0.0])[0] - moves_in_res_past.get(origin_product_id, 0.0) + moves_out_res_past.get(origin_product_id, 0.0)
            else:
                qty_available = quants_res.get(origin_product_id, [0.0])[0]
            reserved_quantity = quants_res.get(origin_product_id, [False, 0.0])[1]
            res[product_id]['qty_available'] = float_round(qty_available, precision_rounding=rounding)
            res[product_id]['free_qty'] = float_round(qty_available - reserved_quantity, precision_rounding=rounding)
            res[product_id]['incoming_qty'] = float_round(moves_in_res.get(origin_product_id, 0.0), precision_rounding=rounding)
            res[product_id]['outgoing_qty'] = float_round(moves_out_res.get(origin_product_id, 0.0), precision_rounding=rounding)
            res[product_id]['virtual_available'] = float_round(
                qty_available + res[product_id]['incoming_qty'] - res[product_id]['outgoing_qty'],
                precision_rounding=rounding)

        return res