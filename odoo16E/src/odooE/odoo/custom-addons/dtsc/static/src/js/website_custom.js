odoo.define('dtsc.website_custom', function (require) {
    "use strict";

    var publicWidget = require('web.public.widget');
    var WebsiteSale = require('website_sale.website_sale'); // 强制引入 WebsiteSale

    console.log("WebsiteSale 模块:", WebsiteSale);

    if (!WebsiteSale) {
        console.error("WebsiteSale 模块未正确加载，请检查是否启用了 website_sale 模块！");
        return;
    }

    publicWidget.registry.WebsiteSale.include({
        init: function () {
            console.log("WebsiteSale 被扩展成功");
            this._super.apply(this, arguments);
        },
		
		_onChangeCartQuantity: function (ev) {
            ev.preventDefault(); // 阻止默认行为

            var $input = $(ev.currentTarget); // 当前触发事件的输入框
            var $row = $input.closest('tr'); // 获取当前行
            var $decreaseButton = $row.find('a.js_add_cart_json:has(.fa-minus)'); // 找到减数量按钮
            //var minQuantity = parseFloat($decreaseButton.data('min-quantity')); // 从按钮获取最小数量
            var minQuantity = parseFloat($input.data('min-quantity'));
            var currentQuantity = parseFloat($input.val()); // 当前数量
			
			if (currentQuantity === 0){
				this._super.apply(this, arguments);
				return;
			}
            console.log("当前数量:", currentQuantity, "最小数量:", minQuantity);

			if (isNaN(currentQuantity) || currentQuantity < minQuantity) {
				console.warn("输入的数量无效或小于最小数量，重置为最小数量");
				//alert(`The minimum quantity for this product is ${minQuantity}.`);
				$input.val(minQuantity); // 将输入框的值重置为最小数量
				currentQuantity = minQuantity; // 更新当前数量变量
			}


            // 根据数量动态禁用或启用按钮
            if (currentQuantity <= minQuantity) {
                console.warn("禁用减数量按钮，因为当前数量 <= 最小数量");
                $decreaseButton.prop('disabled', true); // 禁用按钮
            } else {
                console.log("启用减数量按钮，因为当前数量 > 最小数量");
                $decreaseButton.prop('disabled', false); // 启用按钮
            }

            // 调用原始逻辑
            this._super.apply(this, arguments);
        },
		
		async _onChangeCombination(ev, $parent, combination) {
            // 调用父类逻辑
            this._super.apply(this, arguments);

            // 检查组合信息中是否有 `min_quantity`
            if (combination && combination.min_quantity !== undefined) {
                console.log(`最小购买量: ${combination.min_quantity}`);

                // 存储 min_quantity 到 DOM 的数据中，供后续逻辑使用
                $parent.data('min_quantity', combination.min_quantity);

                // 获取当前数量输入框的值
                const $qtyInput = $parent.find('input[name="add_qty"]');
                const currentQty = parseFloat($qtyInput.val()) || 0;

                console.log(`当前数量: ${currentQty}, 最小购买量: ${combination.min_quantity}`);

                // 检查当前数量是否满足最小购买量
                if (currentQty < combination.min_quantity) {
                    console.warn(`数量不足，禁用按钮。当前数量 ${currentQty}, 最小购买量 ${combination.min_quantity}`);
                    
                    // 禁用按钮并显示警告
                    $parent.find('#add_to_cart').addClass('disabled').prop('disabled', true).css('pointer-events', 'none');
                    $parent.find('.js_min_qty_warning').remove(); // 避免重复插入
                    $parent.append(`<div class="js_min_qty_warning text-danger">
                        最小購買數量為 ${combination.min_quantity}，請增加數量後再試。
                    </div>`);
                } else {
                    console.info(`数量满足要求，启用按钮。当前数量 ${currentQty}, 最小购买量 ${combination.min_quantity}`);
                    
                    // 启用按钮并隐藏警告
                    $parent.find('#add_to_cart').removeClass('disabled').prop('disabled', false).css('pointer-events', 'auto');
                    $parent.find('.js_min_qty_warning').remove();
                }
            } else {
                console.warn("组合信息中未找到最小购买量！");
            }
        },
		
		/* _getCombinationInfo: function () {
            const result = this._super.apply(this, arguments); // 调用父类逻辑
            console.log("组合信息返回数据:", result);

            // 检查是否包含 min_quantity，并绑定到 DOM 元素
            const $form = $('div#o_wsale_cta_wrapper');
            if (result && result.min_quantity !== undefined) {
                $form.data('combination', result); // 绑定组合信息
                console.log(`已绑定最小购买量: ${result.min_quantity}`);
            } else {
                console.warn("组合信息中未找到最小购买量！");
            }
            return result;
        }, */

        /* _onChangeAddQuantity: function (ev) {
            console.log("调用 _onChangeAddQuantity 方法");

            this._super.apply(this, arguments);

            const $input = $(ev.currentTarget); // 当前的数量输入框
            const currentQty = parseFloat($input.val()) || 0; // 当前数量值

            const minQuantity = 5; // 示例：最小购买量为 2
            console.log(`当前数量: ${currentQty}, 最小购买量: ${minQuantity}`);

            const $form = $input.closest('div#o_wsale_cta_wrapper'); // 定位到整个 div 容器

            // 检查是否小于最小购买量
            if (currentQty < minQuantity) {
                console.warn(`数量不足，禁用按钮。当前数量 ${currentQty}, 最小购买量 ${minQuantity}`);

                // 禁用按钮并显示警告
                $form.find('#add_to_cart').addClass('disabled').prop('disabled', true).css('pointer-events', 'none');
                $form.find('.js_min_qty_warning').remove(); // 避免重复插入
                $form.append(`<div class="js_min_qty_warning text-danger">
                    最小購買數量為 ${minQuantity} 件，請增加數量後再試。
                </div>`);
            } else {
                console.info(`数量满足要求，启用按钮。当前数量 ${currentQty}, 最小购买量 ${minQuantity}`);

                // 启用按钮并隐藏警告
                $form.find('#add_to_cart').removeClass('disabled').prop('disabled', false).css('pointer-events', 'auto');
                $form.find('.js_min_qty_warning').remove();
            }
        }, */
    });
});


// Patch QWeb模板渲染，替换支付状态页面订单号为TEST123
/* odoo.define('dtsc.payment_display_tx_list_patch', function (require) {
    "use strict";
    var core = require('web.core');
    var qweb = core.qweb;

    var origRender = qweb.render;
    qweb.render = function (template, context) {
        if (template === 'payment.display_tx_list' && context) {
            // 遍历所有 tx_* 列表，把 reference 直接赋值
            ['tx_error', 'tx_done', 'tx_pending', 'tx_authorized', 'tx_draft', 'tx_cancel'].forEach(function (key) {
                if (context[key] && Array.isArray(context[key])) {
                    context[key].forEach(function (tx) {
                        tx.reference = '';
                    });
                }
            });
        }
        return origRender.apply(this, arguments);
    };
});
 */