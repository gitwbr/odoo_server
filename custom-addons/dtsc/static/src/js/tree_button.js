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

// patch(ListController.prototype, 'res_partner_tree_supp', PartnerListController);

// export class PartnerListRenderer extends ListRenderer {
	// setup() {
        // super.setup();
        // alert("2222")
    // }
	
// }
// patch(PartnerListRenderer.prototype, 'expense_list_renderer_qrcode', ExpenseMobileQRCode);
// patch(PartnerListRenderer.prototype, 'expense_list_renderer_qrcode_dzone', ExpenseDocumentDropZone);
// PartnerListRenderer.template = 'hr_expense.ListRenderer';

// export class ExpenseDashboardListRenderer extends PartnerListRenderer {}
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