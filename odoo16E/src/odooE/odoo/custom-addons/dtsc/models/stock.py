from datetime import datetime, timedelta, date
from odoo.exceptions import AccessDenied, ValidationError
from odoo import models, fields, api
from odoo.fields import Command
from odoo import _
import logging
import math
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import math
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero
from io import BytesIO
import pytz
from pytz import timezone
_logger = logging.getLogger(__name__)
import xlsxwriter
import base64
class StockQuantityHistory(models.TransientModel):
    _name = 'stock.quantity.history'
    _description = 'Stock Quantity History'

    inventory_datetime = fields.Date('庫存日期',
        help="Choose a date to get the inventory at that date",
        default=fields.Date.today)

    def open_at_date(self):

        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        internal_location_ids = internal_locations.ids
        # records = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])
        # for quant in records: 
            # quant.inventory_quantity_set = False
            # quant.inventory_quantity = 0
            # quant.inventory_diff_quantity = 0
    
        # return

        
        self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)]).write({'stock_date': self.inventory_datetime})
        tree_view_id = self.env.ref('stock.view_stock_quant_tree_inventory_editable').id
        
        
        formatted_datetime = self.inventory_datetime.strftime('%Y-%m-%d')
        
        # print(internal_locations)
        # We pass `to_date` in the context so that `qty_available` will be computed across
        # moves until date.
        action = {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id, 'tree')],
            'view_mode': 'tree,form',
            'res_model': 'stock.quant',
            'domain': [('location_id', 'in', internal_location_ids)],
            'context': {'search_default_zskc': 1,'group_by' : 'product_id','default_is_set_date': True},
            'display_name': str(formatted_datetime)+"庫存盤點",
        }
        return action
        
class StockQuant(models.Model):
    _inherit = "stock.quant"
    
    lastmodifydate = fields.Datetime("最後修改時間",compute="_compute_lastmodifydate")
    zksl_cai = fields.Float("在庫數量(才)",compute="_compute_zksl_cai")
    average_price = fields.Float("平均採購價格" , compute="_compute_average_price")
    total_value = fields.Float("成本" , compute="_compute_average_price")
    categ_id = fields.Many2one("product.category",string="產品分類",related="product_id.product_tmpl_id.categ_id",store=True)
    stock_date = fields.Date("指定盤點日期")
    stock_date_num = fields.Float("指定日期庫存",compute="_compute_stock_date_num")
   
    is_set_date = fields.Boolean(store=False)
    
    @api.model
    def is_set_color(self, name):
        return name
    
    # @api.onchange("stock_date")
    # def onchange_stock_date(self):
        # if self.stock_date: 
            # internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
            # self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)]).write({'stock_date': self.stock_date})
            # return {
                # 'type': 'ir.actions.act_window',
                # 'res_model': 'stock.quant',
                # 'view_mode': 'tree,form',
                # 'target': 'current',  # 仅刷新当前视图
            # }
    @api.depends("stock_date_num")
    def _compute_stock_date_num(self):
        for record in self:
            if record.stock_date:
                qty_out = 0
                qty_in = 0
                if record.lot_id:
                    move_lines = self.env['stock.move.line'].search([
                        ('lot_id', '=', record.lot_id.id),
                        ('location_id', '=', record.location_id.id),  # 出库
                        ('state', '=', 'done'),
                        ('date', '>', record.stock_date)
                    ])

                    move_lines_in = self.env['stock.move.line'].search([
                        ('lot_id', '=', record.lot_id.id),
                        ('location_dest_id', '=', record.location_id.id),  # 入库
                        ('state', '=', 'done'),
                        ('date', '>', record.stock_date)
                    ])
                
                    for line in move_lines:
                        if line.product_uom_id.name == "才": #如果卷材是按才扣料 需要转换成卷的百分比
                            tmp = round(line.qty_done / line.product_uom_id.factor , 2)
                            qty_out = qty_out + tmp
                        else:
                            qty_out = qty_out+line.qty_done
                    
                    
                    for line in move_lines_in:

                        if line.product_uom_id.name == "才": #如果卷材是按才扣料 需要转换成卷的百分比
                            tmp = round(line.qty_done / line.product_uom_id.factor , 2)
                            qty_in = qty_in + tmp
                        else:
                            qty_in = qty_in+line.qty_done
                    
                    record.stock_date_num = record.quantity + qty_out - qty_in
                else:
                    move_lines = self.env['stock.move.line'].search([
                        ('product_id', '=', record.product_id.id),
                        ('location_id', '=', record.location_id.id),  # 出库
                        ('state', '=', 'done'),
                        ('date', '>', record.stock_date)
                    ])

                    move_lines_in = self.env['stock.move.line'].search([
                        ('product_id', '=', record.product_id.id),
                        ('location_dest_id', '=', record.location_id.id),  # 入库
                        ('state', '=', 'done'),
                        ('date', '>', record.stock_date)
                    ])
                    qty_out = sum(line.qty_done for line in move_lines)
                    qty_in = sum(line.qty_done for line in move_lines_in)
                    
                    record.stock_date_num = record.quantity + qty_out - qty_in
            else:
                record.stock_date_num = record.quantity
    # @api.depends()
    # def _compute_stock_date(self):
        # for record in self:
            # record.stock_date = datetime.today().date()
    
    # def _inverse_stock_date(self):
        # for record in self:
            # pass
    
    @api.model
    def _update_reserved_quantity(self, product_id, location_id, quantity, lot_id=None, package_id=None, owner_id=None, strict=False):
        """ Increase the reserved quantity, i.e. increase `reserved_quantity` for the set of quants
        sharing the combination of `product_id, location_id` if `strict` is set to False or sharing
        the *exact same characteristics* otherwise. Typically, this method is called when reserving
        a move or updating a reserved move line. When reserving a chained move, the strict flag
        should be enabled (to reserve exactly what was brought). When the move is MTS,it could take
        anything from the stock, so we disable the flag. When editing a move line, we naturally
        enable the flag, to reflect the reservation according to the edition.

        :return: a list of tuples (quant, quantity_reserved) showing on which quant the reservation
            was done and how much the system was able to reserve on it
        """
        self = self.sudo()
        rounding = product_id.uom_id.rounding
        quants = self._gather(product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
        reserved_quants = []

        if float_compare(quantity, 0, precision_rounding=rounding) > 0:
            # if we want to reserve
            available_quantity = sum(quants.filtered(lambda q: float_compare(q.quantity, 0, precision_rounding=rounding) > 0).mapped('quantity')) - sum(quants.mapped('reserved_quantity'))
            if float_compare(quantity, available_quantity, precision_rounding=rounding) > 0:
                raise UserError(_('It is not possible to reserve more products of %s than you have in stock.', product_id.display_name))
        # elif float_compare(quantity, 0, precision_rounding=rounding) < 0:
            # if we want to unreserve
            # available_quantity = sum(quants.mapped('reserved_quantity'))
            # if float_compare(abs(quantity), available_quantity, precision_rounding=rounding) > 0:
                # raise UserError(_('It is not possible to unreserve more products of %s than you have in stock.', product_id.display_name))
        else:
            return reserved_quants

        for quant in quants:
            if float_compare(quantity, 0, precision_rounding=rounding) > 0:
                max_quantity_on_quant = quant.quantity - quant.reserved_quantity
                if float_compare(max_quantity_on_quant, 0, precision_rounding=rounding) <= 0:
                    continue
                max_quantity_on_quant = min(max_quantity_on_quant, quantity)
                quant.reserved_quantity += max_quantity_on_quant
                reserved_quants.append((quant, max_quantity_on_quant))
                quantity -= max_quantity_on_quant
                available_quantity -= max_quantity_on_quant
            else:
                max_quantity_on_quant = min(quant.reserved_quantity, abs(quantity))
                quant.reserved_quantity -= max_quantity_on_quant
                reserved_quants.append((quant, -max_quantity_on_quant))
                quantity += max_quantity_on_quant
                available_quantity += max_quantity_on_quant

            if float_is_zero(quantity, precision_rounding=rounding) or float_is_zero(available_quantity, precision_rounding=rounding):
                break
        return reserved_quants
    
    def action_set_inventory_quantity_to_zero(self):
        self.inventory_quantity = 0
        self.inventory_diff_quantity = 0
        self.inventory_quantity_set = False
    
    
    @api.depends('inventory_quantity','stock_date')
    def _compute_inventory_diff_quantity(self):
        for quant in self: 
            if quant.inventory_quantity_set == False:
                quant.inventory_diff_quantity = 0  
                continue
                
            if self.env.context.get('default_is_set_date') is True:  
                quant.inventory_diff_quantity = quant.inventory_quantity - quant.stock_date_num
            else:
                quant.inventory_diff_quantity = quant.inventory_quantity - quant.quantity 
    
    @api.depends('quantity')
    def _compute_average_price(self):
        for record in self:
            if record.lot_id:#如果是有批次的產品
                purchase_line = self.env['purchase.order.line'].search([
                    ('product_id', '=', record.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done']),
                    ('order_id',"=",record.lot_id.purchase_order_id.id)
                    ], order='date_order desc',limit=1)
                    
                if purchase_line:
                    # record.average_price = purchase_line.price_unit
                    if purchase_line.price_unit == 0:
                        record.average_price = purchase_line.product_id.standard_price
                    else:
                        record.average_price = purchase_line.price_unit
                    record.total_value = record.quantity * record.average_price
                else:#如果找不到相同序號的 ，則找最近一個相同產品的
                    # lot_purchase_lines_other = self.env['purchase.order.line'].search([
                    # ('product_id', '=', record.product_id.id),
                    # ('order_id.state', 'in', ['purchase', 'done'])
                    # ], order='date_order desc', limit=1)
                    # record.average_price = lot_purchase_lines_other.price_unit
                    record.average_price = record.product_id.standard_price
                    record.total_value = record.quantity * record.average_price
                    
            else:#無批次產品
                total_value = 0.0
                average_price = 0.0
                total_qty_needed = record.quantity
                purchase_lines = self.env['purchase.order.line'].search([
                    ('product_id', '=', record.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                ], order='date_order desc')

                qty_consumed = 0
                if not purchase_lines:
                    average_price = record.product_id.standard_price
                    total_value = average_price * total_qty_needed
                else:
                    for line in purchase_lines:
                        if total_qty_needed <= 0:
                            break
                        purchase_qty = line.product_qty
                        purchase_price = 0
                        if line.price_unit != 0:
                            purchase_price = line.price_unit
                        else:
                            purchase_price = line.product_id.standard_price
                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty

                    average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0
            
                record.average_price = average_price
                record.total_value = total_value

    
    @api.depends('quantity')
    def _compute_zksl_cai(self):
        for record in self:
            if record.lot_id:
                uom_obj = self.env["uom.uom"]
                uom_record = uom_obj.browse(record.product_uom_id.id)
                now_category_id = uom_record.category_id.id
                other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                record.zksl_cai = round(record.quantity * other_uom.factor,1)
            else:
                record.zksl_cai = 0
    
    def _domain_product_id(self):
        if not self._is_inventory_mode():
            return
        domain = [('type', '=', 'product'), ('product_tmpl_id.purchase_ok', '=', True)]
        if self.env.context.get('product_tmpl_ids') or self.env.context.get('product_tmpl_id'):
            products = self.env.context.get('product_tmpl_ids', []) + [self.env.context.get('product_tmpl_id', 0)]
            domain = expression.AND([domain, [('product_tmpl_id', 'in', products)]])
        return domain
        
    @api.depends('quantity', 'product_id.stock_move_ids', 'lot_id')
    def _compute_lastmodifydate(self):
        for record in self:
            domain = [('product_id', '=', record.product_id.id)]
            if record.lot_id:
                domain.append(('lot_id', '=', record.lot_id.id))

            move_lines = self.env['stock.move.line'].search(
                domain, order='date desc', limit=1)
            if move_lines:
                record.lastmodifydate = move_lines.date
            else: 
                record.lastmodifydate = None
    

    
    def _get_inventory_move_values(self, qty, location_id, location_dest_id, out=False, date=False):
        self.ensure_one()
        if fields.Float.is_zero(qty, 0, precision_rounding=self.product_uom_id.rounding):
            name = _('Product Quantity Confirmed')
        else:
            name = _('Product Quantity Updated')

        # 使用传入的日期，如果未传入，则保持原行为
        move_date = date or fields.Datetime.now()

        return {
            'name': self.env.context.get('inventory_name') or name,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': qty,
            'company_id': self.company_id.id or self.env.company.id,
            'state': 'confirmed',
            'location_id': location_id.id,
            'location_dest_id': location_dest_id.id,
            'is_inventory': True,
            'date': move_date,  # 在 stock.move 上设置日期
            'move_line_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'product_uom_id': self.product_uom_id.id,
                'qty_done': qty,
                'location_id': location_id.id,
                'location_dest_id': location_dest_id.id,
                'company_id': self.company_id.id or self.env.company.id,
                'lot_id': self.lot_id.id,
                'package_id': out and self.package_id.id or False,
                'result_package_id': (not out) and self.package_id.id or False,
                'owner_id': self.owner_id.id,
                'date': move_date,  # 在 stock.move.line 上设置日期
            })]
        }    
        
    def confirm_btn(self,mpr_id):
        quant = self.env["stock.quant"].search([('product_id' , "=" , mpr_id.product_id.id),("lot_id" ,"=" , mpr_id.product_lot.id),("location_id" ,"=" ,mpr_id.stock_location_id.id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
        mpr_id.write({'final_stock_num': str(round(quant.quantity,3))})        
        picking = self.env['stock.picking'].create({
            'picking_type_id' : 1,
            'location_id': mpr_id.stock_location_id.id,  #库存
            'location_dest_id': 15, #Production 用于生产
            'origin' : mpr_id.name, 
        })
        mpr_id.picking_id = picking.id
        move = self.env['stock.move'].create({
            'name' : mpr_id.name,
            'reference' : "捲料完成", 
            'product_id': mpr_id.product_id.id,
            'product_uom_qty' : quant.quantity,
            'product_uom' : mpr_id.uom_id.id,
            "picking_id" : picking.id,
            "quantity_done" : quant.quantity,
            'origin' : mpr_id.name,
            'location_id': mpr_id.stock_location_id.id,  #库存
            'location_dest_id': 15, #Production 用于生产                
        })
        mpr_id.stock_move_id = move.id
        
        # stock_lot_obj = self.env['stock.lot'].search([('barcode', '=', self.name)],limit=1)
        move_line = self.env['stock.move.line'].create({
            'reference' : "捲料完成"+mpr_id.name, 
            'origin' : mpr_id.name,
            "move_id": move.id, 
            "picking_id" : picking.id,
            'product_id': mpr_id.product_id.id,
            'qty_done': quant.quantity ,
            'product_uom_id' : mpr_id.uom_id.id,                
            'location_id': mpr_id.stock_location_id.id,  #库存
            'location_dest_id': 15, #Production 用于生产 
            'lot_name' : mpr_id.product_lot.name,
            'lot_id': mpr_id.product_lot.id,
            'state': "draft", 
        })                
        mpr_id.stock_move_line_id = [(4, move_line.id)]
        move_line_objs = self.env['stock.move.line'].search(["|",("lot_id" ,"=" , False ),("lot_name" ,"=" , False ),("product_id" , "=" ,mpr_id.product_id.id ),('picking_id',"=", picking.id)])
        move_line_objs.unlink()
        
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate() 
        mpr_id.write({'state': "succ"})
        local_tz = pytz.timezone('Asia/Shanghai')  # 替換為你所在的時區
        
        today = datetime.now(local_tz).date()
        mpr_id.succ_date = today
    
    def ok_btn(self,mpr_id,quant):
        count = 0
        for record in mpr_id.lotmprline_id:
            if record.state == "succ":
                continue
            if record.shengyu == 0:
                count = count + 1
        
        if count > 1:
            raise ValidationError("扣料超過2個項次多于此料，請檢查，如需用備料請加入備料序號，保留一個多餘項次!")
    
    
        uom_obj = self.env["uom.uom"]
        
        #當前庫存
        
        uomid = mpr_id.uom_id.id
        uom_record = uom_obj.browse(mpr_id.uom_id.id)
        now_category_id = uom_record.category_id.id
        other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
        if other_uom:
            uomid = other_uom.id
        
        # _logger.info("======")
        # _logger.info(self.id)
        # _logger.info(self.lot_stock_num)
        # _logger.info("======")
        if mpr_id.lot_stock_num.isdigit():  # 检查是否是数字
            if int(mpr_id.lot_stock_num) < 0:
                raise ValidationError("此料無庫存!")
        elif mpr_id.lot_stock_num == "無":  # 检查是否为字符串 "無"
            raise ValidationError("此料無庫存!")
        
        now_stock_p = float(mpr_id.lot_stock_num) * other_uom.factor
        for record in mpr_id.lotmprline_id:
            if record.state == "succ":
                continue
            
            if record.sjkl == 0:
                qty_done_cai = record.yujixiaohao
            else: 
                qty_done_cai = record.sjkl


            # if (now_stock_p - record.yujixiaohao) < 0 :
            if (now_stock_p - qty_done_cai) < 0 :
                raise ValidationError("捲料:%s存在未能扣除的項次,請去捲料扣料表扣料!" % (quant.lot_id.barcode))  
            

            # _logger.info("===========================")
            # _logger.info(record.name)
            # _logger.info(qty_done_cai)
            # _logger.info(mpr_id.name)
            now_stock_p = now_stock_p - qty_done_cai
            picking = self.env['stock.picking'].create({
                'picking_type_id' : 1,
                'location_id': mpr_id.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产
                'origin' : record.name, 
            })
            record.picking_id = picking.id
            move = self.env['stock.move'].create({
                'name' : record.name,
                'reference' : "庫存盤點捲料扣料", 
                'product_id': mpr_id.product_id.id,
                'product_uom_qty' : qty_done_cai,
                'product_uom' : uomid,
                "picking_id" : picking.id,
                "quantity_done" : qty_done_cai,
                'origin' : record.name,
                'location_id': mpr_id.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产                
            })
            record.stock_move_id = move.id
            
            stock_lot_obj = self.env['stock.lot'].search([('barcode', '=', mpr_id.name)],limit=1)
            # _logger.info(quant.lot_id.name)
            # _logger.info(quant.lot_id.id)
            # _logger.info("===========================")
            move_line = self.env['stock.move.line'].create({
                'reference' : "庫存盤點捲料扣料", 
                'origin' : record.name,
                "move_id": move.id, 
                "picking_id" : picking.id,
                'product_id': mpr_id.product_id.id,
                'qty_done': qty_done_cai ,
                'product_uom_id' : uomid,                
                'location_id': mpr_id.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产 
                'lot_name' : quant.lot_id.name,
                'lot_id': quant.lot_id.id,
                'state': "draft",
            })                
            record.stock_move_line_id = [(4, move_line.id)]
            # move_line_objs = self.env['stock.move.line'].search(["|",("lot_id" ,"=" , False ),("lot_name" ,"=" , False ),("product_id" , "=" ,mpr_id.product_id.id ),('picking_id',"=", picking.id)])
            # move_line_objs.unlink()
            
            picking.action_confirm()
            picking.action_assign()
            picking.button_validate() 
            _logger.info("====---------------======")
            record.state = "succ" 
            record.sjkl = qty_done_cai 
    
    def action_apply_inventory(self):
        products_tracked_without_lot = []
        all_past_inventory = True
        move_vals = []
        past_date = ""
        
        for quant in self:
            if not self.env.context.get('default_is_set_date') is True: 
                if quant.lot_id and quant.inventory_quantity == 0 and quant.inventory_diff_quantity != 0:
                    obj = self.env['dtsc.lotmpr']
                    is_has_mpr = obj.search([('product_lot',"=",quant.lot_id.id)],limit=1)
                    if not is_has_mpr:
                        mpr_id = obj.create({
                           'name' : quant.lot_id.barcode, 
                           'product_id' : quant.lot_id.product_id.id,
                           'product_lot' : quant.lot_id.id,
                           'lot_stock_num' : str(quant.quantity),
                        })
                        _logger.info(f"================{mpr_id.id}")
                        self.env['dtsc.lotmprline'].create({
                           'name' : "邊料損耗", 
                           'yujixiaohao' : 25,
                           'sjkl' : 25,
                           "lotmpr_id" : mpr_id.id,
                        })
                        self.ok_btn(mpr_id,quant)
                        self.confirm_btn(mpr_id)
                    else:
                        self.ok_btn(is_has_mpr,quant)
                        self.confirm_btn(is_has_mpr)
                    continue
            
            
            if self.env.context.get('default_is_set_date') is True:  
                # quant.stock_date = fields.Date.today()
                
            # if quant.stock_date.strftime('%Y-%m-%d') != datetime.today().strftime('%Y-%m-%d'):
                past_date = quant.stock_date
                rounding = quant.product_uom_id.rounding
                # 计算需要调整的库存差异
                inventory_diff = quant.inventory_diff_quantity
                if float_compare(inventory_diff, 0, precision_rounding=rounding) == 0:
                    continue  # 如果没有差异，跳过

                # 创建库存调整的 stock.move 数据
                if inventory_diff > 0:
                    # print(inventory_diff)
                    move_vals.append(
                        quant._get_inventory_move_values(
                            inventory_diff,
                            quant.product_id.with_company(quant.company_id).property_stock_inventory,
                            quant.location_id,
                            date=past_date
                        )
                    )
                else:
                    move_vals.append(
                        quant._get_inventory_move_values(
                            -inventory_diff,
                            quant.location_id,
                            quant.product_id.with_company(quant.company_id).property_stock_inventory,
                            out=True,
                            date=past_date
                        )
                    )
            else:
                all_past_inventory = False                
                rounding = quant.product_uom_id.rounding
                if fields.Float.is_zero(quant.inventory_diff_quantity, precision_rounding=rounding)\
                        and fields.Float.is_zero(quant.inventory_quantity, precision_rounding=rounding)\
                        and fields.Float.is_zero(quant.quantity, precision_rounding=rounding):
                    continue
                if quant.product_id.tracking in ['lot', 'serial'] and\
                        not quant.lot_id and quant.inventory_quantity != quant.quantity and not quant.quantity:
                    products_tracked_without_lot.append(quant.product_id.id)
        
        if all_past_inventory:
            # past_date = datetime.today()
            moves = self.env['stock.move'].with_context(inventory_mode=False).create(move_vals)
            moves._action_done()
            
            for move in moves:
                move.write({'date': past_date})
                for line in move.move_line_ids:
                    line.write({'date': past_date})  # 确保 move_line 的日期为指定的盘点日期
            # 更新库存盘点日期和当前状态
            self.location_id.write({'last_inventory_date': past_date})
            self.write({
                'inventory_quantity': False,
                'user_id': False,
                'inventory_quantity_set': False,
                'inventory_diff_quantity': 0
            })
            # if self.ids:
                # self.env.cr.execute("""
                    # UPDATE stock_quant
                    # SET inventory_quantity = NULL
                    # WHERE id IN %s
                # """, (tuple(self.ids),))
            return
        
        # for some reason if multi-record, env.context doesn't pass to wizards...
        ctx = dict(self.env.context or {})
        ctx['default_quant_ids'] = self.ids
        quants_outdated = self.filtered(lambda quant: quant.is_outdated)
        if quants_outdated:
            ctx['default_quant_to_fix_ids'] = quants_outdated.ids
            return {
                'name': _('Conflict in Inventory Adjustment'),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_model': 'stock.inventory.conflict',
                'target': 'new',
                'context': ctx,
            }
        if products_tracked_without_lot:
            ctx['default_product_ids'] = products_tracked_without_lot
            return {
                'name': _('Tracked Products in Inventory Adjustment'),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'views': [(False, 'form')],
                'res_model': 'stock.track.confirmation',
                'target': 'new',
                'context': ctx,
            }
        self._apply_inventory()
        self.inventory_quantity_set = False
        
    @api.model_create_multi
    def create(self, vals_list):
        """ Override to handle the "inventory mode" and create a quant as
        superuser the conditions are met.
        """
        quants = self.env['stock.quant']
        is_inventory_mode = self._is_inventory_mode()
        allowed_fields = self._get_inventory_fields_create()
        for vals in vals_list:
            vals.pop('stock_date',None)
            vals.pop('is_set_date',None)
            if is_inventory_mode and any(f in vals for f in ['inventory_quantity', 'inventory_quantity_auto_apply']):
                if any(field for field in vals.keys() if field not in allowed_fields):
                    _logger = logging.getLogger(__name__)
                    _logger.info(f"is_inventory_mode: {is_inventory_mode}")
                    _logger.info(f"vals: {vals}")
                    _logger.info(f"allowed_fields: {allowed_fields}")
                    raise UserError(_("Quant's creation is restricted, you can't do this operation."))
                auto_apply = 'inventory_quantity_auto_apply' in vals
                inventory_quantity = vals.pop('inventory_quantity_auto_apply', False) or vals.pop(
                    'inventory_quantity', False) or 0
                # Create an empty quant or write on a similar one.
                product = self.env['product.product'].browse(vals['product_id'])
                location = self.env['stock.location'].browse(vals['location_id'])
                lot_id = self.env['stock.lot'].browse(vals.get('lot_id'))
                package_id = self.env['stock.quant.package'].browse(vals.get('package_id'))
                owner_id = self.env['res.partner'].browse(vals.get('owner_id'))
                quant = self.env['stock.quant']
                if not self.env.context.get('import_file'):
                    # Merge quants later, to make sure one line = one record during batch import
                    quant = self._gather(product, location, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=True)
                if lot_id:
                    quant = quant.filtered(lambda q: q.lot_id)
                if quant:
                    quant = quant[0].sudo()
                else:
                    quant = self.sudo().create(vals)
                if auto_apply:
                    quant.write({'inventory_quantity_auto_apply': inventory_quantity})
                else:
                    # Set the `inventory_quantity` field to create the necessary move.
                    quant.inventory_quantity = inventory_quantity
                    quant.user_id = vals.get('user_id', self.env.user.id)
                    quant.inventory_date = fields.Date.today()
                quants |= quant
            else:
                quant = super().create(vals)
                quants |= quant
                if self._is_inventory_mode():
                    quant._check_company()
        return quants

class Productproduct(models.Model):
    _inherit = "product.product"
    
    sec_uom_id = fields.Many2one("uom.uom")
    average_price = fields.Float("平均採購價格" , compute="_compute_average_price")
    total_value = fields.Float("總計金額" , compute="_compute_average_price",store=True)
    
    @api.depends('qty_available','standard_price')
    def _compute_average_price(self):
        for record in self:
            total_value = 0.0
            average_price = 0.0
            total_qty_needed = record.qty_available
            purchase_lines = self.env['purchase.order.line'].search([
                ('product_id', '=', record.id),
                ('order_id.state', 'in', ['purchase', 'done'])
            ], order='date_order desc')

            qty_consumed = 0
            if not purchase_lines:
                average_price = record.standard_price
            else:
                for line in purchase_lines:
                    if total_qty_needed <= 0:
                        break
                    purchase_qty = line.product_qty
                    purchase_price = 0
                    if line.price_unit != 0:
                        purchase_price = line.price_unit
                    else:
                        purchase_price = line.product_id.standard_price
                    if purchase_qty >= total_qty_needed:
                        total_value += total_qty_needed * purchase_price
                        qty_consumed += total_qty_needed
                        total_qty_needed = 0
                    else:
                        total_value += purchase_qty * purchase_price
                        qty_consumed += purchase_qty
                        total_qty_needed -= purchase_qty

                average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0
        
            record.average_price = average_price
            record.total_value = average_price * record.qty_available
    
    
    
    
    
    
class StockMove(models.Model):
    _inherit = "stock.move"
    
    reference = fields.Char(compute='_compute_reference_new', string="Reference", store=True)
    
    @api.depends('picking_id', 'name')
    def _compute_reference_new(self):
        for move in self:
            if move.reference:
                move.reference = move.reference
            else:
                move.reference = move.picking_id.name if move.picking_id else move.name
        
        
class Mpr(models.Model):
    _name = "dtsc.mpr"
    _order = "name desc"
    name = fields.Char("單號")
    from_name = fields.Char("銷售單號")
    state = fields.Selection([
        ("draft","待扣料"),
        ("succ","扣料完成"),   
    ],default='draft' ,string="狀態")
    mprline_ids = fields.One2many("dtsc.mprline" , "mpr_id")
    picking_id = fields.Many2one("stock.picking")
    stock_move_id = fields.Many2one("stock.move")
    stock_move_line_id = fields.Many2many("stock.move.line")
    stock_location_id = fields.Many2one("stock.location", string="同步所有倉庫項次",domain=[('usage', '=', 'internal')] ,default = 8 )
    
    @api.onchange('stock_location_id')
    def _onchange_stock_location_id(self): 
        for record in self:
            for mprline in record.mprline_ids:
                mprline.write({
                    'stock_location_id': record.stock_location_id.id  # 更新 mprline 的 stock_location_id
                })
    
    
    def back_btn(self):
        self.ensure_one()
        if not self.picking_id or self.picking_id.state != 'done':
            raise UserError('无有效的完成拣货操作，无法回退。')

        # 创建逆向拣货记录
        reverse_picking_vals = {
            'picking_type_id': self.picking_id.picking_type_id.id,
            'origin': '退回 ' + self.name.replace("W","B"),
        }
        reverse_picking = self.env['stock.picking'].create(reverse_picking_vals)
        
        
        for move in self.picking_id.move_ids:
        
            reverse_move_vals = {
                'name': move.name,
                'reference': "退回" + self.name.replace("W","B"),
                'origin' : self.name.replace("W","B"),
                'product_id': move.product_id.id,
                'product_uom_qty': move.product_uom_qty,
                'quantity_done': move.quantity_done,
                'product_uom': move.product_uom.id,
                'picking_id': reverse_picking.id,
                'location_id': move.location_dest_id.id,
                'location_dest_id': move.location_id.id,
            }
            reverse_move = self.env['stock.move'].create(reverse_move_vals)
            # print(line.id)  
            # 处理序列号
            for move_line in move.move_line_ids:
                if move_line.lot_id:
                    reverse_move_line_vals = {
                        'reference' : "退回"+self.name.replace("W","B"), 
                        'origin' : self.name.replace("W","B"),
                        'move_id': reverse_move.id,
                        'product_id': move_line.product_id.id,
                        'product_uom_id': move_line.product_uom_id.id,
                        'picking_id': reverse_picking.id,
                        'reserved_uom_qty': move_line.qty_done,
                        'qty_done': move_line.qty_done,
                        'lot_id': move_line.lot_id.id,  # 指定序列号
                        'location_id': move_line.location_dest_id.id,
                        'location_dest_id': move_line.location_id.id,
                    }
                    moveline  = self.env['stock.move.line'].create(reverse_move_line_vals)
                    move_line_objs = self.env['stock.move.line'].search([("product_id" , "=" ,move_line.product_id.id ),("lot_id" ,"=" , False ),('picking_id',"=", reverse_picking.id)])
                    move_line_objs.unlink()
            
   
        # 确认并完成逆向拣货
        reverse_picking.action_confirm()
        reverse_picking.action_assign()
        reverse_picking.button_validate()
        
        
        self.write({'state': 'draft'})
    
    def floor_to_one_decimal_place(self,number):
        return math.floor(number * 10) / 10
        
        
    def confirm_btn(self):
        if not self.mprline_ids:
            self.write({"state": "succ"})
            return
    
        for record in self.mprline_ids:
            if record.product_product_id.product_tmpl_id.tracking == "serial": #如果這個產品設定的是有唯一序列號的 則需要選擇序號
                if not record.product_lot:
                    raise UserError('%s 還未選擇正確的序號！' %record.product_product_id.name)
                  
            if record.final_use < 0:
                raise UserError('%s 扣料必須大於0！' %record.product_product_id.name)
            elif record.final_use == 0:
                record.final_use = record.now_use
                
        # now_stock_location_id = self.stock_location_id.id       
        picking = self.env['stock.picking'].create({
            # 'name':self.name.replace("W","B/W/"),
            'picking_type_id' : 1,
            # 'location_id': now_stock_location_id,  #库存
            'location_dest_id': 15, #Production 用于生产
            'origin' : self.name.replace("W","B"),
        })
        
        self.write({'picking_id': picking.id})
        uom_obj = self.env["uom.uom"]
        
        for record in self.mprline_ids:
            if not record.product_product_id:
                continue
            uomid = record.uom_id.id
            
            if "卷" in record.uom_id.name:
                uom_record = uom_obj.browse(record.uom_id.id)
                now_category_id = uom_record.category_id.id
                other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                uomid = other_uom.id
            
            final_use = record.final_use
            # if record.product_lot: 
                # quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_product_id.id),("lot_id" ,"=" , record.product_lot.id),("location_id" ,"=" ,now_stock_location_id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
                # if quant:
                    # uom_record = uom_obj.browse(record.uom_id.id)
                    # now_category_id = uom_record.category_id.id
                    # other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                    # if other_uom.name == "才":
                        # if quant.quantity * other_uom.factor < record.final_use:
                            # raise UserError('%s 實際扣料大於庫存！' %record.product_product_id.name)
                            # final_use = self.floor_to_one_decimal_place(quant.quantity * other_uom.factor)
                                        
                    # if record.is_all == True:
                        # uomid = record.uom_id.id
                        # final_use = quant.quantity
            
            move = self.env['stock.move'].create({
                'name' : self.name.replace("W","B/W/"),
                'reference' : "工單扣料"+self.name.replace("W","B"), 
                'product_id': record.product_product_id.id,
                'product_uom_qty' : final_use,
                'product_uom' : uomid,
                "picking_id" : picking.id,
                "quantity_done" : final_use,
                'origin' : self.name.replace("W","B"),
                'location_id': record.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产                
            })
            self.write({'stock_move_id': move.id})
            
            if record.product_lot:    
                # move_line_obj = self.env['stock.move.line'].browse(move.id)
                move_line = self.env['stock.move.line'].create({
                    'reference' : "工單扣料"+self.name.replace("W","B"), 
                    'origin' : self.name.replace("W","B"),
                    "move_id": move.id, 
                    "picking_id" : picking.id,
                    'product_id': record.product_product_id.id,
                    'qty_done': final_use ,
                    'product_uom_id' : uomid,                
                    'location_id': record.stock_location_id.id,  #库存
                    'location_dest_id': 15, #Production 用于生产 
                    'lot_name' : record.product_lot.name,
                    'lot_id': record.product_lot.id,
                    'state': "draft",
                })                
                self.stock_move_line_id = [(4, move_line.id)]
                move_line_objs = self.env['stock.move.line'].search(["|",("lot_id" ,"=" , False ),("lot_name" ,"=" , False ),("product_id" , "=" ,record.product_product_id.id ),('picking_id',"=", picking.id)])
                move_line_objs.unlink()
        picking.action_confirm()
        picking.action_assign()
        picking.button_validate() 
        
        self.write({"state":"succ"})
    
class MprLine(models.Model):
    _name = "dtsc.mprline"
    
    mpr_id = fields.Many2one("dtsc.mpr")
    # final_use_readonly = fields.Boolean(compute='_compute_final_use_readonly', default=False, store=False)
    purchase_product_id = fields.Many2one("dtsc.checkout",readonly=True)
    product_product_id = fields.Many2one("product.product" , "物料名稱")
    product_lot = fields.Many2one("stock.lot" , "產品序號")
    product_id_formake=fields.Many2one('product.template',readonly=True) 
    product_id = fields.Many2one("product.template" , "製作物" ,readonly = True)
    attr_name = fields.Char("屬性名",readonly=True)
    uom_id = fields.Many2one('uom.uom',string="單位")
    now_use = fields.Float("預計消耗" ,readonly=True)
    final_use = fields.Float("實際消耗")
    lot_stock_num = fields.Char(string = "單序號庫存" ,compute = '_compute_lot_stock_num')
    now_stock = fields.Char(string='總庫存',compute = '_compute_now_stock' ,readonly=True)
    barcode_input = fields.Char("條碼輸入")
    comment = fields.Char("備註")
    is_all = fields.Boolean("扣除餘料")
    stock_location_id = fields.Many2one("stock.location", string="倉庫",domain=[('usage', '=', 'internal')] ,default = 8 )

    
    ####权限
    is_in_by_mg = fields.Boolean(compute='_compute_is_in_by_mg')
    
    def floor_to_one_decimal_place(self,number):
        return math.floor(number * 10) / 10
    
    @api.onchange("is_all")
    def change_is_all(self): 
        uom_obj = self.env["uom.uom"]    
        for record in self:
            if self.is_all == True:
                if record.product_lot.id:
                
                    quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_product_id.id),("lot_id" ,"=" , record.product_lot.id),("location_id" ,"=" ,8)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
                
                    if quant:
                        uom_record = uom_obj.browse(record.uom_id.id)
                        now_category_id = uom_record.category_id.id
                        other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                        if other_uom.name == "才":
                            record.final_use = self.floor_to_one_decimal_place(quant.quantity * other_uom.factor)
                        else:
                            record.final_use = quant.quantity
                    else:
                        raise UserError('該序號產品沒有庫存。')
                else:
                    raise UserError('非序號產品無法扣除餘料。')
    
    @api.depends("product_product_id")
    def _compute_is_in_by_mg(self):
        group_dtsc_mg = self.env.ref('dtsc.group_dtsc_mg', raise_if_not_found=False)
        user = self.env.user
        #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        self.is_in_by_mg = group_dtsc_mg and user in group_dtsc_mg.users
        
    is_in_by_sc = fields.Boolean(compute='_compute_is_in_by_sc')

    @api.depends("product_product_id")
    def _compute_is_in_by_sc(self):
        group_dtsc_sc = self.env.ref('dtsc.group_dtsc_sc', raise_if_not_found=False)
        user = self.env.user
        #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        self.is_in_by_sc = group_dtsc_sc and user in group_dtsc_sc.users
        
    is_in_by_ck = fields.Boolean(compute='_compute_is_in_by_ck')

    @api.depends("product_product_id")
    def _compute_is_in_by_ck(self):
        group_dtsc_ck = self.env.ref('dtsc.group_dtsc_ck', raise_if_not_found=False)
        user = self.env.user
        #_logger.info(f"Current user: {user.name}, ID: {user.id}")
        #is_in_group_dtsc_mg = group_dtsc_mg and user in group_dtsc_mg.users

        # 打印调试信息
        #_logger.info(f"User '{user.name}' is in DTSC MG: {is_in_group_dtsc_mg}, is in DTSC GLY: {is_in_group_dtsc_gly}")
        self.is_in_by_ck = group_dtsc_ck and user in group_dtsc_ck.users
    ####权限
    
    @api.model
    def create(self, vals):
        mpr_record = self.env['dtsc.mpr'].browse(vals.get('mpr_id'))
        if mpr_record.state == 'succ':
            raise UserError('不允許在此狀態下添加記錄。')
        return super(MprLine, self).create(vals)

    def write(self, vals):
        if self.mpr_id.state == 'succ':
            raise UserError('不允許在此狀態下修改記錄。')
        return super(MprLine, self).write(vals)

    def unlink(self):
        if any(line.mpr_id.state == 'succ' for line in self):
            raise UserError('不允許在此狀態下刪除記錄。')
        return super(MprLine, self).unlink()

    @api.onchange('barcode_input')
    def _onchange_barcode_input(self):
        if self.barcode_input:
            parts = self.barcode_input.split('-')
            if len(parts) > 2:
                # 假设 a 是 product_product_id 的外部 ID
                product = self.env['product.product'].search([('default_code', '=', parts[0])])
                if product:
                    self.product_product_id = product.id
                # 假设 b 是 product_lot 的名称
                # lot = self.env['stock.lot'].search([('name', '=', parts[1]+"-"+parts[2])])
                lot = self.env['stock.lot'].search([('barcode', '=', self.barcode_input)])
                if lot:
                    self.product_lot = lot.id

    
    @api.onchange("product_product_id")
    def change_uom(self):
        for record in self:
            if self.product_product_id:
                self.uom_id = self.product_product_id.uom_id.id
    
    
    @api.depends('product_id','product_product_id',"product_lot")
    def _compute_lot_stock_num(self):
        uom_obj = self.env["uom.uom"]
        for record in self:
            if record.product_lot.id:
            
                quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_product_id.id),("lot_id" ,"=" , record.product_lot.id),("location_id" ,"=" ,8)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
            
                if quant:
                    uom_record = uom_obj.browse(record.uom_id.id)
                    now_category_id = uom_record.category_id.id
                    other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                    if other_uom.name == "才":
                        # record.lot_stock_num = str(round(quant.quantity,1)) + "(" + str(round(quant.quantity * other_uom.factor,1)) +" 才)"
                        record.lot_stock_num = str(round(quant.quantity,3)) + "(" + str(self.floor_to_one_decimal_place(quant.quantity * other_uom.factor)) +" 才)"
                    else:
                        record.lot_stock_num = quant.quantity
                else:
                    record.lot_stock_num = "無"
            else:
                record.lot_stock_num = "無"
                
    @api.depends('product_id','product_product_id','stock_location_id')
    def _compute_now_stock(self):
        for record in self:
            # print(record.mpr_id.stock_location_id.id)
            # print(record.product_product_id.id)
            quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_product_id.id),("location_id" ,"=" ,record.stock_location_id.id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
            if quant:
                record.now_stock = quant.quantity
            else:
                record.now_stock = "0"
         

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'
    
    description = fields.Text(string="採購描述" , related="move_id.purchase_line_id.name")
    move_before_quantity = fields.Float("移動前")
    move_after_quantity = fields.Float("移動後",compute="_compute_move_after_quantity",store=True)
    location_ori = fields.Many2one("stock.location",compute="_compute_move_after_quantity",store=True)
    report_year = fields.Many2one("dtsc.year",string="年",compute="_compute_year_month",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",compute="_compute_year_month",store=True) 
    
    def action_printexcel_move_line(self):
        active_ids = self._context.get('active_ids')
        records = self.env['stock.move.line'].browse(active_ids)
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('盤點損耗表')
        bold_format = workbook.add_format({'bold': True, 'font_size': 14})
        worksheet.set_column('A:A', 20) 
        worksheet.set_column('B:B', 30) 
        worksheet.set_column('C:C', 40) 
        worksheet.set_column('D:D', 20) 
        worksheet.set_column('E:E', 15) 
        worksheet.set_column('F:F', 15) 
        worksheet.set_column('G:G', 15) 
        worksheet.set_column('H:H', 15) 
        # 写入表头
        worksheet.write(0, 0, '日期', bold_format)
        worksheet.write(0, 1, '參照', bold_format)
        worksheet.write(0, 2, '產品', bold_format)
        worksheet.write(0, 3, '序號', bold_format)
        worksheet.write(0, 4, '倉庫', bold_format)
        worksheet.write(0, 5, '移動前', bold_format)
        worksheet.write(0, 6, '移動後', bold_format)
        worksheet.write(0, 7, '完成', bold_format)
        worksheet.write(0, 8, '量度單位', bold_format)
        row = 1
        for record in records:
            worksheet.write(row, 0, record.date.strftime('%Y-%m-%d %H:%M:%S'))
            worksheet.write(row, 1, record.reference if record.reference else "")
            worksheet.write(row, 2, record.product_id.name if record.product_id else "")
            worksheet.write(row, 3, record.lot_id.name if record.lot_id else "")
            worksheet.write(row, 4, record.location_ori.name if record.location_ori else "")
            worksheet.write(row, 5, str(round(record.move_before_quantity,2)) if record.move_before_quantity else "0")
            worksheet.write(row, 6, str(round(record.move_after_quantity,2)) if record.move_after_quantity else "0")
            if record.move_before_quantity > record.move_after_quantity: 
                worksheet.write(row, 7, str(-round(record.qty_done,2)) if record.qty_done else "")
            else:
                worksheet.write(row, 7, str(round(record.qty_done,2)) if record.qty_done else "")
            worksheet.write(row, 8, str(record.product_uom_id.name) if record.product_uom_id else "")           
            row = row + 1
        
        workbook.close()
        output.seek(0) 

        # 创建 Excel 文件并返回
        attachment = self.env['ir.attachment'].create({
            'name': "盤點損耗表.xlsx",
            'datas': base64.b64encode(output.getvalue()),
            'res_model': 'stock.move.line',
            'type': 'binary'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }
    @api.depends("date")
    def _compute_year_month(self):
        # invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        for record in self:
                
            next_year_str = record.date.strftime('%Y')  # 两位数的年份
            next_month_str = record.date.strftime('%m')  # 月份
            
            year_record = self.env['dtsc.year'].search([('name', '=', next_year_str)], limit=1)
            month_record = self.env['dtsc.month'].search([('name', '=', next_month_str)], limit=1)

            record.report_year = year_record.id if year_record else False
            record.report_month = month_record.id if month_record else False
    
    @api.depends("state")
    def _compute_move_after_quantity(self):
        for record in self:
            if record.state == "done":
                #decoration-danger="(location_usage in ('internal','transit')) and (location_dest_usage not in ('internal','transit'))"   扣料
                #decoration-success="(location_usage not in ('internal','transit')) and (location_dest_usage in ('internal','transit'))"  入库
                obj = False 
                if record.location_usage in ["internal","transit"] and record.location_dest_usage not in ['internal','transit']:   
                    if record.lot_id:
                        obj = self.env["stock.quant"].search([('product_id','=',record.product_id.id),('location_id','=',record.location_id.id),("lot_id","=",record.lot_id.id)],limit=1)
                    else:
                        obj = self.env["stock.quant"].search([('product_id','=',record.product_id.id),('location_id','=',record.location_id.id)],limit=1)
                    record.location_ori = record.location_id
                elif record.location_usage not in ["internal","transit"] and record.location_dest_usage in ['internal','transit']:
                    if record.lot_id:
                        obj = self.env["stock.quant"].search([('product_id','=',record.product_id.id),('location_id','=',record.location_dest_id.id),("lot_id","=",record.lot_id.id)],limit=1)
                    else:
                        obj = self.env["stock.quant"].search([('product_id','=',record.product_id.id),('location_id','=',record.location_dest_id.id)],limit=1)
                    record.location_ori = record.location_dest_id
                elif record.location_usage in ["internal", "transit"] and record.location_dest_usage in ["internal", "transit"]:
                    # 調撥情境：看來源倉庫剩餘量 
                    record.location_ori = record.location_id
                    if record.lot_id:
                        obj = self.env["stock.quant"].search([
                            ('product_id', '=', record.product_id.id),
                            ('location_id', '=', record.location_id.id),
                            ("lot_id", "=", record.lot_id.id)
                        ], limit=1)
                    else:
                        obj = self.env["stock.quant"].search([
                            ('product_id', '=', record.product_id.id),
                            ('location_id', '=', record.location_id.id)
                        ], limit=1)  
                        
                if obj:
                    record.move_after_quantity = obj.quantity
                else:
                    record.move_after_quantity = False
    
    @api.model
    def create(self, vals):
        location = self.env['stock.location'].browse(vals['location_id'])
        location_dest = self.env['stock.location'].browse(vals['location_dest_id'])
    
        if location.usage in ["internal","transit"] and location_dest.usage not in ['internal','transit']:                    
            location_id = vals['location_id']
        elif location.usage not in ["internal","transit"] and location_dest.usage in ['internal','transit']:
            location_id = vals['location_dest_id']
        else:
            location_id = vals['location_id']
        
        lot_id = vals.get('lot_id', None)
        if lot_id:
            obj = self.env["stock.quant"].search([('product_id','=',vals['product_id']),('lot_id','=',vals['lot_id']),('location_id','=',location_id)],limit=1)
        else:
            obj = self.env["stock.quant"].search([('product_id','=',vals['product_id']),('location_id','=',location_id)],limit=1)
            
        # ==========={'product_id': 112, 'product_uom_id': 51, 'qty_done': 0.2, 'location_id': 8, 'location_dest_id': 14, 'company_id': 1, 'lot_id': 7, 'package_id': False, 'result_package_id': False, 'owner_id': False, 'date': datetime.datetime(2025, 3, 27, 9, 12, 46), 'move_id': 28}========
        if obj:
            vals["move_before_quantity"] = obj.quantity
        # _logger.info(f"==========={obj.quantity}========")
        res = super(StockMoveLine, self).create(vals)

        return res
    
    @api.onchange('qty_done', 'product_uom_id')
    def _onchange_qty_done(self):
        """ When the user is encoding a move line for a tracked product, we apply some logic to
        help him. This onchange will warn him if he set `qty_done` to a non-supported value.
        """
        res = {}
        # if self.qty_done and self.product_id.tracking == 'serial':
            # qty_done = self.product_uom_id._compute_quantity(self.qty_done, self.product_id.uom_id)
            # if float_compare(qty_done, 1.0, precision_rounding=self.product_id.uom_id.rounding) != 0:
                # message = _('You can only process 1.0 %s of products with unique serial number.', self.product_id.uom_id.name)
                # res['warning'] = {'title': _('Warning'), 'message': message}
        return res
    # remark = fields.Text(string="備註")
    # def _get_inventory_move_values(self, qty, location_id, location_dest_id, out=False):
 
        # self.ensure_one()
        # if self.remark:
            # if fields.Float.is_zero(qty, 0, precision_rounding=self.product_uom_id.rounding):
                # name = "數量確認 (" + self.remark+")"
            # else:
                # name = "數量更新 (" + self.remark +")"
        
        # self.write({"remark":""})
        # return {
            # 'name': self.env.context.get('inventory_name') or name,
            # 'product_id': self.product_id.id,
            # 'product_uom': self.product_uom_id.id,
            # 'product_uom_qty': qty,
            # 'company_id': self.company_id.id or self.env.company.id,
            # 'state': 'confirmed',
            # 'location_id': location_id.id,
            # 'location_dest_id': location_dest_id.id,
            # 'is_inventory': True,
            # 'move_line_ids': [(0, 0, {
                # 'product_id': self.product_id.id,
                # 'product_uom_id': self.product_uom_id.id,
                # 'qty_done': qty,
                # 'location_id': location_id.id,
                # 'location_dest_id': location_dest_id.id,
                # 'company_id': self.company_id.id or self.env.company.id,
                # 'lot_id': self.lot_id.id,
                # 'package_id': out and self.package_id.id or False,
                # 'result_package_id': (not out) and self.package_id.id or False,
                # 'owner_id': self.owner_id.id,
            # })]
        # }

        
# class StockQuantInherit(models.Model):
    # _inherit = 'stock.quant'

    # purchase_price = fields.Float('採購價格')
        
class ReportStockQuant(models.AbstractModel):
    _name = 'report.dtsc.report_inventory'
    
    
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        end_date = data.get('endtime')
        select_method = data.get('select_method')
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        is_print_zero = data.get('is_print_zero')
        # if not is_print_zero:
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])
        # else:
            # quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids),("quantity",">=",0)])
            
        product_quant_map = {}
        
        # key = 0
        report_data = []
        for quant in quants:
            if quant.product_id.name == "其他 (採購用)" or quant.product_id.detailed_type not in ['product']:
                continue
            # 使用 (product_id, location_id) 作为键
            is_lot = quant.lot_id.id if quant.lot_id else 0
            key = (quant.product_id.id, quant.location_id.name, is_lot)
            
            if key not in product_quant_map:
                product_quant_map[key] = {
                    'product_id': quant.product_id,
                    'location': quant.location_id,
                    'lot_id': quant.lot_id,
                    'quantity': quant.quantity,
                    'uom': quant.product_uom_id.name,
                    'total_value': 0.0,
                    'average_price': 0.0,
                }
            total_value = 0.0
            average_price = 0.0
            b=0
            if not end_date:
                if quant.lot_id:#如果是捲料 則直接找捲料單價
                    b=1
                    lot_purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('order_id.state', 'in', ['purchase', 'done']),
                        ('order_id',"=",quant.lot_id.purchase_order_id.id)
                    ], order='date_order desc', limit=1)

                    # 如果找到了对应的采购单行，使用该批次的单价
                    if lot_purchase_lines:
                        if lot_purchase_lines.price_unit == 0:
                            average_price = quant.product_id.standard_price
                        else:
                            average_price = lot_purchase_lines.price_unit
                        total_value = quant.quantity * average_price
                    else:#如果找不到相同序號的 ，則找最近一個相同產品的
                        average_price = quant.product_id.standard_price
                        total_value = quant.quantity * average_price
                        
                else:#否則計算加權平均價格
                    # 否则使用加权平均价格计算
                    total_qty_needed = quant.quantity
                    purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                    ], order='date_order desc')

                    qty_consumed = 0
                    for line in purchase_lines:
                        if total_qty_needed <= 0:
                            break
                        purchase_qty = line.product_qty
                        purchase_price = 0
                        if line.price_unit != 0:
                            purchase_price = line.price_unit
                        else:
                            purchase_price = line.product_id.standard_price

                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty
                    if total_qty_needed > 0 and qty_consumed == 0:
                        total_value = total_qty_needed * quant.product_id.standard_price
                        average_price = quant.product_id.standard_price                        
                    else:    
                        average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0
                    
                    average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0

                if not is_print_zero:
                    if round(quant.quantity, 2) > 0:
                        report_data.append({
                            'product_id': quant.product_id,
                            'lot_id':quant.lot_id.name,
                            'quantity': round(quant.quantity, 2),
                            'uom': quant.product_uom_id.name,
                            'is_lot':b,
                            'location': quant.location_id.name,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': round(total_value, 2),  # 总价值
                        })
                else:
                    if round(quant.quantity, 2) >= 0:
                        report_data.append({
                            'product_id': quant.product_id,
                            'lot_id':quant.lot_id.name,
                            'quantity': abs(round(quant.quantity, 2)),
                            'uom': quant.product_uom_id.name,
                            'is_lot':b,
                            'location': quant.location_id.name,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': abs(round(total_value, 2)),  # 总价值
                        })
            
        # print(len(product_quant_map))    
        if end_date:
            for location in internal_locations:
                move_lines_out = self.env['stock.move.line'].search([
                    ('location_id', '=', location.id),  # 出库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                for line in move_lines_out:
                    if line.product_id.name == "其他 (採購用)" or line.product_id.detailed_type not in ['product']:
                        continue
                    is_lot = line.lot_id.id if line.lot_id else 0
                    key = (line.product_id.id, location.name, is_lot)
                    # print(key)
                    qty_change = round(line.qty_done / line.product_uom_id.factor, 4) if line.lot_id and line.product_uom_id.name == "才" else line.qty_done

                    # 更新数量
                    if key in product_quant_map:
                        product_quant_map[key]['quantity'] += qty_change 
                    else:                        
                        product_quant_map[key] = {
                            'product_id': line.product_id,
                            'location': location.id,
                            'lot_id': line.lot_id,
                            'quantity': qty_change,
                            'uom': line.product_uom_id.name,
                            'total_value': 0.0,
                            'average_price': 0.0,
                        }          
                
                # print(len(product_quant_map))
                move_lines_in = self.env['stock.move.line'].search([
                    ('location_dest_id', '=', location.id),  # 入库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                for line in move_lines_in:
                    if line.product_id.name == "其他 (採購用)" or line.product_id.detailed_type not in ['product']:
                        continue
                    is_lot = line.lot_id.id if line.lot_id else 0
                    key = (line.product_id.id, location.name, is_lot)
                    qty_change = round(line.qty_done / line.product_uom_id.factor, 4) if line.lot_id and line.product_uom_id.name == "才" else line.qty_done

                    # 更新数量
                    if key in product_quant_map:   
                        product_quant_map[key]['quantity'] -= qty_change 
                    else:                    
                        product_quant_map[key] = {
                            'product_id': line.product_id,
                            'location': location.id,
                            'lot_id': line.lot_id,
                            'quantity': qty_change,
                            'uom': line.product_uom_id.name,
                            'total_value': 0.0,
                            'average_price': 0.0,
                        }
                # print(len(product_quant_map))
            for (product_id, loc ,lot), data in product_quant_map.items():
            
                total_value = 0.0
                average_price = 0.0
                b = 0
                lot_name = ""
                if lot:#如果是捲料 則直接找捲料單價
                    # continue
                    b = 1
                    lot_obj = self.env['stock.lot'].browse(lot)
                    lot_name = lot_obj.name
                    lot_purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', product_id),
                        ('order_id.state', 'in', ['purchase', 'done']),
                        ('order_id',"=",lot_obj.purchase_order_id.id)
                    ], order='date_order desc', limit=1)

                    # 如果找到了对应的采购单行，使用该批次的单价
                    if lot_purchase_lines:
                        if lot_purchase_lines.price_unit == 0:
                            average_price = lot_purchase_lines.product_id.standard_price
                        else:
                            average_price = lot_purchase_lines.price_unit
                        total_value = data['quantity'] * average_price
                    else:#如果找不到相同序號的 ，則找最近一個相同產品的
                        # lot_purchase_lines_other = self.env['purchase.order.line'].search([
                        # ('product_id', '=', product_id),
                        # ('order_id.state', 'in', ['purchase', 'done'])
                        # ], order='date_order desc', limit=1)
                        # average_price = lot_purchase_lines_other.price_unit
                        average_price = self.env['product.product'].browse(product_id).standard_price
                        total_value = data['quantity'] * average_price
                        
                else:#否則計算加權平均價格
                    # continue
                    # 否则使用加权平均价格计算
                    total_qty_needed = data['quantity']
                    purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', product_id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                    ], order='date_order desc')

                    qty_consumed = 0
                    for line in purchase_lines:
                        if total_qty_needed <= 0:
                            break
                        purchase_qty = line.product_qty
                        purchase_price = 0
                        if line.price_unit != 0:
                            purchase_price = line.price_unit
                        else:
                            purchase_price = line.product_id.standard_price

                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty
                    if total_qty_needed > 0 and qty_consumed == 0:
                        total_value = total_qty_needed * product_id.standard_price
                        average_price = product_id.standard_price                        
                    else:    
                        average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0
                if not is_print_zero:
                    if round(data['quantity'], 2) > 0:
                        report_data.append({
                            'product_id': self.env['product.product'].browse(product_id),
                            'lot_id':  lot_name,
                            'quantity': round(data['quantity'], 2),
                            'uom': data['uom'],
                            'is_lot':b,
                            'location': loc,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': round(total_value, 2),  # 总价值
                        })
                else:
                    if round(data['quantity'], 2) >= 0:
                        report_data.append({
                            'product_id': self.env['product.product'].browse(product_id),
                            'lot_id':  lot_name,
                            'quantity': abs(round(data['quantity'], 2)),
                            'uom': data['uom'],
                            'is_lot':b,
                            'location': loc,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': abs(round(total_value, 2)),  # 总价值
                        })
                        
        merged_data = {}
        for data in report_data:
            product_id = data['product_id']
            if product_id not in merged_data:
                merged_data[product_id] = {
                    'product_id': product_id,
                    'lot_id': data['lot_id'],
                    'quantity': round(data['quantity'],2),
                    'uom': data['uom'],
                    'is_lot': data['is_lot'],
                    'location': data['location'],
                    'total_value': data['total_value'],
                    'total_weighted_price': round(data['average_price'] * data['quantity'],2),  # 加权总价格
                }
            else:
                # 合并数据
                merged_data[product_id]['quantity'] += round(data['quantity'],2)
                merged_data[product_id]['total_value'] += data['total_value']
                merged_data[product_id]['total_weighted_price'] += data['average_price'] * data['quantity']

        # 计算加权平均价格并生成合并后的列表
        consolidated_report_data = []
        for item in merged_data.values():
            if item['quantity'] > 0:
                item['average_price'] = round(item['total_weighted_price'] / item['quantity'], 2)  # 加权平均价格
            else:
                item['average_price'] = 0.0
            # 移除临时字段 total_weighted_price
            item.pop('total_weighted_price', None)
            consolidated_report_data.append(item)

        # 按照仓库名称排序
        sorted_report_data = sorted(consolidated_report_data, key=lambda x: (x['location'], -x['is_lot'], x['product_id']))

        return {
            'doc_ids': docids,
            'docs': quants,
            'date' : end_date or datetime.today().strftime('%Y-%m-%d'),
            'doc_model': 'stock.quant',
            'data': sorted_report_data,  # 传递合并后的数据给报告
        }
    '''
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        select_company = data.get('select_method', None)
        end_date = data.get('endtime')
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        if not end_date:#查詢當前庫存 
            quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids),("quantity",">",0)])
        else:
            quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])    
        product_quant_map = {}


        for quant in quants:
            # 使用 (product_id, location_id) 作为键
            if quant.product_id.name == "其他 (採購用)" or quant.product_id.detailed_type not in ['product']:
                continue
            key = (quant.product_id, quant.location_id)
            if key not in product_quant_map:
                if quant.lot_id:
                    a = 1
                else:
                    a = 0
                product_quant_map[key] = {
                    'total_qty': 0.0,
                    'uom': quant.product_uom_id.name,
                    'location': quant.location_id.name,  # 增加仓库位置
                    'is_lot': a,
                }
            product_quant_map[key]['total_qty'] += quant.quantity
        
        # 准备传递给报告的数据
        report_data = []
        for (product, location), data in product_quant_map.items():
            adjusted_qty = round(data['total_qty'],2)
            if end_date:
                qty_out = 0
                qty_in = 0
                
                move_lines = self.env['stock.move.line'].search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id),  # 出库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])

                move_lines_in = self.env['stock.move.line'].search([
                    ('product_id', '=', product.id),
                    ('location_dest_id', '=', location.id),  # 入库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                if data['is_lot'] == 1:
                    for line in move_lines:
                        if line.product_uom_id.name == "才": #如果卷材是按才扣料 需要转换成卷的百分比
                            tmp = round(line.qty_done / line.product_uom_id.factor , 2)
                            qty_out = qty_out + tmp
                        else:
                            qty_out = qty_out+line.qty_done
                    
                    
                    for line in move_lines_in:

                        if line.product_uom_id.name == "才": #如果卷材是按才扣料 需要转换成卷的百分比
                            tmp = round(line.qty_done / line.product_uom_id.factor , 2)
                            qty_in = qty_in + tmp
                        else:
                            qty_in = qty_in+line.qty_done
                else:
                    qty_out = sum(line.qty_done for line in move_lines)
                    qty_in = sum(line.qty_done for line in move_lines_in)
        
                # if product.id == 494:
                    # print(adjusted_qty)
                    # print(qty_out)
                    # print(qty_in)
                    # print(adjusted_qty + qty_out - qty_in)
        
                adjusted_qty = adjusted_qty + qty_out - qty_in
                
            if round(adjusted_qty,2) > 0:
                report_data.append({
                    'product_id': product,
                    'quantity': round(adjusted_qty,2),
                    'uom': data['uom'],
                    'location': data['location'],  # 在报告中显示仓库位置
                    'is_lot' : data['is_lot'],
                })
       # 返回传递给报告的数据
        # print(report_data)
        # 按照仓库名称排序
        sorted_report_data = sorted(report_data, key=lambda x:( x['location'], -x['is_lot'], x['product_id'].name))
        return {
            'doc_ids': docids,
            'docs': quants,
            'doc_model': 'stock.quant',
            'data': sorted_report_data,  # 传递合并后的数据给报告
        }
    '''
    
        
class ReportStockQuantAmount(models.AbstractModel):
    _name = 'report.dtsc.report_inventory_amount'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        end_date = data.get('endtime')
        select_method = data.get('select_method')
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        is_print_zero = data.get('is_print_zero')
        # if not is_print_zero:
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])
        # else:
            # quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids),("quantity",">=",0)])
        product_quant_map = {}
        
        # key = 0
        report_data = []
        for quant in quants:
            if quant.product_id.name == "其他 (採購用)" or quant.product_id.detailed_type not in ['product']:
                continue
            # 使用 (product_id, location_id) 作为键
            is_lot = quant.lot_id.id if quant.lot_id else 0
            key = (quant.product_id.id, quant.location_id.name, is_lot)
            
            if key not in product_quant_map:
                product_quant_map[key] = {
                    'product_id': quant.product_id,
                    'location': quant.location_id,
                    'lot_id': quant.lot_id,
                    'quantity': quant.quantity,
                    'uom': quant.product_uom_id.name,
                    'total_value': 0.0,
                    'average_price': 0.0,
                }
            total_value = 0.0
            average_price = 0.0
            b=0
            if not end_date:
                if quant.lot_id:#如果是捲料 則直接找捲料單價
                    b=1
                    lot_purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('order_id.state', 'in', ['purchase', 'done']),
                        ('order_id',"=",quant.lot_id.purchase_order_id.id)
                    ], order='date_order desc', limit=1)

                    # 如果找到了对应的采购单行，使用该批次的单价
                    if lot_purchase_lines:
                        if lot_purchase_lines.price_unit == 0:
                            average_price = quant.product_id.standard_price
                        else:
                            average_price = lot_purchase_lines.price_unit
                        total_value = abs(round(quant.quantity, 2)) * average_price
                    else:#如果找不到相同序號的 ，則找最近一個相同產品的
                        average_price = quant.product_id.standard_price
                        total_value = abs(round(quant.quantity, 2)) * average_price
                        
                else:#否則計算加權平均價格
                    # 否则使用加权平均价格计算
                    total_qty_needed = quant.quantity
                    purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                    ], order='date_order desc')

                    qty_consumed = 0
                    for line in purchase_lines:
                        if total_qty_needed <= 0:
                            break
                        purchase_qty = line.product_qty
                        purchase_price = 0
                        if line.price_unit != 0:
                            purchase_price = line.price_unit
                        else:
                            purchase_price = line.product_id.standard_price

                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty
                    
                    if total_qty_needed > 0 and qty_consumed == 0:
                        total_value = total_qty_needed * quant.product_id.standard_price
                        average_price = quant.product_id.standard_price                        
                    else:    
                        average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0

                if not is_print_zero:
                    if round(quant.quantity, 2) > 0:
                        report_data.append({
                            'product_id': quant.product_id,
                            'lot_id':quant.lot_id.name,
                            'quantity': round(quant.quantity, 2),
                            'uom': quant.product_uom_id.name,
                            'is_lot':b,
                            'location': quant.location_id.name,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': round(total_value, 2),  # 总价值
                        })
                else:
                    if round(quant.quantity, 2) >= 0:
                        report_data.append({
                            'product_id': quant.product_id,
                            'lot_id':quant.lot_id.name,
                            'quantity': abs(round(quant.quantity, 2)),
                            'uom': quant.product_uom_id.name,
                            'is_lot':b,
                            'location': quant.location_id.name,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': abs(round(total_value, 2)),  # 总价值
                        })
            
        # print(len(product_quant_map))    
        if end_date:
            for location in internal_locations:
                move_lines_out = self.env['stock.move.line'].search([
                    ('location_id', '=', location.id),  # 出库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                for line in move_lines_out:
                    if line.product_id.name == "其他 (採購用)" or line.product_id.detailed_type not in ['product']:
                        continue
                    is_lot = line.lot_id.id if line.lot_id else 0
                    key = (line.product_id.id, location.name, is_lot)
                    # print(key)
                    qty_change = round(line.qty_done / line.product_uom_id.factor, 4) if line.lot_id and line.product_uom_id.name == "才" else line.qty_done

                    # 更新数量
                    if key in product_quant_map:
                        product_quant_map[key]['quantity'] += qty_change 
                    else:                        
                        product_quant_map[key] = {
                            'product_id': line.product_id,
                            'location': location.id,
                            'lot_id': line.lot_id,
                            'quantity': qty_change,
                            'uom': line.product_uom_id.name,
                            'total_value': 0.0,
                            'average_price': 0.0,
                        }          
                
                # print(len(product_quant_map))
                move_lines_in = self.env['stock.move.line'].search([
                    ('location_dest_id', '=', location.id),  # 入库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                for line in move_lines_in:
                    if line.product_id.name == "其他 (採購用)" or line.product_id.detailed_type not in ['product']:
                        continue
                    is_lot = line.lot_id.id if line.lot_id else 0
                    key = (line.product_id.id, location.name, is_lot)
                    qty_change = round(line.qty_done / line.product_uom_id.factor, 4) if line.lot_id and line.product_uom_id.name == "才" else line.qty_done

                    # 更新数量
                    if key in product_quant_map:   
                        product_quant_map[key]['quantity'] -= qty_change 
                    else:                    
                        product_quant_map[key] = {
                            'product_id': line.product_id,
                            'location': location.id,
                            'lot_id': line.lot_id,
                            'quantity': qty_change,
                            'uom': line.product_uom_id.name,
                            'total_value': 0.0,
                            'average_price': 0.0,
                        }
                # print(len(product_quant_map))
            for (product_id, loc ,lot), data in product_quant_map.items():
            
                total_value = 0.0
                average_price = 0.0
                b = 0
                lot_name = ""
                if lot:#如果是捲料 則直接找捲料單價
                    # continue
                    b = 1
                    lot_obj = self.env['stock.lot'].browse(lot)
                    lot_name = lot_obj.name
                    lot_purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', product_id),
                        ('order_id.state', 'in', ['purchase', 'done']),
                        ('order_id',"=",lot_obj.purchase_order_id.id)
                    ], order='date_order desc', limit=1)

                    # 如果找到了对应的采购单行，使用该批次的单价
                    if lot_purchase_lines:
                        if lot_purchase_lines.price_unit == 0:
                            average_price = lot_purchase_lines.product_id.standard_price
                        else:
                            average_price = lot_purchase_lines.price_unit
                        total_value = abs(round(data['quantity'], 2)) * average_price
                    else:#如果找不到相同序號的 ，則找最近一個相同產品的
                        average_price = self.env['product.product'].browse(product_id).standard_price
                        total_value = abs(round(data['quantity'], 2)) * average_price
                        
                else:#否則計算加權平均價格
                    # continue
                    # 否则使用加权平均价格计算
                    total_qty_needed = abs(round(data['quantity'], 2))
                    purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', product_id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                    ], order='date_order desc')

                    qty_consumed = 0
                    for line in purchase_lines:
                        if total_qty_needed <= 0:
                            break
                        purchase_qty = line.product_qty
                        purchase_price = 0
                        if line.price_unit != 0:
                            purchase_price = line.price_unit
                        else:
                            purchase_price = line.product_id.standard_price

                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty

                    if total_qty_needed > 0 and qty_consumed == 0:
                        total_value = total_qty_needed * product_id.standard_price
                        average_price = product_id.standard_price                        
                    else:    
                        average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0
                if not is_print_zero:
                    if round(data['quantity'], 2) > 0:
                        report_data.append({
                            'product_id': self.env['product.product'].browse(product_id),
                            'lot_id':  lot_name,
                            'quantity': round(data['quantity'], 2),
                            'uom': data['uom'],
                            'is_lot':b,
                            'location': loc,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': round(total_value, 2),  # 总价值
                        })
                else:
                    if round(data['quantity'], 2) >= 0:
                        report_data.append({
                            'product_id': self.env['product.product'].browse(product_id),
                            'lot_id':  lot_name,
                            'quantity': abs(round(data['quantity'], 2)),
                            'uom': data['uom'],
                            'is_lot':b,
                            'location': loc,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': abs(round(total_value, 2)),  # 总价值
                        })
                        
        merged_data = {}
        for data in report_data:
            key = (data['product_id'], data['location'])  # 使用 (product_id, location) 作为唯一键
            if key not in merged_data:
                merged_data[key] = {
                    'product_id': data['product_id'],
                    'lot_id': data['lot_id'],
                    'quantity': round(data['quantity'], 2),
                    'uom': data['uom'],
                    'is_lot': data['is_lot'],
                    'location': data['location'],
                    'total_value': data['total_value'],
                    'total_weighted_price': round(data['average_price'] * data['quantity'], 2),  # 加权总价格
                }
            else:
                # 合并数据
                merged_data[key]['quantity'] += round(data['quantity'], 2)
                merged_data[key]['total_value'] += data['total_value']
                merged_data[key]['total_weighted_price'] += data['average_price'] * data['quantity']

        # 计算加权平均价格并生成合并后的列表
        consolidated_report_data = []
        for item in merged_data.values():
            if item['quantity'] > 0:
                item['average_price'] = round(item['total_weighted_price'] / item['quantity'], 2)  # 加权平均价格
            else:
                item['average_price'] = 0.0
            # 移除临时字段 total_weighted_price
            item.pop('total_weighted_price', None)
            consolidated_report_data.append(item)

        # 按照仓库名称排序
        sorted_report_data = sorted(consolidated_report_data, key=lambda x: (x['location'], -x['is_lot'], x['product_id']))

        return {
            'doc_ids': docids,
            'docs': quants,
            'date' : end_date or datetime.today().strftime('%Y-%m-%d'),
            'doc_model': 'stock.quant',
            'data': sorted_report_data,  # 传递合并后的数据给报告
        }
    
    '''
    @api.model
    def _get_report_values(self, docids, data=None):
        end_date = data.get('endtime')
        
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids),("quantity",">",0)])
        product_quant_map = {}        
        report_data = []
        
        for quant in quants:
            # 使用 (product_id, location_id) 作为键
            if quant.product_id.name == "其他 (採購用)" or quant.product_id.detailed_type not in ['product']:
                continue
            key = (quant.product_id, quant.location_id)
            if key not in product_quant_map:
                product_quant_map[key] = {
                    'total_qty': 0.0,
                    'uom': quant.product_uom_id.name,
                    'location': quant.location_id.name,  # 增加仓库位置
                    'lots': [],
                    'lot_qty': [],
                }
            product_quant_map[key]['total_qty'] += quant.quantity
            if quant.lot_id:
                product_quant_map[key]['lots'].append(quant.lot_id)
                product_quant_map[key]['lot_qty'].append(quant.quantity)

        if end_date:
            for location in internal_locations:
                move_lines_out = self.env['stock.move.line'].search([
                    ('location_id', '=', location.id),  # 出库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                for line in move_lines_out:
                    if line.product_id.name == "其他 (採購用)" or line.product_id.detailed_type not in ['product']:
                        continue
                    key = (line.product_id, line.location_id)
                    
                    qty_change = round(line.qty_done / line.product_uom_id.factor , 4) if line.lot_id and line.product_uom_id.name == "才" else line.qty_done

                    if key in product_quant_map:
                        # 更新现有记录
                        product_quant_map[key]['total_qty'] += qty_change
                        if line.lot_id:
                            if line.lot_id in product_quant_map[key]['lots']:
                                index = product_quant_map[key]['lots'].index(line.lot_id)
                                product_quant_map[key]['lot_qty'][index] += qty_change
                            else:
                                product_quant_map[key]['lots'].append(line.lot_id)
                                product_quant_map[key]['lot_qty'].append(qty_change)
                    else:
                        # 新增记录
                        product_quant_map[key] = {
                            'total_qty': qty_change,
                            'uom': line.product_id.uom_id.name,
                            'location': line.location_id.name,
                            'lots': [line.lot_id] if line.lot_id else [],
                            'lot_qty': [qty_change] if line.lot_id else [],
                        }
                
                move_lines_in = self.env['stock.move.line'].search([
                    ('location_dest_id', '=', location.id),  # 入库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                for line in move_lines_in:
                    if line.product_id.name == "其他 (採購用)" or line.product_id.detailed_type not in ['product']:
                        continue
                    key = (line.product_id, line.location_dest_id)
                    qty_change = round(line.qty_done / line.product_uom_id.factor , 4) if line.lot_id and line.product_uom_id.name == "才" else line.qty_done

                    if key in product_quant_map:
                        # 更新现有记录
                        product_quant_map[key]['total_qty'] -= qty_change
                        if line.lot_id:
                            if line.lot_id in product_quant_map[key]['lots']:
                                index = product_quant_map[key]['lots'].index(line.lot_id)
                                product_quant_map[key]['lot_qty'][index] -= qty_change
                            else:
                                product_quant_map[key]['lots'].append(line.lot_id)
                                product_quant_map[key]['lot_qty'].append(-qty_change)
                    else:
                        # 新增记录
                        product_quant_map[key] = {
                            'total_qty': -qty_change,
                            'uom': line.product_id.uom_id.name,
                            'location': line.location_dest_id.name,
                            'lots': [line.lot_id] if line.lot_id else [],
                            'lot_qty': [-qty_change] if line.lot_id else [],
                        }             
        
        # 准备传递给报告的数据
        for (product, location), data in product_quant_map.items():
            total_qty_needed = data['total_qty']  # 该仓库中该产品的总库存数量
            total_value = 0.0  # 总价值
            qty_consumed = 0  # 已处理的数量
            average_price = 0
            
            
            if data["lots"]:
                # continue
                for index, lot in enumerate(data["lots"]):
                    purchase_line = self.env['purchase.order.line'].search([
                    ('product_id', '=', product.id),
                    ('order_id.state', 'in', ['purchase', 'done']),
                    ('order_id',"=",lot.purchase_order_id.id)
                    ], order='date_order desc',limit=1)

                    if purchase_line:
                        average_price = purchase_line.price_unit
                        lot_qty = data['lot_qty'][index]  # 获取该批次的数量
                        total_value += lot_qty * average_price  # 计算总价值
                    else:#如果找不到相同序號的 ，則找最近一個相同產品的
                        lot_purchase_lines_other = self.env['purchase.order.line'].search([
                        ('product_id', '=', product.id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                        ], order='date_order desc', limit=1)
                        
                        if lot_purchase_lines_other:
                            average_price = lot_purchase_lines_other.price_unit
                            lot_qty = data['lot_qty'][index]  # 获取该批次的数量
                            total_value += lot_qty * average_price  # 计算总价值
                
                if round(data['total_qty'], 2) > 0:
                    report_data.append({
                        'product_id': product,
                        'quantity': round(data['total_qty'], 2),
                        'uom': data['uom'],
                        'location': data['location'],
                        'average_price': round(average_price, 2),  # 加权平均价格
                        'total_value': round(total_value, 2),  # 总价值
                        'is_lot':1, 
                    })    
                
            else:
                continue
                # 获取该产品的所有采购记录，按时间从最近到最早排序
                purchase_lines = self.env['purchase.order.line'].search([
                    ('product_id', '=', product.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                ], order='date_order desc')
                
                
                
                # 根据采购记录计算加权平均价格
                a = 0
                if total_qty_needed <= 0:
                    #如果數量為0 則找最近一筆的單價顯示
                    if purchase_lines:
                        a = purchase_lines[0].price_unit
                    average_price = a  # 如果没有采购记录，则保持为0
                else:    
                    for line in purchase_lines:
                        if total_qty_needed <= 0:
                            # if line.price_unit:
                                # a = line.price_unit
                            break

                        purchase_qty = line.product_qty  # 采购的数量
                        purchase_price = line.price_unit  # 采购的单价

                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty

                    # 如果没有采购记录或库存消耗完了，价格为0
                    # if total_qty_needed <= 0:
                        # average_price = a
                    # else:
                    average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0

                # 加入到报告数据中
                if round(data['total_qty'], 2) > 0:
                    report_data.append({
                        'product_id': product,
                        'quantity': round(data['total_qty'], 2),
                        'uom': data['uom'],
                        'location': data['location'],
                        'average_price': round(average_price, 2),  # 加权平均价格
                        'total_value': round(total_value, 2),
                        'is_lot':0,                    # 总价值
                    })
        

        
        # 按照仓库名称排序
        sorted_report_data = sorted(report_data, key=lambda x:( x['location'], -x['is_lot'], x['product_id'].name))

        return {
            'doc_ids': docids,
            'docs': quants,
            'doc_model': 'stock.quant',
            'data': sorted_report_data,  # 传递合并后的数据给报告
        }
    '''
    '''
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])
        product_quant_map = {}

        for quant in quants:
            # 对每个quant, 找到对应的stock.move.line和stock.move
            move_lines = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('location_id', '=', 4)
            ], limit=1)

            if move_lines:
                move = move_lines.move_id
                if move:
                    # 获取价格从采购订单行
                    purchase_line = move.purchase_line_id
                    price_unit = purchase_line.price_unit if purchase_line else move.price_unit  # 如果没有采购行则使用move的price_unit

                    # 对于每个产品，累计其数量和总价格
                    if quant.product_id not in product_quant_map:
                        product_quant_map[quant.product_id] = {
                            'total_price': 0.0,
                            'total_qty': 0.0,
                            'uom': quant.product_uom_id.name  
                        }
                    
                    product_quant_map[quant.product_id]['total_price'] += round(price_unit * quant.quantity, 1)
                    product_quant_map[quant.product_id]['total_qty'] += quant.quantity
        
        # 计算平均价格
        for product_id, data in product_quant_map.items():
            print(f"Product: {product_id.display_name}, Total Quantity: {data['total_qty']}, Total Price: {data['total_price']}")
            if data['total_qty'] > 0:
                data['avg_price'] = round(data['total_price'] / data['total_qty'], 1)
            else:
                data['avg_price'] = 0.0
        
        # 准备传递给报告的数据
        report_data = []
        for product, data in product_quant_map.items():
            report_data.append({
                'product_id': product,
                'quantity': data['total_qty'],
                'average_price': data['avg_price'],
                'total_price': data['total_price'],
                'uom': data['uom']
            })

        return {
            'doc_ids': docids,
            'doc_model': 'stock.quant',
            'data': report_data,  # 传递合并后的数据给报告
        }
        '''
class StockQuantInherit(models.Model):
    _inherit = 'stock.quant'

    purchase_price = fields.Float('採購價格')
    
    #重写方法 不判断序号大于1的扣料情况
    @api.constrains('quantity')
    def check_quantity(self):
        sn_quants = self.filtered(lambda q: q.product_id.tracking == 'serial' and q.location_id.usage != 'inventory' and q.lot_id)
        if not sn_quants:
            return
        # domain = expression.OR([
            # [('product_id', '=', q.product_id.id), ('location_id', '=', q.location_id.id), ('lot_id', '=', q.lot_id.id)]
            # for q in sn_quants
        # ])
        # groups = self.read_group(
            # domain,
            # ['quantity'],
            # ['product_id', 'location_id', 'lot_id'],
            # orderby='id',
            # lazy=False,
        # )
        # for group in groups:
            # product = self.env['product.product'].browse(group['product_id'][0])
            # lot = self.env['stock.lot'].browse(group['lot_id'][0])
            # uom = product.uom_id
            # if float_compare(abs(group['quantity']), 1, precision_rounding=uom.rounding) > 0:
                # raise ValidationError(_('The serial number has already been assigned: \n Product: %s, Serial Number: %s') % (product.display_name, lot.name))
        
class ReportStockQuantBase(models.AbstractModel):
    _name = 'report.dtsc.report_inventory_base'
    
    @api.model
    def _get_report_values(self, docids, data=None):
        # 获取所有特定位置的stock.quant
        end_date = data.get('endtime')
        select_method = data.get('select_method')
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])        
        is_print_zero = data.get('is_print_zero')
        # if not is_print_zero:
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])
        # else:
            # quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids),("quantity",">=",0)])
        product_quant_map = {}
        
        # key = 0
        report_data = []
        for quant in quants:
            if quant.product_id.name == "其他 (採購用)" or quant.product_id.detailed_type not in ['product']:
                continue
            # 使用 (product_id, location_id) 作为键
            is_lot = quant.lot_id.id if quant.lot_id else 0
            key = (quant.product_id.id, quant.location_id.name, is_lot)
            
            if key not in product_quant_map:
                product_quant_map[key] = {
                    'product_id': quant.product_id,
                    'location': quant.location_id,
                    'lot_id': quant.lot_id,
                    'quantity': quant.quantity,
                    'uom': quant.product_uom_id.name,
                    'total_value': 0.0,
                    'average_price': 0.0,
                }
            total_value = 0.0
            average_price = 0.0
            b=0
            if not end_date:
                if quant.lot_id:#如果是捲料 則直接找捲料單價
                    b=1
                    lot_purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('order_id.state', 'in', ['purchase', 'done']),
                        ('order_id',"=",quant.lot_id.purchase_order_id.id)
                    ], order='date_order desc', limit=1)

                    # 如果找到了对应的采购单行，使用该批次的单价
                    if lot_purchase_lines:
                        if lot_purchase_lines.price_unit == 0:
                            average_price = quant.product_id.standard_price
                        else:
                            average_price = lot_purchase_lines.price_unit
                        # average_price = lot_purchase_lines.price_unit
                        total_value = abs(round(quant.quantity, 2)) * average_price
                    else:#如果找不到相同序號的 ，則找最近一個相同產品的
                        average_price = quant.product_id.standard_price
                        total_value = abs(round(quant.quantity, 2)) * average_price
                        
                else:#否則計算加權平均價格
                    # 否则使用加权平均价格计算
                    total_qty_needed = abs(round(quant.quantity, 2))
                    purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', quant.product_id.id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                    ], order='date_order desc')

                    qty_consumed = 0
                    for line in purchase_lines:
                        if total_qty_needed <= 0:
                            break
                        purchase_qty = line.product_qty
                        purchase_price = 0
                        if line.price_unit != 0:
                            purchase_price = line.price_unit
                        else:
                            purchase_price = line.product_id.standard_price

                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty

                    if total_qty_needed > 0 and qty_consumed == 0:
                        total_value = total_qty_needed * quant.product_id.standard_price
                        average_price = quant.product_id.standard_price                        
                    else:    
                        average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0

                if not is_print_zero:
                    if round(quant.quantity, 2) > 0:
                        report_data.append({
                            'product_id': quant.product_id,
                            'lot_id':quant.lot_id.name,
                            'quantity': round(quant.quantity, 2),
                            'uom': quant.product_uom_id.name,
                            'is_lot':b,
                            'location': quant.location_id.name,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': round(total_value, 2),  # 总价值
                        })
                else:
                    if round(quant.quantity, 2) >= 0:
                        report_data.append({
                            'product_id': quant.product_id,
                            'lot_id':quant.lot_id.name,
                            'quantity': abs(round(quant.quantity, 2)),
                            'uom': quant.product_uom_id.name,
                            'is_lot':b,
                            'location': quant.location_id.name,
                            'average_price': abs(round(average_price, 2)),  # 加权平均价格
                            'total_value': abs(round(total_value, 2)),  # 总价值
                        })
               
        if end_date:
            for location in internal_locations:
                move_lines_out = self.env['stock.move.line'].search([
                    ('location_id', '=', location.id),  # 出库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                for line in move_lines_out:
                    if line.product_id.name == "其他 (採購用)" or line.product_id.detailed_type not in ['product']:
                        continue
                    is_lot = line.lot_id.id if line.lot_id else 0
                    key = (line.product_id.id, location.name, is_lot)
                    # print(key)
                    qty_change = round(line.qty_done / line.product_uom_id.factor, 4) if line.lot_id and line.product_uom_id.name == "才" else line.qty_done

                    # 更新数量
                    if key in product_quant_map:
                        product_quant_map[key]['quantity'] += qty_change 
                    else:                        
                        product_quant_map[key] = {
                            'product_id': line.product_id,
                            'location': location.id,
                            'lot_id': line.lot_id,
                            'quantity': qty_change,
                            'uom': line.product_uom_id.name,
                            'total_value': 0.0,
                            'average_price': 0.0,
                        }          
                
                # print(len(product_quant_map))
                move_lines_in = self.env['stock.move.line'].search([
                    ('location_dest_id', '=', location.id),  # 入库
                    ('state', '=', 'done'),
                    ('date', '>', end_date)
                ])
                
                for line in move_lines_in:
                    if line.product_id.name == "其他 (採購用)" or line.product_id.detailed_type not in ['product']:
                        continue
                    is_lot = line.lot_id.id if line.lot_id else 0
                    key = (line.product_id.id, location.name, is_lot)
                    qty_change = round(line.qty_done / line.product_uom_id.factor, 4) if line.lot_id and line.product_uom_id.name == "才" else line.qty_done

                    # 更新数量
                    if key in product_quant_map:   
                        product_quant_map[key]['quantity'] -= qty_change 
                    else:                    
                        product_quant_map[key] = {
                            'product_id': line.product_id,
                            'location': location.id,
                            'lot_id': line.lot_id,
                            'quantity': qty_change,
                            'uom': line.product_uom_id.name,
                            'total_value': 0.0,
                            'average_price': 0.0,
                        }
                # print(len(product_quant_map))
            for (product_id, loc ,lot), data in product_quant_map.items():
            
                total_value = 0.0
                average_price = 0.0
                b = 0
                lot_name = ""
                if lot:#如果是捲料 則直接找捲料單價
                    # continue
                    b = 1
                    lot_obj = self.env['stock.lot'].browse(lot)
                    lot_name = lot_obj.name
                    lot_purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', product_id),
                        ('order_id.state', 'in', ['purchase', 'done']),
                        ('order_id',"=",lot_obj.purchase_order_id.id)
                    ], order='date_order desc', limit=1)

                    # 如果找到了对应的采购单行，使用该批次的单价
                    if lot_purchase_lines:
                        if lot_purchase_lines.price_unit == 0:
                            average_price = lot_purchase_lines.product_id.standard_price
                        else:
                            average_price = lot_purchase_lines.price_unit
                        total_value = abs(round(data['quantity'], 2)) * average_price
                    else:
                        average_price = self.env['product.product'].browse(product_id).standard_price
                        total_value = abs(round(data['quantity'], 2)) * average_price
                        
                else:#否則計算加權平均價格
                    # continue
                    # 否则使用加权平均价格计算
                    total_qty_needed = abs(round(data['quantity'], 2))
                    purchase_lines = self.env['purchase.order.line'].search([
                        ('product_id', '=', product_id),
                        ('order_id.state', 'in', ['purchase', 'done'])
                    ], order='date_order desc')

                    qty_consumed = 0
                    for line in purchase_lines:
                        if total_qty_needed <= 0:
                            break
                        purchase_qty = line.product_qty
                        purchase_price = 0
                        if line.price_unit != 0:
                            purchase_price = line.price_unit
                        else:
                            purchase_price = line.product_id.standard_price

                        if purchase_qty >= total_qty_needed:
                            total_value += total_qty_needed * purchase_price
                            qty_consumed += total_qty_needed
                            total_qty_needed = 0
                        else:
                            total_value += purchase_qty * purchase_price
                            qty_consumed += purchase_qty
                            total_qty_needed -= purchase_qty

                    
                    if total_qty_needed > 0 and qty_consumed == 0:
                        total_value = total_qty_needed * product_id.standard_price
                        average_price = product_id.standard_price                        
                    else:    
                        average_price = total_value / qty_consumed if qty_consumed > 0 else 0.0
                if not is_print_zero:
                    if round(data['quantity'], 2) > 0:
                        report_data.append({
                            'product_id': self.env['product.product'].browse(product_id),
                            'lot_id':  lot_name,
                            'quantity': round(data['quantity'], 2),
                            'uom': data['uom'],
                            'is_lot':b,
                            'location': loc,
                            'average_price': round(average_price, 2),  # 加权平均价格
                            'total_value': round(total_value, 2),  # 总价值
                        })
                else:
                    if round(data['quantity'], 2) >= 0:
                        report_data.append({
                            'product_id': self.env['product.product'].browse(product_id),
                            'lot_id':  lot_name,
                            'quantity': abs(round(data['quantity'], 2)),
                            'uom': data['uom'],
                            'is_lot':b,
                            'location': loc,
                            'average_price': abs(round(average_price, 2)),  # 加权平均价格
                            'total_value': abs(round(total_value, 2)),  # 总价值
                        })
                        
        
        # 按照仓库名称排序
        sorted_report_data = sorted(report_data, key=lambda x: (x['location'], -x['is_lot']  , x['product_id']))

        return {
            'doc_ids': docids,
            'docs': quants,
            'date' : end_date or datetime.today().strftime('%Y-%m-%d'),
            'doc_model': 'stock.quant',
            'data': sorted_report_data,  # 传递合并后的数据给报告
        }
        
    '''
    @api.model
    def _get_report_values(self, docids, data=None):
        internal_locations = self.env['stock.location'].search([('usage', '=', 'internal')])
        quants = self.env['stock.quant'].search([('location_id', 'in', internal_locations.ids)])
        for quant in quants:
            # 根据lot_id和location_id找到对应的stock.move.line
            move_lines = self.env['stock.move.line'].search([
                ('lot_id', '=', quant.lot_id.id),
                ('location_id', '=', 4)  # 根据您的描述，这里使用location_id=4
            ], limit=1)  # 假设我们只关心找到的第一条记录
            
            if move_lines:
                move = move_lines.move_id  # 从stock.move.line获取stock.move
                if move:
                    # 现在我们有了move对象，可以获取price_unit
                    quant.purchase_price = move.price_unit
                else:
                    quant.purchase_price = 0
            else:
                quant.purchase_price = 0
        
        return {
            'doc_ids': docids,
            'doc_model': 'stock.quant',
            'docs': quants,
            'data': data,
        }   
    '''
class Stockreportwizard(models.TransientModel):
    _name = 'dtsc.stockreportwizard'

    # 向导字段定义
    endtime = fields.Date('截止時間')
    is_print_zero = fields.Boolean('包含0庫存')
    select_method = fields.Selection([
        ("1","庫存表"),
        ("2","庫存表(金額)"),
        ("3","庫存表(展開)"),
    ],default='1' ,string="列印方式")
    
    
    def your_confirm_method(self):
        # docids = self.env["stock.quant"].search([])
        
        docids=[]
        data = {
            'endtime': self.endtime,
            'is_print_zero': self.is_print_zero,
            'select_method': self.select_method,
            'docids':docids,
        }
        
        if self.select_method == "1":
            return self.env.ref('dtsc.action_report_stock_quant3').report_action( docids, data)        
        elif self.select_method == "2":
            return self.env.ref('dtsc.action_report_stock_quant_amount3').report_action( docids, data)        
        elif self.select_method == "3":
            return self.env.ref('dtsc.action_report_stock_quant_base3').report_action( docids, data)
