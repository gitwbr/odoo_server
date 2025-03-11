odoo.define('dtsc.test', function(require) {
    "use strict";

    var core = require('web.core');
    var ajax = require('web.ajax');
    var AbstractAction = require('web.AbstractAction');

    var TestPage = AbstractAction.extend({
        template: "TestPageTemplate",
        events: {
            'change #unit-selection': '_onUnitChange',
            'input .param-input': '_onParamInput',
        },
        start: function () {
            var self = this;
            return this._super.apply(this, arguments)
                .then(function () {
                    self._fetchUnits();
                });
        },
        _fetchUnits: function () {
            var self = this;
            return ajax.jsonRpc("/web/dataset/call_kw", "call", {
                model: 'dtsc.unit_conversion',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name', 'conversion_formula'],
                },
            }).then(function (units) {
                self.units = units;
                self._updateUnitSelection();
            });
        },
        _updateUnitSelection: function () {
            var $selection = this.$('#unit-selection');
            $selection.empty();
            _.each(this.units, function (unit) {
                $selection.append($('<option>').val(unit.id).text(unit.name));
            });
            this._updateCurrentUnit();
        },
        _updateCurrentUnit: function () {
            var selectedId = parseInt(this.$('#unit-selection').val());
            this.currentUnit = _.findWhere(this.units, {id: selectedId});
        },
        _onUnitChange: function () {
            this._updateCurrentUnit();
            this._calculateResult();
        },
        _onParamInput: function () {
            this._calculateResult();
        },
        _calculateResult: function () {
            var param1 = parseFloat(this.$('#param1').val());
            var param2 = parseFloat(this.$('#param2').val());
            var result;
            // 注意这里使用了 eval，可能会有安全问题
            eval(this.currentUnit.conversion_formula);
            this.$('#result').text(result);
        },
    });

    core.action_registry.add('test_action', TestPage);
});
