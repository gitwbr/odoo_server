/** @odoo-module **/

import { _lt } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { ListController } from "@web/views/list/list_controller";
import { patch } from '@web/core/utils/patch';

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
	  
	  // this.actionService.doAction({
            // res_model: mainObject.model,
            // res_id: mainObject.id,
            // views: [[false, "form"]],
            // type: "ir.actions.act_window",
            // view_mode: "form",
        // });
	  
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