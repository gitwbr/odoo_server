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
		
		/* _onChangeCartQuantity: function (ev) {
			var $input = $(ev.currentTarget);
			if ($input.data('update_change')) {
				return;
			}

			var value = parseInt($input.val() || 0, 10);
			if (isNaN(value)) {
				value = 1;
			}

			var $dom = $input.closest('tr');
			var $dom_optional = $dom.nextUntil(':not(.optional_product.info)');
			var line_id = parseInt($input.data('line-id'), 10);
			var productIDs = [parseInt($input.data('product-id'), 10)];

			// 调用原有逻辑，Odoo 后端会根据扩展的模型自动计算
			this._changeCartQuantity($input, value, $dom_optional, line_id, productIDs);
		}, */
		
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
