odoo.define('dtsc.res_partner', function (require) {
    "use strict";
	var core = require('web.core');
    var FormController = require('web.FormController');
	/* var rpc = require('web.rpc');  
	console.log("start_res_partner");
    rpc.query({
		model: 'dtsc.unit_conversion',
		method: 'search_read',
		args: [[]],
		kwargs: {
			fields: ['name', 'conversion_formula'],
		},
	}).then(function(units) {
		var $selection = $('#unit-selection');
		$selection.empty();
		$.each(units, function(i, unit) {
			console.log(unit.name); // 将每个单位的名称打印到控制台
			$selection.append($('<option>').val(unit.id).text(unit.name).data('formula', unit.conversion_formula));
		});
	}); */

	console.log("end_res_partner");
});