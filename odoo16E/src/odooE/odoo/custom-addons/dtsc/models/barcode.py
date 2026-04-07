from odoo import api, models, fields
import random
import string
import barcode
from barcode.writer import ImageWriter
from io import BytesIO
from PIL import Image
import base64
from datetime import datetime
import qrcode


class ProductionLot(models.Model):
    _inherit = "stock.lot"
    
    barcode = fields.Char("條碼", copy=False)
    barcode_image = fields.Binary("Barcode Image", compute='_generate_qrcode_image', store=True)
    purchase_order_id = fields.Many2one('purchase.order', string='採購訂單')
    _order = 'create_date desc, product_id , name'
    
    def _generate_unique_barcode(self):
        """Generate a unique barcode based on product's default_code, lot number, and current date."""
        product_default_code = self.product_id.default_code or "UNKNOWN"
        lot_name = self.name or "0"
        current_date = datetime.now().strftime("%Y%m%d")
        # barcode = f"{product_default_code}-{current_date}-{lot_name}"
        barcode = f"{product_default_code}-{lot_name}"
        return barcode
    # @api.model
    # def create(self, vals):
        # lot = super().create(vals)
        # lot.barcode = lot._generate_unique_barcode()
        # return lot
    
    def unlink(self):
        quantObj = self.env["stock.quant"].search([('product_id',"=",self.product_id.id),("lot_id","=",self.id)])
        # print(quantObj)
        if quantObj:        
            quantObj.unlink()
            

        # 调用父类的 unlink 方法来实际删除记录
        result = super(ProductionLot, self).unlink()
        return result    
        
    
    @api.model
    def create(self, vals):
        # 首先调用父类的create方法创建记录
        lot = super().create(vals)
        
        # 为新创建的记录生成唯一的条形码
        lot.barcode = lot._generate_unique_barcode()

        # 接下来添加寻找匹配的采购订单的逻辑
        # 这是一个示例，您需要根据自己的业务需求来调整这部分
        product_id = vals.get('product_id', False)
        if product_id:
            # 假设基于产品ID寻找最近的匹配的采购订单
            purchase_order_line = self.env['purchase.order.line'].search([('product_id', '=', product_id)], limit=1)
            if purchase_order_line:
                lot.purchase_order_id = purchase_order_line.order_id.id

        # 返回更新后的记录
        return lot
    
    # def _generate_unique_barcode(self):
        # """Generate a unique barcode for the production lot."""
        # while True:
            # barcode = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
            # if not self.search([('barcode', '=', barcode)]):
                # return barcode

    # @api.model_create_multi
    # def create(self, vals_list):
        # for vals in vals_list:
            # if not vals.get('barcode'):
                # vals['barcode'] = self._generate_unique_barcode()
        # return super(ProductionLot, self).create(vals_list)
        
    # @api.depends('barcode')
    # def _generate_barcode_image(self):
        # for record in self:
            # if record.barcode:
                # barcode_type = barcode.get_barcode_class('code128')
                # barcode_obj = barcode_type(record.barcode, writer=ImageWriter())

                # buffer = BytesIO()
                # barcode_obj.write(buffer)

                # barcode_data = base64.b64encode(buffer.getvalue()).decode('utf-8')  # 使用buffer的内容

                # record.barcode_image = barcode_data
                
    @api.depends('barcode')
    def _generate_qrcode_image(self):
        for record in self:
            if record.barcode:
                # 创建一个二维码对象
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(record.barcode)
                qr.make(fit=True)

                # 将二维码转换为图像
                img = qr.make_image(fill_color="black", back_color="white")

                buffer = BytesIO()
                img.save(buffer, format="PNG")
                buffer.seek(0)
                qr_data = base64.b64encode(buffer.getvalue()).decode('utf-8')

                record.barcode_image = qr_data