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
import pytz
from pytz import timezone
import logging

_logger = logging.getLogger(__name__)
class LotMprScancode(models.Model):
    _name = "dtsc.lotmprscancode"
    
    barcode_input = fields.Char("條碼輸入") 
    
    @api.onchange('barcode_input')
    def _onchange_barcode_input(self):
        if self.barcode_input:
            self.barcode_input = self.barcode_input.lower()
            
    def clean_view(self):
        self.barcode_input = ""
    def open_form_view(self):
        parts = self.barcode_input.split('-')
        # print(parts)
        if len(parts) > 2 and len(parts) < 4:
            # print(self.barcode_input)
            stock_lot_obj = self.env['stock.lot'].search([('barcode', '=ilike', self.barcode_input)],limit=1)
            if stock_lot_obj:
                lotmprobj = self.env['dtsc.lotmpr'].search([('name', '=ilike', self.barcode_input)],limit=1)
                formid = 0
                if lotmprobj:
                    formid = lotmprobj.id
                else:
                    # print(self.barcode_input)
                    obj = self.env['dtsc.lotmpr'].create({
                       'name' : stock_lot_obj.barcode, 
                       'product_id' : stock_lot_obj.product_id.id,
                       'product_lot' : stock_lot_obj.id,
                    })
                    
                    self.env['dtsc.lotmprline'].create({
                       'name' : "邊料損耗", 
                       'yujixiaohao' : 25,
                       'sjkl' : 25,
                       "lotmpr_id" : obj.id,
                    })
                    formid = obj.id
                self.barcode_input = ""
                # print(formid)
                return{
                    'name' : '條碼產品扣料表',
                    'view_type' : 'form', 
                    'view_mode' : 'form',                    
                    'res_model' : 'dtsc.lotmpr',
                    'res_id' : formid,
                    'type' : 'ir.actions.act_window',
                    'view_id' : self.env.ref("dtsc.view_lotmpr_form").id
                   
                }
                
            else:
                self.barcode_input = ""
                # self.errorlog = "未找到此條碼在庫存中"
                raise ValidationError("未找到此條碼在庫存中!")
            # product = self.env['product.product'].search([('default_code', '=', parts[0])])
            # if product:
                # self.product_product_id = product.id
            # else:
                # raise UserError('未找到%s系列產品' %parts[0])
            # lot = self.env['stock.lot'].search([('barcode', '=', self.barcode_input)])
            # if lot:
                # self.product_lot = lot.id
        else:
            self.barcode_input = ""
            # self.errorlog = "掃入的條碼格式不正確"
            raise ValidationError("掃入的條碼格式不正確!")
        
class LotMpr(models.Model):
    _name = "dtsc.lotmpr"
    _order = "write_date desc"
    
    barcode_input = fields.Char("條碼輸入")
    lotmprline_id = fields.One2many("dtsc.lotmprline","lotmpr_id")
    name = fields.Char("條碼名稱")
    product_id = fields.Many2one('product.product',string="產品名稱")
    # lot_id = fields.Many2one('stock.lot',string="產品序號", compute="_compute_lot_id",store=True)
    state = fields.Selection([
        ("draft","待扣料"),
        ("succ","扣料完成"),   
    ],default='draft' ,string="狀態")
    product_lot = fields.Many2one("stock.lot" , "產品序號")
    lot_stock_num = fields.Char(string = "庫存" ,compute='_compute_lot_stock_num'  ,store=True) 
    final_stock_num = fields.Char(string = "消耗率") 
    uom_id = fields.Many2one(string = "單位" ,related='product_id.uom_id') 
    total_size = fields.Float("基礎總才數",compute='_compute_lot_stock_num')
    picking_id = fields.Many2one("stock.picking")
    barcode_backup = fields.Char("備選料號條碼")
    stock_move_id = fields.Many2one("stock.move")
    stock_move_line_id = fields.Many2many("stock.move.line")
    last_cai = fields.Char("剩餘才數",compute="_compute_last_cai")
    stock_location_id = fields.Many2one("stock.location", string="倉庫位置",compute="_compute_last_cai")
    succ_date = fields.Date(string='完成時間')    
    report_year = fields.Many2one("dtsc.year",string="年",compute="_compute_year_month",store=True)
    report_month = fields.Many2one("dtsc.month",string="月",compute="_compute_year_month",store=True) 
    
    
    @api.depends("succ_date")
    def _compute_year_month(self):
        invoice_due_date = self.env['ir.config_parameter'].sudo().get_param('dtsc.invoice_due_date')
        for record in self:
            if record.succ_date:
                current_date = record.succ_date           
                if current_date.day > int(invoice_due_date):
                    if current_date.month == 12:
                        next_date = current_date.replace(year=current_date.year + 1, month=1 ,day=1)
                    else:
                        next_date = current_date.replace(month=current_date.month + 1,day=1)
                else:
                    next_date = current_date
                    
                next_year_str = next_date.strftime('%Y')  # 两位数的年份
                next_month_str = next_date.strftime('%m')  # 月份
                
                year_record = self.env['dtsc.year'].search([('name', '=', next_year_str)], limit=1)
                month_record = self.env['dtsc.month'].search([('name', '=', next_month_str)], limit=1)

                record.report_year = year_record.id if year_record else False
                record.report_month = month_record.id if month_record else False
            else:
                record.report_year = False
                record.report_month = False
                
    @api.depends()
    def asyn_date(self):
        active_ids = self._context.get('active_ids')
        records = self.env["dtsc.lotmpr"].browse(active_ids)
        
        for record in records:
            print(record.state)
            if record.state == 'succ':
                record.succ_date = record.write_date.date()
            else:
                record.succ_date = False
                
    # stock_location_id_backup = fields.Many2one("stock.location", string="备选料倉庫位置",compute="_compute_stock_location_id_backup")
    
    # @api.depends('barcode_backup')
    # def _compute_stock_location_id_backup(self):
        # stock_lot_obj = self.env['stock.lot'].search([('barcode', '=', self.barcode_backup)],limit=1)
        # if stock_lot_obj:
            # location_ids = self.env["stock.location"].search([('usage' , "=" , "internal")])
            # found_quant = False
            # for location_id in location_ids:
                # quant = self.env["stock.quant"].search([('product_id' , "=" , stock_lot_obj.product_id.id ),("lot_id" ,"=" , stock_lot_obj.id),("location_id" ,"=" ,location_id.id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
                # if quant:
                    # if quant.quantity > 0:                        
                        # self.stock_location_id_backup = location_id.id
                        # found_quant = True
                        # break
            
            # if not found_quant:
                # self.stock_location_id_backup = False
        # else:
            # self.stock_location_id_backup = False
            
            
    @api.depends('lot_stock_num',"total_size")
    def _compute_last_cai(self):
        # self.last_cai = round(float(self.lot_stock_num) * self.total_size,2)
        try:
            lot_stock_num = float(self.lot_stock_num) if self.lot_stock_num not in ['無', ''] else 0.0
            self.last_cai = round(lot_stock_num * self.total_size, 2)
        except ValueError:
            self.last_cai = 0.0 
    
    def floor_to_one_decimal_place(self,number):
        return math.floor(number * 10) / 10
        
    @api.depends('product_id',"product_lot")
    def _compute_lot_stock_num(self):
        uom_obj = self.env["uom.uom"]
        for record in self:
            if record.product_lot.id:
                #同一卷料不会出现在不同仓库 所以遍历所有实体仓库
                location_ids = self.env["stock.location"].search([('usage' , "=" , "internal")])
                found_quant = False
                for location_id in location_ids:
                    quant = self.env["stock.quant"].search([('product_id' , "=" , record.product_id.id),("lot_id" ,"=" , record.product_lot.id),("location_id" ,"=" ,location_id.id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
                
                    if quant:
                        uom_record = uom_obj.browse(record.product_lot.product_uom_id.id)
                        now_category_id = uom_record.category_id.id
                        other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
                        if other_uom.name == "才":
                            # record.lot_stock_num = str(round(quant.quantity,1)) + "(" + str(round(quant.quantity * other_uom.factor,1)) +" 才)"
                            record.lot_stock_num = str(round(quant.quantity,3)) #+ "(" + str(self.floor_to_one_decimal_place(quant.quantity * other_uom.factor)) +" 才)"
                            record.total_size = 1 * other_uom.factor
                        else:
                            record.lot_stock_num = quant.quantity
                            record.total_size = quant.quantity
                        
                        record.stock_location_id = location_id.id
                        found_quant = True  # 标记为找到库存
                        break  # 找到库存后退出循环
                if not found_quant:
                    record.lot_stock_num = "無"
                    record.total_size = 0
                    record.stock_location_id = False
            else:
                record.lot_stock_num = "無"
                record.total_size = 0
                record.stock_location_id = False
                
    # @api.depends('product_id')
    # def _compute_lot_id(self):
        # for record in self
            # obj = self.env["stock.lot"].search([('product_id', '=', self.barcode_input)])
    #完成按鈕
    def confirm_btn(self):
        quant = self.env["stock.quant"].search([('product_id' , "=" , self.product_id.id),("lot_id" ,"=" , self.product_lot.id),("location_id" ,"=" ,self.stock_location_id.id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
        self.write({'final_stock_num': str(round(quant.quantity,3))})        
        if quant.quantity == 0:
            self.write({'state': "succ"})
            local_tz = pytz.timezone('Asia/Shanghai')  # 替換為你所在的時區
            
            today = datetime.now(local_tz).date()
            self.succ_date = today
        else:        
            picking = self.env['stock.picking'].create({
                'picking_type_id' : 1,
                'location_id': self.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产
                'origin' : self.name, 
            })
            self.picking_id = picking.id
            move = self.env['stock.move'].create({
                'name' : self.name,
                'reference' : "捲料完成", 
                'product_id': self.product_id.id,
                'product_uom_qty' : quant.quantity,
                'product_uom' : self.uom_id.id,
                "picking_id" : picking.id,
                "quantity_done" : quant.quantity,
                'origin' : self.name,
                'location_id': self.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产                
            })
            self.stock_move_id = move.id
            
            # stock_lot_obj = self.env['stock.lot'].search([('barcode', '=', self.name)],limit=1)
            move_line = self.env['stock.move.line'].create({
                'reference' : "捲料完成"+self.name, 
                'origin' : self.name,
                "move_id": move.id, 
                "picking_id" : picking.id,
                'product_id': self.product_id.id,
                'qty_done': quant.quantity ,
                'product_uom_id' : self.uom_id.id,                
                'location_id': self.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产 
                'lot_name' : self.product_lot.name,
                'lot_id': self.product_lot.id,
                'state': "draft", 
            })                
            self.stock_move_line_id = [(4, move_line.id)]
            move_line_objs = self.env['stock.move.line'].search(["|",("lot_id" ,"=" , False ),("lot_name" ,"=" , False ),("product_id" , "=" ,self.product_id.id ),('picking_id',"=", picking.id)])
            move_line_objs.unlink()
            
            picking.action_confirm()
            picking.action_assign()
            picking.button_validate() 
            self.write({'state': "succ"})
            local_tz = pytz.timezone('Asia/Shanghai')  # 替換為你所在的時區
            
            today = datetime.now(local_tz).date()
            self.succ_date = today
        
        
        
        # quant = self.env["stock.quant"].search([('product_id' , "=" , self.product_id.id),("lot_id" ,"=" , self.product_lot.id),("location_id" ,"=" ,self.stock_location_id.id)],limit=1) #這裡出現的負數我用company_id隱藏，未來要修正
        
        
    
    #恢復完成
    def back_btn(self):
        if not self.picking_id:
            self.write({'state': "draft"})
            self.write({'final_stock_num': "-"})
        else:
            reverse_picking_vals = {
                'picking_type_id': self.picking_id.picking_type_id.id,
                'location_id': self.picking_id.location_dest_id.id,
                'location_dest_id': self.picking_id.location_id.id,
                'origin': '退回完成捲料' + self.name,
            }
            reverse_picking = self.env['stock.picking'].create(reverse_picking_vals)
            for move in self.picking_id.move_ids:        
                reverse_move_vals = {
                    'name': move.name,
                    'reference': "退回完成捲料" + move.name,
                    'origin' : move.name,
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
                        # print(move_line.product_id.name)
                        # print(move_line.lot_id.name)
                        # print(move_line.lot_id.id)
                        reverse_move_line_vals = {
                            'reference' : "退回"+move.name, 
                            'origin' : move.name,
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
            reverse_picking.action_confirm()
            reverse_picking.action_assign()
            reverse_picking.button_validate()
            self.write({'state': "draft"})
            self.write({'final_stock_num': "-"})
        
    #扣料動作
    def ok_btn(self):
        count = 0
        for record in self.lotmprline_id:
            if record.state == "succ":
                continue
            if record.shengyu == 0:
                count = count + 1
        
        if count > 1:
            raise ValidationError("扣料超過2個項次多于此料，請檢查，如需用備料請加入備料序號，保留一個多餘項次!")
    
    
        uom_obj = self.env["uom.uom"]
        
        #當前庫存
        
        uomid = self.uom_id.id
        uom_record = uom_obj.browse(self.uom_id.id)
        now_category_id = uom_record.category_id.id
        other_uom = uom_obj.search([( 'category_id' , "=" , now_category_id ) , ("id","!=",uom_record.id)],limit=1)
        if other_uom:
            uomid = other_uom.id
        
        if self.lot_stock_num.isdigit():  # 检查是否是数字
            if int(self.lot_stock_num) < 0:
                raise ValidationError("此料無庫存!")
        elif self.lot_stock_num == "無":  # 检查是否为字符串 "無"
            raise ValidationError("此料無庫存!")
        
        now_stock_p = float(self.lot_stock_num) * other_uom.factor
        for record in self.lotmprline_id:
            if record.state == "succ":
                continue
            
            if record.sjkl == 0:
                qty_done_cai = record.yujixiaohao
            else: 
                qty_done_cai = record.sjkl


            # if (now_stock_p - record.yujixiaohao) < 0 :
            if (now_stock_p - qty_done_cai) < 0 :
                #如果不夠扣
                
                quant = self.env["stock.quant"].search([('product_id' , "=" , self.product_id.id),("lot_id" ,"=" , self.product_lot.id),("location_id" ,"=" ,self.stock_location_id.id)],limit=1) 
                # print(quant)
                if quant:
                    qty_done_cai = round(math.floor(quant.quantity * 100) / 100 * other_uom.factor ,2 )
                    other_qty_done = record.yujixiaohao - qty_done_cai
                    
                    if not self.barcode_backup:
                        raise ValidationError("扣料超過此料總庫存，請加入備選扣料料號!") 
                    parts = self.barcode_backup.split('-')
                    
                    if len(parts) > 2 and len(parts) < 4:                        
                        stock_lot_obj = self.env['stock.lot'].search([('barcode', '=', self.barcode_backup)],limit=1)
                        if stock_lot_obj:
                            lotmprobj = self.env['dtsc.lotmpr'].search([('name', '=', self.barcode_backup)],limit=1)
                            if lotmprobj:
                                self.env['dtsc.lotmprline'].create({
                                   'lotmpr_id' : lotmprobj.id,
                                   'name' : record.name,
                                   'other_qty_done': other_qty_done,
                                   'is_other_stock': True,
                                })
                            else:
                                obj = self.env['dtsc.lotmpr'].create({
                                   'name' : self.barcode_backup, 
                                   'product_id' : stock_lot_obj.product_id.id,
                                   'product_lot' : stock_lot_obj.id,
                                }) 
                                self.env['dtsc.lotmprline'].create({
                                   'lotmpr_id' : obj.id,
                                   'name' : record.name,
                                   'other_qty_done': other_qty_done,
                                   'is_other_stock': True,
                                })
                            #如果填了備選料，自動轉爲完成
                            self.write({'final_stock_num': '0'})   
                            self.write({'state': "succ"})
                            local_tz = pytz.timezone('Asia/Shanghai')  # 替換為你所在的時區
                            today = datetime.now(local_tz).date()
                            self.succ_date = today
                            
                        else:                            
                            raise ValidationError("未找到此條碼在庫存中!")
                      
                    else:                       
                        raise ValidationError("備選條碼格式不正確!")
                     
                
            #now_stock_p = now_stock_p - record.yujixiaohao
            now_stock_p = now_stock_p - qty_done_cai
            picking = self.env['stock.picking'].create({
                'picking_type_id' : 1,
                'location_id': self.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产
                'origin' : record.name, 
            })
            record.picking_id = picking.id
            move = self.env['stock.move'].create({
                'name' : record.name,
                'reference' : "工單扣料"+record.name, 
                'product_id': self.product_id.id,
                'product_uom_qty' : qty_done_cai,
                'product_uom' : uomid,
                "picking_id" : picking.id,
                "quantity_done" : qty_done_cai,
                'origin' : record.name,
                'location_id': self.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产                
            })
            record.stock_move_id = move.id
            
            stock_lot_obj = self.env['stock.lot'].search([('barcode', '=', self.name)],limit=1)
            move_line = self.env['stock.move.line'].create({
                'reference' : "工單扣料"+record.name, 
                'origin' : record.name,
                "move_id": move.id, 
                "picking_id" : picking.id,
                'product_id': self.product_id.id,
                'qty_done': qty_done_cai ,
                'product_uom_id' : uomid,                
                'location_id': self.stock_location_id.id,  #库存
                'location_dest_id': 15, #Production 用于生产 
                'lot_name' : stock_lot_obj.name,
                'lot_id': stock_lot_obj.id,
                'state': "draft",
            })                
            record.stock_move_line_id = [(4, move_line.id)]
            move_line_objs = self.env['stock.move.line'].search(["|",("lot_id" ,"=" , False ),("lot_name" ,"=" , False ),("product_id" , "=" ,self.product_id.id ),('picking_id',"=", picking.id)])
            move_line_objs.unlink()
            
            picking.action_confirm()
            picking.action_assign()
            picking.button_validate() 
            
            record.state = "succ" 
            record.sjkl = qty_done_cai 
                

class LotMprLine(models.Model):
    _name = "dtsc.lotmprline"    
    lotmpr_id = fields.Many2one("dtsc.lotmpr")
    name = fields.Char("工單項次")
    outman = fields.Many2one('dtsc.userlist',string="輸出", compute="_compute_sccz")
    sccz = fields.Char("輸出材質", compute="_compute_sccz")
    make_ori_product_id = fields.Many2one("product.template",string="基礎扣料物")
    yujixiaohao = fields.Float("預計消耗" , compute="_compute_sccz" ,store = True)
    shengyu = fields.Float("剩餘才數" , compute="_compute_shengyu" ) 
    is_other_stock = fields.Boolean(default=False)
    other_qty_done = fields.Float()
    state = fields.Selection([
        ("draft","待扣料"),
        ("succ","扣料完成"),   
    ],default='draft' ,string="狀態",readonly=True)
    picking_id = fields.Many2one("stock.picking") 
    stock_move_id = fields.Many2one("stock.move")
    stock_move_line_id = fields.Many2many("stock.move.line")
    sjkl = fields.Float("實際消耗")
    comment = fields.Char("備註")
    
    @api.constrains('name', 'lotmpr_id')
    def _check_name_unique(self):
        for record in self:
            # print(record.name)
            if self.search_count([
                ('name', '=', record.name),
                ('lotmpr_id', '=', record.lotmpr_id.id),
                ('id', '!=', record.id)
            ]) > 0:
                raise ValidationError("同一單不能出現兩個相同的項次!")

    
    
    
    def unlink(self):
        if any(line.lotmpr_id.state == 'succ' for line in self):
            raise UserError('不允許在此狀態下刪除記錄。')
            
        for record in self:
            # print(record.state)
            if record.state == "succ":
                if not record.picking_id or record.picking_id.state != 'done':
                    raise UserError('无有效的完成拣货操作，无法回退。')
                
                reverse_picking_vals = {
                    'picking_type_id': record.picking_id.picking_type_id.id,
                    'location_id': record.picking_id.location_dest_id.id,
                    'location_dest_id': record.picking_id.location_id.id,
                    'origin': '退回 ' + record.name,
                }
                reverse_picking = self.env['stock.picking'].create(reverse_picking_vals)
                for move in record.picking_id.move_ids:        
                    reverse_move_vals = {
                        'name': move.name,
                        'reference': "退回" + move.name,
                        'origin' : move.name,
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
                        # print("========================")
                        if move_line.lot_id:
                            # print(move_line.product_id.name)
                            # print(move_line.lot_id.name)
                            # print(move_line.lot_id.id)
                            reverse_move_line_vals = {
                                'reference' : "退回"+move.name, 
                                'origin' : move.name,
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
                reverse_picking.action_confirm()
                reverse_picking.action_assign()
                reverse_picking.button_validate()
            
            # self.unlink()
        return super(LotMprLine, self).unlink()
    
    
    def delete_btn(self):
        if self.state == "draft":
            self.unlink()
        elif self.state == "succ":
            if not self.picking_id or self.picking_id.state != 'done':
                raise UserError('无有效的完成拣货操作，无法回退。')
            
            reverse_picking_vals = {
                'picking_type_id': self.picking_id.picking_type_id.id,
                'location_id': self.picking_id.location_dest_id.id,
                'location_dest_id': self.picking_id.location_id.id,
                'origin': '退回 ' + self.name,
            }
            reverse_picking = self.env['stock.picking'].create(reverse_picking_vals)
            for move in self.picking_id.move_ids:        
                reverse_move_vals = {
                    'name': move.name,
                    'reference': "退回" + move.name,
                    'origin' : move.name,
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
                    # print("========================")
                    if move_line.lot_id:
                        # print(move_line.product_id.name)
                        # print(move_line.lot_id.name)
                        # print(move_line.lot_id.id)
                        reverse_move_line_vals = {
                            'reference' : "退回"+move.name, 
                            'origin' : move.name,
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
            reverse_picking.action_confirm()
            reverse_picking.action_assign()
            reverse_picking.button_validate()
            
            self.unlink()
            
            
            
    @api.depends("yujixiaohao")    
    def _compute_shengyu(self):
        lot_stock_num = float(self.lotmpr_id.lot_stock_num) if self.lotmpr_id.lot_stock_num not in ['無', ''] else 0.0
        tmp = self.lotmpr_id.total_size * float(lot_stock_num)
       
        for record in self.lotmpr_id.lotmprline_id:
            # print(record.name)
            if record.state == "succ":
                record.shengyu = False
            else:
                if (tmp - record.yujixiaohao) < 0:
                    record.shengyu = 0
                    tmp = 0
                else:
                    record.shengyu = tmp - record.yujixiaohao
                    tmp = tmp - record.yujixiaohao
            
                
            
    @api.depends("name")
    def _compute_sccz(self):
        for record in self:
            if record.name: 
                if record.name == "邊料損耗":
                    record.sccz = ""
                    record.outman = False
                    record.yujixiaohao = 25
                else:
                    parts = record.name.split('-')
                    if len(parts) > 1:
                        makein_obj = self.env["dtsc.makein"].search([('name','=',parts[0])],limit=1)
                        if makein_obj:
                            obj = self.env["dtsc.makeinline"].search([('make_order_id','=',makein_obj.id),("sequence","=",int(parts[1]))],limit=1)
                            
                            if obj:
                                record.sccz = obj.output_material
                                record.outman = obj.outman.id
                                if record.is_other_stock and record.other_qty_done:
                                    record.yujixiaohao = record.other_qty_done
                                else:
                                    record.yujixiaohao = obj.total_size
                            else:
                                record.sccz = ""
                                record.outman = False
                                record.yujixiaohao = False
                        else:
                            record.sccz = "沒有此工單號" + parts[0]
                            record.outman = False
                            record.yujixiaohao = False
                    else:
                        record.sccz = ""
                        record.outman = False
                        record.yujixiaohao = False
            else:
                    record.sccz = ""
                    record.outman = False
                    record.yujixiaohao = False
                # raise UserError('沒有此工單號%s' %parts[0])
                
    @api.model
    def create(self, vals):
        mpr_record = self.env['dtsc.lotmpr'].browse(vals.get('lotmpr_id'))
        if mpr_record.state == 'succ':
            raise UserError('不允許在已完成的捲料上添加記錄。')
    
    
        res = super(LotMprLine, self).create(vals)
        records = self.env['dtsc.lotmprline'].search([("name" , "=", False)])
        # print(records)
        records.unlink()
        return res

    def write(self, vals):
        if self.lotmpr_id.state == 'succ':
            raise UserError('不允許在此狀態下修改記錄。')
        # 删除name字段为空的记录
        if 'name' in vals and not vals['name']:
            self.unlink()
            return False
        return super(LotMprLine, self).write(vals)
        
        
        
