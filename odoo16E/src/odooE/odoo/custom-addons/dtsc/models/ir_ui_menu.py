from odoo import models, api
# 臨時權限 
class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    # @api.model
    # def get_user_roots(self):
        # # 获取根菜单
        # roots = super(IrUiMenu, self).get_user_roots()
        # print("=== Dynamic get_user_roots called ===")

        # if self.env.user.has_group('dtsc.group_dtsc_disable'):
            # print("User belongs to dtsc.group_dtsc_disable")

            # # 尝试获取需要过滤的菜单
            # menu_to_filter = self.env.ref('dtsc.purchase', raise_if_not_found=False)
            # if menu_to_filter:
                # print(f"Menu to filter: {menu_to_filter.id}, Name: {menu_to_filter.name}")
                
                # # 遍历根菜单，找到「印刷訂單系統」的子菜单
                # for root_menu in roots:
                    # if root_menu.id == self.env.ref('dtsc.menu_root').id:  # 确保是「印刷訂單系統」
                        # # 过滤子菜单
                        # filtered_children = root_menu.child_id.filtered(
                            # lambda menu: menu.id != menu_to_filter.id
                        # )
                        # print(f"Filtered child menus: {[child.name for child in filtered_children]}")

                        # # 返回新的菜单对象而不是直接修改 child_id
                        # root_menu = root_menu.with_context(child_id=filtered_children)

        # print(f"Roots after filtering: {[menu.name for menu in roots]}")
        # return roots
   
        
    @api.model
    def search(self, args, offset=0, limit=None, order=None, count=False):
        if self.env.user.has_group('dtsc.group_dtsc_disable'):
            # 收集需要過濾的菜單
            menus_to_filter = [
                # self.env.ref('dtsc.purchase', raise_if_not_found=False),
                self.env.ref('dtsc.yszd', raise_if_not_found=False),
                self.env.ref('dtsc.yfzd', raise_if_not_found=False),
                self.env.ref('dtsc.menu_chart_dashboard_root', raise_if_not_found=False),
            ]
            # 過濾掉 None 的菜單（確保菜單存在）
            menu_ids_to_filter = [menu.id for menu in menus_to_filter if menu]
            if menu_ids_to_filter:
                args += [('id', 'not in', menu_ids_to_filter)]
        
        if self.env.user.has_group('dtsc.group_dtsc_disable_cg'):
            menus_to_filter = [
                self.env.ref('dtsc.purchase', raise_if_not_found=False),
            ]
            menu_ids_to_filter = [menu.id for menu in menus_to_filter if menu]
            if menu_ids_to_filter:
                args += [('id', 'not in', menu_ids_to_filter)]

        if self.env.user.has_group('dtsc.group_dtsc_disable_bb'):
            menus_to_filter = [
                self.env.ref('dtsc.menu_chart_dashboard_root1', raise_if_not_found=False),
            ]
            menu_ids_to_filter = [menu.id for menu in menus_to_filter if menu]
            if menu_ids_to_filter:
                args += [('id', 'not in', menu_ids_to_filter)]
                
        if self.env.user.has_group('dtsc.group_dtsc_disable_ysyf'):
            # 收集需要過濾的菜單
            menus_to_filter = [
                self.env.ref('dtsc.yszd', raise_if_not_found=False),
                self.env.ref('dtsc.yfzd', raise_if_not_found=False),
                self.env.ref('dtsc.menu_chart_dashboard', raise_if_not_found=False),
                self.env.ref('dtsc.menu_sales_chart_dashboard', raise_if_not_found=False),
                self.env.ref('dtsc.menu_machine_chart_dashboard', raise_if_not_found=False),
                self.env.ref('dtsc.menu_product_chart_dashboard', raise_if_not_found=False),
                self.env.ref('dtsc.menu_makeout_chart_dashboard', raise_if_not_found=False),
                self.env.ref('dtsc.menu_order_preview', raise_if_not_found=False),
                self.env.ref('dtsc.menu_make_order_preview', raise_if_not_found=False),
            ]
            # 過濾掉 None 的菜單（確保菜單存在）
            menu_ids_to_filter = [menu.id for menu in menus_to_filter if menu]
            if menu_ids_to_filter:
                args += [('id', 'not in', menu_ids_to_filter)]
                
        return super(IrUiMenu, self).search(args, offset, limit, order, count)