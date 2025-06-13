/* odoo.define('dtsc.FloatFieldCustom', function (require) {
"use strict";

var BasicFields = require('web.basic_fields');
var fieldRegistry = require('web.field_registry');

var FieldFloatCustom = BasicFields.FieldFloat.extend({
    _formatValue: function (value) {
        if (value % 1 === 0) { // 如果小数部分为0
            return value.toFixed(0); // 不显示小数
        }
        return this._super.apply(this, arguments); // 否则使用默认的格式化逻辑
    },
});

fieldRegistry.add('float_custom', FieldFloatCustom);

});
 */
odoo.define('dtsc.FloatFieldCustom', function (require) {
    "use strict";

    console.log("开始加载 FloatFieldCustom"); // 确认文件开始执行

    var FieldFloat = require('web.basic_fields').FieldFloat;
    var fieldRegistry = require('web.field_registry');

    var FloatFieldCustom = FieldFloat.extend({
        init: function () {
            this._super.apply(this, arguments);
            console.log("FloatFieldCustom 初始化"); // 确认构造函数被调用
        },
        _formatValue: function (value) {
            // 确认 _formatValue 方法被调用，及其处理的值
            console.log("FloatFieldCustom _formatValue 被调用, 值为:", value);
            return "测试";
        }
    });

    fieldRegistry.add('dtsc_float_custom', FloatFieldCustom);
    console.log("FloatFieldCustom 注册完成");

    return FloatFieldCustom;
});
