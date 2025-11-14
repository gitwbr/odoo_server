/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { ListController } from "@web/views/list/list_controller";
import { patch } from '@web/core/utils/patch';
import { WebsitePreview } from "@website/client_actions/website_preview/website_preview";



const { onWillStart } = owl;
export class PartnerListControllerS extends ListController {
    setup() {
        super.setup();
    }
	
	OnTestClick() {
	   this.actionService.doAction({
          type: 'ir.actions.act_url',
          url: '/download_excel_supp',
          target: 'self',
      });
	  
   }

}
export class PartnerListControllerC extends ListController {
    setup() {
        super.setup();
    }
	
	OnTestClick() {
       
	   this.actionService.doAction({
          type: 'ir.actions.act_url',
          url: '/download_excel_custom',
          target: 'self',
      });
   }

}
export class InstallProductListControllerS extends ListController {
    setup() {
        super.setup();
    }
	
	OnTestClick() {
	   this.actionService.doAction({
          type: 'ir.actions.act_window',
          views: [[false, "form"]],
		  view_mode: "form",
          res_model: 'dtsc.reportmounthinstall',
          target: 'new',
      });
	  
	  
   }

}
export class PartnerListControllerA extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
    }
	
	async OnTestClick() {
		try {
            await this.orm.call("dtsc.attendance", "action_run_missing_attendance", [], {});
            this.notification.add("已執行：缺卡檢測完成", { type: "success" });
			await this.actionService.doAction({ type: "ir.actions.client", tag: "reload" })
        } catch (e) {
            this.notification.add("執行失敗：" + (e?.message || ""), { type: "danger" });
            // console.error(e);
        }
   }

}

registry.category('views').add('InstallProductClass', {
    ...listView,
    buttonTemplate: 'InstallProduct.ListButtons',
    Controller: InstallProductListControllerS,
});
registry.category('views').add('res_partner_tree_supp', {
    ...listView,
    buttonTemplate: 'DtscPartner.ListButtons',
    Controller: PartnerListControllerS,
    // Renderer: PartnerListRenderer,
});
registry.category('views').add('res_partner_tree_custom', {
    ...listView,
    buttonTemplate: 'DtscPartner.ListButtons',
    Controller: PartnerListControllerC,
    // Renderer: PartnerListRenderer,
});
registry.category('views').add('dtsc_attendance_tree', {
    ...listView,
    buttonTemplate: 'Attendance.ListButtons',
    Controller: PartnerListControllerA,
    // Renderer: PartnerListRenderer,
});