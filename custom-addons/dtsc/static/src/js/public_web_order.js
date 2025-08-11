/*
================================================================================
Odoo16 前端下单页面 public_web_order.js 详细结构与开发说明
================================================================================

【文件定位与业务场景】
- 负责Odoo前台下单页面的所有前端交互、动态表单、自动填充、联动、文件上传、后加工方式等复杂逻辑。
- 典型场景：广告/印刷行业客户自助下单，支持多产品、多属性、多后加工方式、文件自动解析。

--------------------------------------------------------------------------------
【1. 依赖与工具函数】
- Widget、rpc：Odoo标准依赖。
- debugLog(message, data)：调试日志，debugMode控制。
- rpcQuery/model, method, domain, fields/：通用Odoo RPC调用，返回Promise。
- rpcQuery2/model, method, domain, data/：带自定义kwargs的RPC调用。
- waitAndSelectProductTemplate/Variant：辅助等待下拉框渲染并选中，自动填充用。

--------------------------------------------------------------------------------
【2. 主类 CheckoutWidget】
- 属性初始化：
    - 用户信息：partner_id, customer_class_id, custom_init_name, isInternalUser, isFixedCustomerMode
    - 业务标志：nop（无价格模式）、isSubmitting（下单中）、previewRecordId（预览ID）
    - 单位换算：conversion_formula, rounding_method
- 生命周期：
    - start()：页面入口，拉取用户、单位换算、事件绑定、弹窗初始化
    - fillCurrentUserInfo()：获取当前用户信息，决定客户/内部模式
    - fetchUnitConversion()：拉取单位换算公式和取整方式

--------------------------------------------------------------------------------
【3. 事件绑定与表单交互】
- bindEvents()：统一入口，调用各类事件绑定
- bindParamInputEvents()：尺寸输入联动，自动计算才数/数量
- bindFileInputEvents()：文件上传、自动填充（文件名解析、属性自动选中）
- bindProductCategoryEvents()：产品类型、模板、属性下拉框联动
- 其他事件：预览、下单、校验弹窗、删除产品、添加产品等
- 事件绑定建议用命名空间，防止重复绑定。

--------------------------------------------------------------------------------
【4. UI渲染与动态表单】
- createBannerTable(selectedCustomer, categories)：生成每个产品表格（含上传控件、产品选择、属性、备注等tr）
- renderProductHeaderRow()：生成表头tr（宽度、高度、数量等）
- renderProductInputRow()：生成输入tr（input/下拉框等）
- renderPostProcessSection(postProcessList)：生成后加工方式tr（复选框、数量输入）
- renderCommentRow()：生成备注tr
- clearDynamicRows($table)：清理所有动态tr，防止重复插入
- 动态tr class统一：如 .tr_product_attribute_class、.product_attribute_checkboxs.tr_product_attribute_class、.tr_post_process_section、.tr_comment_row
- 典型tr结构：
    - 表头tr：<tr class="table-active tr_product_attribute_class">...</tr>
    - 输入tr：<tr class="product_attribute_class input_row_class tr_product_attribute_class">...</tr>
    - 后加工tr：<tr class="table-active product_attribute_class tr_product_attribute_class">...</tr> + <tr class="product_attribute_checkboxs tr_product_attribute_class">...</tr>
    - 备注tr：<tr class="product_attribute_class tr_product_attribute_class">...</tr>

--------------------------------------------------------------------------------
【5. 自动填充与属性联动】
- onFileInputChange($fileInput)：文件上传后自动解析文件名，自动选中产品类型、模板、属性、尺寸、数量
- autoFillFormByFileName($table, fileName)：只设置属性值，不触发change，最后统一判断并触发一次联动
- waitForAttributeDropdowns($table, expectedCount)：辅助等待所有属性下拉框渲染完毕
- onAllAttributesSelected($table, selectedProductId)：所有属性选完后，生成后续输入行、后加工方式、备注等
- 兼容手动流程：手动选择属性时也会触发同样的后续生成逻辑
- 典型调用链：文件上传change → 自动填充属性 → 检查全部选完 → 只触发一次属性联动 → 生成后续tr

--------------------------------------------------------------------------------
【6. 业务逻辑与数据处理】
- collectFormData()：收集所有表单数据，组装成结构化对象
- validateFormData(formData)：校验表单必填项，返回缺失字段
- uploadAllFiles()：批量上传所有产品文件，返回Promise
- uploadFile($table)：单文件上传，含分片、进度条、表单比对
- submitOrder(orderData)：组装下单数据并提交到后端
- generateTableContent(formData)：生成预览表格HTML
- previewOrder()：预览订单明细，校验并弹窗
- showValidationModal(missingFields)：弹窗显示缺失字段
- 典型数据流：表单收集 → 校验 → 文件上传 → 组装数据 → 提交下单 → 预览/弹窗

--------------------------------------------------------------------------------
【7. 入口与页面ready】
- $(document).ready()：只做一次性实例化CheckoutWidget，挂到window方便全局调用

--------------------------------------------------------------------------------
【8. 典型异步流程说明】
- 自动填充时，先设置所有属性值，等待所有下拉框渲染完毕，最后只触发一次属性联动，防止重复插入。
- 属性联动、后加工方式生成等全部promise化，确保顺序和唯一性。
- 动态tr插入前先清理，所有tr加统一class，防止页面重复。
- 文件上传分片、进度条、表单比对、上传状态提示等全部promise化，便于链式调用。

--------------------------------------------------------------------------------
【9. 常见坑点与维护建议】
- 自动补全和手动流程要兼容，事件不要多次触发。
- 动态tr插入、清理要彻底，class统一，插入前先清理。
- 事件绑定用命名空间，防止重复绑定。
- 关键函数、变量、流程全部加详细注释，命名规范。
- 业务逻辑、UI渲染、事件监听彻底分离，便于维护和扩展。
- 典型bug：属性自动补全时多次触发change导致tr重复，需只在全部选完后统一触发一次。
- 典型bug：异步race condition导致tr插入顺序错乱，需promise化保证顺序。

================================================================================
*/
odoo.define('dtsc.public_web_order', function (require) {
    "use strict";
	var debugMode = true;
	//var debugMode = false;
	//var session = require('web.session'); 
    var Widget = require('web.Widget');
    var rpc = require('web.rpc');
    function debugLog(message, data) {
        if (debugMode) console.log(message, data);
    }

    async function rpcQuery(model, method, domain, fields) {
        try {
            return await rpc.query({
                model,
                method,
                domain,
                kwargs: { fields },
            });
        } catch (error) {
            console.error(`rpc.query错误，模型为${model}:`, error);
            return null;
        }
    }
	
	async function rpcQuery2(model, method, domain, data) {
		try {
			return await rpc.query({
				model,
				method,
				domain,
				kwargs: data
			});
		} catch (error) {
			console.error(`rpc.query错误，模型为${model}:`, error);
			return null;
		}
	}
	
    var CheckoutWidget = Widget.extend({
			init: function() {
			this._super.apply(this, arguments);
			this.partner_id = 0; 
			this.customer_class_id = 0; 
			this.custom_init_name = ''; 
			this.nop = false; 
			this.isSubmitting = false; // 添加订单提交状态标志位
			this.previewRecordId = null; // 预览记录ID
			this.isFixedCustomerMode = false; // 是否为固定客户模式
		},
        start: function () {
			this.conversion_formula="";
			this.rounding_method="";
            this._super.apply(this, arguments);
            // 统一入口，先尝试获取当前用户信息，判断类型后决定模式
            this.fillCurrentUserInfo();
            this.fetchUnitConversion();
            this.bindParamInputEvents(); 
            // 统一注册所有 change 事件代理
            this.registerGlobalChangeEvents();
        },
        registerGlobalChangeEvents: function() {
            const self = this;
            // 产品类型
            $(document).off('change', '.product_category');
            $(document).on('change', '.product_category', async function() {
                $(this).closest('table').find('.product_category_2').closest('td').remove();
                $(this).closest('table').find('.product_variant').closest('td').remove();
                var selectedCategId = $(this).val();
                debugLog("initProductCategoryChangeListener=>:selectedCategId:", selectedCategId);
                $(this).closest('tr').find('td').has('.product_category_2').remove();
                if (selectedCategId) {
                    var productCategory2 = $('<select>').addClass('form-control product_category_2');
                    var newTd = $('<td colspan="3">').css('width', '50%').append(
                        $('<div>').addClass('form-group').append(productCategory2)
                    );
                    $(this).closest('tr').append(newTd);
                    productCategory2.empty();
                    productCategory2.append($('<option>').attr({disabled: '1', selected: '1'}).text(' -- 請選擇產品模板 -- '));
                    try {
                        const dtsc_products = await rpcQuery('dtsc.quotation', 'search_read', [['customer_class_id', '=', self.customer_class_id]], ['product_id']);
                        console.table(dtsc_products);
                        var productIds = dtsc_products.map(item => item.product_id[0]);
                        const all_products = await rpcQuery('product.template', 'search_read', [['id', 'in', productIds]], ['name', 'categ_id']);
                        $.each(all_products, function(i, product) {
                            if (product.categ_id[0] === parseInt(selectedCategId)) {
                                productCategory2.append($('<option>').val(product.id).text(product.name));
                            }
                        });
                    } catch (error) {
                        console.error("发生错误：", error);
                    }
                }
            });
            // 产品模板
            $(document).off('change', '.product_category_2');
            $(document).on('change', '.product_category_2', async function() {
                $(this).closest('table').find('.product_variant').closest('td').remove();
                var selectedProductId = $(this).val();
                debugLog("Category2 customer_class_id:", self.customer_class_id);
                debugLog("Selected Product ID:", selectedProductId);
                $(this).closest('tr').find('td').has('.product_variant').remove();
                $(this).closest('tr').find('input[type="hidden"]').remove();
                if (selectedProductId) {
                    try {
                        const quotations = await rpcQuery('dtsc.quotation', 'search_read', [
                            ['customer_class_id', '=', self.customer_class_id],
                            ['product_id', '=', parseInt(selectedProductId)]
                        ], ['id', 'base_price']);
                        let basePrice = quotations.length > 0 ? quotations[0].base_price : null;
                        let quotationId = quotations.length > 0 ? quotations[0].id : null;
                        var basePriceInput = $('<input>').attr({
                            type: 'hidden',
                            id: 'base_price',
                            name: 'base_price',
                            value: basePrice
                        });
                        var quotationIdInput = $('<input>').attr({
                            type: 'hidden',
                            id: 'quotation_id',
                            name: 'quotation_id',
                            value: quotationId
                        });
                        $(this).closest('tr').append(basePriceInput, quotationIdInput);
                        const attributeLines = await rpcQuery('product.template.attribute.line', 'search_read', [['product_tmpl_id', '=', parseInt(selectedProductId)]], ['attribute_id','sequence']);
                        attributeLines.sort((a, b) => a.sequence - b.sequence);
                        debugLog("attributeLines:", attributeLines);
                        let tdCount = 2;
                        let currentTr = $(this).closest('tr');
                        for (let line of attributeLines) {
                            var attributeId = line.attribute_id[0];
                            debugLog("attributeId:", attributeId);
                            const attributeValues = await rpcQuery('product.template.attribute.value', 'search_read', [
                                ['attribute_id', '=', attributeId],
                                ['product_tmpl_id', '=', parseInt(selectedProductId)]
                            ], ['product_attribute_value_id', 'name']);
                            let filteredValues = [];
                            for (let value of attributeValues) {
                                let attributeValueDetail = await rpcQuery('product.attribute.value', 'search_read', [
                                    ['id', '=', value.product_attribute_value_id[0]]
                                ], ['sequence', 'is_visible_on_order'], { order: 'sequence ASC, id ASC' });
                                let nameZhTW;
                                try {
                                    const nameObj = JSON.parse(value.name);
                                    nameZhTW = nameObj['zh_TW'] || value.name;
                                } catch (error) {
                                    nameZhTW = value.name;
                                }
                                if (attributeValueDetail.length > 0 && attributeValueDetail[0].is_visible_on_order) {
                                    filteredValues.push({
                                        id: value.product_attribute_value_id[0],
                                        name: nameZhTW,
                                        sequence: attributeValueDetail[0].sequence || 0
                                    });
                                }
                            }
                            filteredValues.sort((a, b) => a.sequence - b.sequence);
                            debugLog("Filtered and sorted by sequence attributeValues:", filteredValues);
                            var variantSelect = $('<select>').addClass('form-control product_variant');
                            variantSelect.attr('name', line.attribute_id[1]);
                            var newTd = $('<td colspan="3">').css('width', '50%').append(
                                $('<div>').addClass('form-group').append(variantSelect)
                            );
                            var defaultOptionText = ` -- 請選擇${line.attribute_id[1]}屬性 -- `;
                            variantSelect.append($('<option>').attr({ disabled: '1', selected: '1' }).text(defaultOptionText));
                            $.each(filteredValues, function (j, value) {
                                variantSelect.append($('<option>').val(value.id).text(value.name));
                            });
                            if (tdCount >= 2) {
                                currentTr = $('<tr>');
                                $(this).closest('table').append(currentTr);
                                tdCount = 0;
                            }
                            currentTr.append(newTd);
                            tdCount++;
                        }
                        var $table = $(this).closest('table');
                        $table.find('.product_attribute_checkboxs.tr_product_attribute_class, .tr_post_process_section').remove();
                        const productMakeTypeRelResults = await rpcQuery(
                            'product.maketype.rel',
                            'search_read',
                            [['product_id', '=', parseInt(selectedProductId)]],
                            ['make_type_id', 'sequence'],
                            { order: 'sequence ASC, id ASC' }
                        );
                        debugLog("productMakeTypeRelResults:", productMakeTypeRelResults);
                        if (productMakeTypeRelResults && productMakeTypeRelResults.length > 0) {
                            productMakeTypeRelResults.sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
                            var headerTr = $('<tr>').addClass('table-active product_attribute_class tr_product_attribute_class tr_post_process_section');
                            var headerTh = $('<th>').css('text-align','unset').attr('colspan', '6').text('後加工方式, 此區塊估價將由業務人員與您討論後提供');
                            headerTr.append(headerTh);
                            $table.append(headerTr);
                            let currentRow;
                            for (let i = 0; i < productMakeTypeRelResults.length; i++) {
                                const postProcess = productMakeTypeRelResults[i];
                                debugLog("後加工",postProcess.make_type_id[1]);
                                if (i % 3 === 0) {
                                    currentRow = $('<tr>').addClass('product_attribute_checkboxs tr_product_attribute_class tr_post_process_section');
                                    $table.append(currentRow);
                                }
                                var newTdCheckbox = $('<td>').attr('colspan', '2');
                                var newDivCheckbox = $('<div>').css('text-align', 'left').addClass('form-check');
                                var newLabelCheckbox = $('<label>').addClass('form-check-label');
                                var newInputCheckbox = $('<input>').css({'margin': '0 10px 0 0'}).attr({ type: 'checkbox', name: 'multiple[]', value: postProcess.make_type_id[0], id: postProcess.id });
                                var quantityLabel = $('<label>').css({ 'margin-left': '10px', 'margin-right': '5px' }).text('數量:');
                                var quantityInput = $('<input>')
                                    .attr({ type: 'text', name: `quantity_${postProcess.make_type_id[0]}`, value: '1' })
                                    .css({ width: '50px', 'margin-left': '5px' });
                                newLabelCheckbox.append(newInputCheckbox).append(postProcess.make_type_id[1]);
                                newDivCheckbox.append(newLabelCheckbox).append(quantityLabel).append(quantityInput);
                                newTdCheckbox.append(newDivCheckbox);
                                currentRow.append(newTdCheckbox);
                            }
                        }
                    } catch (error) {
                        console.error("An error occurred:", error);
                    }
                }
            });
            // 产品属性
            $(document).off('change', '.product_variant');
            $(document).on('change', '.product_variant', function() {
                debugLog("product_variant选择事件");
                var acc_value = $(this).closest('table').find("select[name='配件'] option:selected").text();
                var $inputTd = $(this).closest('table').find('td.accessory-input-td');
                var $accessoryInput = $inputTd.find('input#accessory_qty');
                debugLog("acc_value",acc_value)
                if (acc_value && acc_value !== '不加配件') {
                    $accessoryInput.prop('disabled', false);
                    $accessoryInput.val(1);
                } else {
                    $accessoryInput.prop('disabled', true).val('');
                }
            });
        },
        fillCurrentUserInfo: function () {
            var self = this;
            require('web.ajax').jsonRpc("/my/user_info_client", 'call', {})
            .then(function (userInfo) {
                console.log('[dtsc] userInfo 返回内容:', userInfo);
                if (userInfo) {
                    self.partner_id = userInfo.id;
                    console.log('[dtsc] partner_id:', self.partner_id);
                    self.customer_class_id = userInfo.customclass_id;
                    console.log('[dtsc] customer_class_id:', self.customer_class_id);
                    self.custom_init_name = userInfo.custom_init_name;
                    console.log('[dtsc] custom_init_name:', self.custom_init_name);
                    self.nop = userInfo.nop;
                    console.log('[dtsc] nop:', self.nop);
                    // 新增逻辑：如果 customer_class_id 无效，则判定为内部用户
                    if (!userInfo.customclass_id || userInfo.customclass_id === 0 || userInfo.customclass_id === false || userInfo.customclass_id === null) {
                        self.isInternalUser = true;
                        console.log('[dtsc] 检测到 customer_class_id 无效，自动切换为内部用户模式');
                        self.isFixedCustomerMode = false;
                        // 内部用户一开始就显示客户关键字提示
                        $('.internal-user-search-tip').remove();
                        var tip = $('<h4 class="internal-user-search-tip"><b>請輸入客戶關鍵字並選擇客戶</b></h4>');
                        $('input[name="search"]').before(tip);
                        self.bindSearchInputEvent();
                        return;
                    }
                    // 其它情况按原逻辑判断
                    self.isInternalUser = !!userInfo.is_internal_user;
                    console.log('[dtsc] is_internal_user:', userInfo.is_internal_user);
                    console.log('[dtsc] 当前用户类型:', userInfo.is_internal_user ? '内部用户' : '客户(外部用户)');
                    if (userInfo.is_internal_user) {
                        self.isFixedCustomerMode = false;
                        console.log('[dtsc] 进入内部用户模式，执行bindSearchInputEvent');
                        // 内部用户一开始就显示客户关键字提示
                        $('.internal-user-search-tip').remove();
                        var tip = $('<h4 class="internal-user-search-tip"><b>請輸入客戶關鍵字並選擇客戶</b></h4>');
                        $('input[name="search"]').before(tip);
                        self.bindSearchInputEvent();
                    } else {
                        self.isFixedCustomerMode = true;
                        console.log('[dtsc] 进入客户模式，显示自身信息，不执行bindSearchInputEvent');
                        self.showCustomerDetails(userInfo);
                    }
                }
            })
            .catch(function (error) {
                console.error('Error fetching user info:', error);
            });
        },

        uploadFileInChunks: function($table) {
            return new Promise(async (resolve, reject) => {
                var uploadedFileName = "";
                var $fileInput = $table.find("input[type='file']");
                var fileName = $table.find('#project_product_name').val();
                var folder = this.custom_init_name;
                var file = $fileInput[0].files[0];

                if (file) {
                    // 生成新的文件名
                    var newFileName = this.generateCustomFileName($table, file);
                    debugLog('分片上传生成的自定义文件名:', newFileName);
                    var chunkSize = 100 * 1024 * 1024; // 分片大小，例如 100MB
                    var totalChunks = Math.ceil(file.size / chunkSize);

                    var file_extension = file.name.split('.').pop();
                    debugLog('file_extension:',file_extension)
                    for (var index = 0; index < totalChunks; index++) {
                        var start = index * chunkSize;
                        var end = Math.min(start + chunkSize, file.size);
                        var chunk = file.slice(start, end);

                        try {
                            let response = await this.uploadChunk(chunk, index, totalChunks, newFileName, folder, file_extension);
                            if (!response.success) {
                                throw new Error(response.message || 'Upload failed');
                            }
                        } catch (error) {
                            console.error('Chunk upload error:', error);
                            reject(error);
                            return;
                        }
                    }

                    resolve('All chunks uploaded successfully');
                } else {
                    resolve('No file to upload');
                }
            });
        },

        uploadChunk: function(chunk, chunkIndex, totalChunks, fileName, folder,file_extension) {
            return new Promise(async (resolve, reject) => {
                var formData = new FormData();
                formData.append('fileChunk', chunk);
                formData.append('chunkIndex', chunkIndex);
                formData.append('totalChunks', totalChunks);
                formData.append('filename', fileName);
                formData.append('folder', folder);
                formData.append('file_extension', file_extension);

                try {
                    let response = await $.ajax({
                        url: '/dtsc/upload_file_chunk', // 新的URL对应于新的后端函数
                        type: 'POST',
                        data: formData,
                        contentType: false,
                        processData: false,
                        dataType: 'json'
                    });
                    debugLog(`Chunk ${chunkIndex + 1}/${totalChunks} uploaded:`, response);
                    resolve(response);
                } catch (error) {
                    debugLog(`Error uploading chunk ${chunkIndex + 1}/${totalChunks}:`, error);
                    reject(error);
                }
            });
        },

        generateCustomFileName: function($table, file) {
            // 檔案名稱-材質-屬性1-屬性2...屬性n-寬x高x數量.擴展名
            var parts = [];
            
            // 1. 檔案名稱
            var fileName = $table.find('#project_product_name').val();
            if (fileName && fileName.trim()) {
                parts.push(fileName.trim());
            } else {
                parts.push('unnamed');
            }
            
            // 2. 材質 (產品模板名稱)
            var materialName = $table.find('.product_category_2 option:selected').text();
            if (materialName && materialName !== ' -- 請選擇產品模板 -- ' && !materialName.includes('請選擇')) {
                parts.push(materialName.trim());
            }
            
            // 3. 所有屬性值（按照select順序）
            $table.find('select.product_variant').each(function() {
                var selectedText = $(this).find('option:selected').text();
                if (selectedText && selectedText !== '無' && !selectedText.includes('請選擇') && selectedText.trim()) {
                    parts.push(selectedText.trim());
                }
            });
            
            // 4. 尺寸和數量
            var width = $table.find('#param1').val();
            var height = $table.find('#param2').val();
            var quantity = $table.find('#quantity').val();
            
            if (width && height && quantity) {
                parts.push(`${width}x${height}x${quantity}`);
            }
            
            // 5. 獲取原始文件擴展名
            var originalName = file.name;
            var extension = '';
            if (originalName && originalName.includes('.')) {
                extension = originalName.substring(originalName.lastIndexOf('.'));
            } else {
                extension = '.unknown';
            }
            
            // 組合文件名
            var customFileName = parts.join('-') + extension;
            
            // 清理文件名中的特殊字符，替換為下劃線
            customFileName = customFileName.replace(/[<>:"/\\|?*\s]/g, '_');
            
            // 避免文件名過長
            if (customFileName.length > 200) {
                var nameWithoutExt = customFileName.substring(0, customFileName.lastIndexOf('.'));
                nameWithoutExt = nameWithoutExt.substring(0, 200 - extension.length);
                customFileName = nameWithoutExt + extension;
            }
            
            debugLog('生成的文件名各部分:', parts);
            debugLog('最終文件名:', customFileName);
            
            return customFileName;
        },

        uploadFile: function($table) {
            /* return new Promise((resolve, reject) => {
                resolve('mock_uploaded_file.pdf'); // 模拟文件名
            }); */
            return new Promise(async (resolve, reject) => {
                var uploadedFileName = "";
                var $fileInput = $table.find("input[type='file']");
                var fileName = $table.find('#project_product_name').val();
                var folder = this.custom_init_name;
                var file = $fileInput[0].files[0];
				var fileName_original = file ? file.name : "";  // 使用文件的原始名称

                if (file) {
                    // 生成新的文件名：檔案名稱-材質-屬性1-屬性2...屬性n-寬x高x數量
                    var newFileName = this.generateCustomFileName($table, file);
                    debugLog('生成的自定义文件名:', newFileName);
                    // 新的文件名格式校验和栏位比对
                    // 文件名格式：案件摘要-檔名-寬x高cmx數量.xxx
                    // 允许x、×、*，cm可有可无
                    /* const newPattern = /^(.+)-(.+)-(\d+)[x×*](\d+)(cm)?[x×*](\d+)/i;
                    debugLog("fileName_original:", fileName_original);
                    var $uploadStatusDiv = $fileInput.siblings('.upload-status');
                    var match = fileName_original.replace(/\.[^/.]+$/, "").match(newPattern); // 去掉扩展名再匹配
                    if (!match) {
                        $uploadStatusDiv.text('文件名格式错误，需为"案件摘要-檔案名稱-寬x高cmx數量"，如：專案A-橫幅-100x200cmx3').css('color', 'red').removeClass('d-none');
                        reject('文件名格式不正确');
                        return;
                    }
                    // 获取栏位值
                    var projectName = $("input[name='project_name']").val().trim();
                    var fileNameField = $table.find('#project_product_name').val().trim();
                    var param1 = $table.find('#param1').val().trim();
                    var param2 = $table.find('#param2').val().trim();
                    var quantity = $table.find('#quantity').val().trim();
                    // 比对
                    var mismatchMessages = [];
					if (match[1] !== projectName) {
						mismatchMessages.push(`案件摘要不一致，表單值：「${projectName}」，檔案值：「${match[1]}」，請修改一致。`);
					}
					if (match[2] !== fileNameField) {
						mismatchMessages.push(`檔案名稱不一致，表單值：「${fileNameField}」，檔案值：「${match[2]}」，請修改一致。`);
					}
					if (match[3] !== param1) {
						mismatchMessages.push(`寬度不一致，表單值：「${param1}」，檔案值：「${match[3]}」，請修改一致。`);
					}
					if (match[4] !== param2) {
						mismatchMessages.push(`高度不一致，表單值：「${param2}」，檔案值：「${match[4]}」，請修改一致。`);
					}
					if (match[6] !== quantity) {
						mismatchMessages.push(`數量不一致，表單值：「${quantity}」，檔案值：「${match[6]}」，請修改一致。`);
					}
					if (mismatchMessages.length > 0) {
						$uploadStatusDiv.html(mismatchMessages.join('<br>')).css('color', 'red').removeClass('d-none');
						reject('文件名与表单栏位不一致');
						return;
					} */

                    var formData = new FormData();
                    formData.append('custom_file', file);
                    formData.append('filename', newFileName);
                    formData.append('fileName_original', fileName_original);
                    formData.append('folder', folder);

                    // 获取与当前文件输入控件相关联的进度条和上传状态显示<div>
                    var $progressBar = $fileInput.siblings('.uploadProgressBar');
                    var $uploadStatusDiv = $fileInput.siblings('.upload-status');
                    $uploadStatusDiv.addClass('d-none');

                    try {
                        let response = await $.ajax({
                            url: '/dtsc/upload_file',
                            type: 'POST',
                            data: formData,
                            contentType: false,
                            processData: false,
                            dataType: 'json',
                            xhr: function() {
                                var xhr = new window.XMLHttpRequest();
                                xhr.upload.addEventListener("progress", function(evt) {
                                    if (evt.lengthComputable) {
                                        var percentComplete = evt.loaded / evt.total;
                                        $progressBar.val(percentComplete * 100);
                                        $progressBar.show(); // 显示进度条
                                    }
                                }, false);
                                return xhr;
                            },
                            success: function(response) {
                                debugLog('Upload response:', response);
                                if (response.success) {
                                    // 显示文件尺寸信息
                                    var sizeInfo = response.image_info;
                                    var filenameSize = sizeInfo.filename_size;
                                    var actualSize = {
                                        width_mm: sizeInfo.width_mm,
                                        height_mm: sizeInfo.height_mm
                                    };
                                    
                                    var sizeMessage = `檔案上傳成功\n` +
                                        `檔案名稱尺寸: ${filenameSize.width_mm.toFixed(2)}×${filenameSize.height_mm.toFixed(2)}mm\n` +
                                        `實際尺寸: ${actualSize.width_mm.toFixed(2)}×${actualSize.height_mm.toFixed(2)}mm`;
                                    
                                    $uploadStatusDiv.html(sizeMessage.replace(/\n/g, '<br>')).css('color', 'green').removeClass('d-none');
                                    $progressBar.hide(); // 隐藏进度条
                                    resolve(response.filename); // 文件上传成功
                                } else {
                                    // 更新上传状态消息并显示
                                    var errorMessage = response.message || response.error || '上传失败';
                                    $uploadStatusDiv.html(errorMessage.replace(/\n/g, '<br>')).css('color', 'red').removeClass('d-none');
                                    $progressBar.hide(); // 隐藏进度条
                                    reject(errorMessage);
                                }
                            },
                            error: function(xhr, status, error) {
                                // 更新上传状态消息并显示
                                $uploadStatusDiv.text('Upload error: ' + error).css('color', 'red').removeClass('d-none');
                                reject(error);
                            }
                        });
                    } catch (error) {
                        // 更新上传状态消息并显示
                        $uploadStatusDiv.text('File upload error: ' + error).css('color', 'red').removeClass('d-none');
                        reject(error);
                    }
                } else {
                    resolve('No file to upload'); // 没有文件上传
                }
            });
        },

        prepareCheckoutData: async function() {
            var self = this; 
            var uploadPromises = [];
            var uploadErrors = false;
            var customer_class_id_p = this.customer_class_id
            let vals = {
                project_name: $("input[name='project_name']").val(),
                customer_id: this.partner_id,
                delivery_carrier : $("input[name='delivery_char']").val(),
                customer_class_id : customer_class_id_p,
				comment :  $("#delivery_comment").val(),
                product_ids: []
            };

            $(".banner_table").each(function() {
                var $table = $(this);
                var uploadPromise = self.uploadFile($table).then(uploadedFileName => {
                    return uploadedFileName;
                }).catch(error => {
                    console.error('Error uploading file:', error);
                    uploadErrors = true;
                    return "";
                });
                uploadPromises.push(uploadPromise);
                let pp = [];
				/* $table.find("input[name='multiple[]']:checked").each(function() {
					pp.push("'" + $(this).parent().text().trim() + "'");
				}); */
				$table.find("input[name='multiple[]']:checked").each(function() {
					// 获取选中项的文本内容
					let textContent = $(this).parent().text().trim();

					// 动态生成数量字段的 name
					let checkboxValue = $(this).val();
					let quantityInputName = `quantity_${checkboxValue}`;
					
					// 获取对应数量的值
					let qty = $table.find(`input[name='${quantityInputName}']`).val();
					qty = qty ? parseInt(qty, 10) : 0; // 默认值为 0

					// 拼接文本内容和数量，格式为 "名称 * 数量"
					pp.push(`${textContent}(${qty})`);
				});
				//var ppString = '[' + pp.join(', ') + ']';
				var ppString = pp.join('+ ');
				
				var charContent = "";
				var fileName = $table.find('#project_product_name').val();
				var productSelection = $table.find('.product_category option:selected').text() + "_" + 
									   $table.closest('table').find('.product_category_2 option:selected').text() + "_" + 
									   $table.closest('table').find('.product_variant option:selected').filter(function() {return $(this).text() !== "無";}).text();
				var width = $table.find('#param1').val();
				var height = $table.find('#param2').val();
				var productSize = `${width}x${height}`;
				var quantity = $table.find('#quantity').val();
                var comment = $table.find("[name='comment']").val();
                
                var product_details = productSelection+ "_" + ppString + "_" +comment;
                
				//charContent += `${productSelection}, ${productSize}, ${quantity}\n`;
				
				let attributeValues = [];
				$table.find("select.product_variant option:selected").each(function() {
					//attributeValues.push(parseInt($(this).val()));
                    if ($(this).text() !== "無") {
                        attributeValues.push(parseInt($(this).val()));
                    }
				});
                debugLog("attributeValues",attributeValues);
				
				vals.product_ids.push([0, 0, {
                    customer_class_id : customer_class_id_p,
					//product_name: $table.find("select.product_category_2 option:selected:not(:disabled)").text(),
					product_id: $table.find("select.product_category_2 option:selected:not(:disabled)").val(),
					product_width: width,
					product_height: height,
					//total_units : $table.find("#total_units").val(),
					quantity : quantity,
					//project_name : charContent,
					multi_chose_ids : ppString,
					project_product_name : fileName, 
					comment : comment,
					product_atts : attributeValues,
					//machine_id : 1,
					//output_mark : $table.find("[name='comment']").val(),
					quantity_peijian : $table.find("#accessory_qty").val(),
                    flag : 1,
                    product_details : product_details,
					aftermakepricelist_lines : [],
					//image_url : uploadedFileName,  
					//peijian_price : fields.Float("配件加價")
					//units_price : $table.find("#base_price").val(),
					//product_total_price : fields.Float("產品總價")
					//total_make_price : fields.Float("加工總價")
					//price = fields.Float("價錢") 
				}]);
				$table.find("input[name='multiple[]']:checked").each(function() {
					let aftermakepricelistId = $(this).closest('div').attr('id');
					if (aftermakepricelistId) {
						aftermakepricelistId = parseInt(aftermakepricelistId.replace('aftermakepricelist_', ''), 10);
					}

					let checkboxValue = $(this).val();
					let quantityInputName = `quantity_${checkboxValue}`;
					let qty = $table.find(`input[name='${quantityInputName}']`).val();
					qty = qty ? parseInt(qty, 10) : 0;

					if (aftermakepricelistId && qty > 0) {
						vals.product_ids[vals.product_ids.length - 1][2].aftermakepricelist_lines.push([0, 0, {
							customer_class_id: customer_class_id_p,
							aftermakepricelist_id: aftermakepricelistId,
							qty: qty,
						}]);
					} else {
						console.warn('Invalid aftermakepricelist_id or qty:', aftermakepricelistId, qty);
					}
				});
				/* vals.product_ids.aftermakepricelist_lines.push([0, 0, {
                    customer_class_id : customer_class_id_p,
					aftermakepricelist_id : ,
					qty:
				}]); */
            }); 
			/* 暂时停止 */
			/* console.log("vals",vals);
			return; */
            try {
                var uploadedFileNames = await Promise.all(uploadPromises);
                console.log('All files uploaded:', uploadedFileNames);

                if (!uploadErrors) {
                    uploadedFileNames.forEach((uploadedFileName, index) => {
                        if (uploadedFileName) {
                            vals.product_ids[index][2].image_url = uploadedFileName;   
                        }
                    });

                    debugLog("vals:",vals);
                    require('web.rpc').query({
                        model: 'dtsc.checkout',
                        method: 'create',
                        args: [vals],
                    }).then(function(new_id){
                        // 下单后预览记录更新逻辑（合并自 order.js）
                        if (self.isFixedCustomerMode && self.previewRecordId) {
                            require('web.rpc').query({
                                model: 'dtsc.order.preview',
                                method: 'write',
                                args: [[self.previewRecordId], { is_ordered: true }],
                            }).then(function() {
                                console.log('Preview record updated successfully');
                            }).catch(function(error) {
                                console.error('Error updating preview record:', error);
                            });
                        }
                        debugLog("New record ID:", new_id);
                        alert("感謝您的訂購！！");
                        if (self.isFixedCustomerMode) {
                            window.location.href = window.location.origin + '/order/list';
                        } else {
                            location.reload();  // 刷新页面
                        }
                    })
                    .catch(function(error){
                        console.error("Error:", error);
                        throw error; // 向上传递错误
                    });
                } else {
                    console.error("One or more files failed to upload.");
                    alert("上傳失敗，請重試");
                    // 处理上传错误
                }
            } catch (error) {
                console.error('An error occurred during file upload:', error);
                // 处理错误
            }
        },



		
		bindParamInputEvents: function() { 
			var self = this;
			   $(document).on('input', '.size_class', function() {
				var $table = $(this).closest('table');
            
				// 检查table中的param1和param2输入框是否都有值
				var param1Value = $table.find('input[id="param1"]').val();
				var param2Value = $table.find('input[id="param2"]').val();

				if (param1Value && param2Value) {
					// 如果两个输入框都有值，则更改当前table中id为total_units的input的值
					//$table.find('input[id="total_units"]').val("111");
					var param1 = Number(param1Value);
					var param2 = Number(param2Value);
					
					var result = eval(self.conversion_formula.replace('param1', param1).replace('param2', param2));

					switch (self.rounding_method) {
						case 'round':
							result = Math.round(result);
							break;
						case 'up':
							result = Math.ceil(result);
							break;
						case 'down':
							result = Math.floor(result);
							break;
						default:
							break; 
					}
					$table.find('input[id="total_units"]').val(result);
					if (!$table.find('input[id="quantity"]').val()) {
						$table.find('input[id="quantity"]').val(1);
					}
				}
			});
		},
		createBannerTable:function(selectedCustomer,categories){
			if (!categories || !Array.isArray(categories) || categories.length === 0) {
				alert('未找到可用产品分类，请联系管理员！');
				return;
			}
			var existingTablesCount = $('table#banner_table').length;
			var nextTableNumber = existingTablesCount + 1;
			var bannerTable = $('<table>').addClass('table customer-detail banner_table').attr('id', 'banner_table').css('width', '100%');

			var headerRow = $('<tr>').addClass('table-active').append(
				 $('<th>').attr('colspan', '6').css({'padding-top': '10px', 'padding-bottom': '10px','text-align':'unset'}).append(  
					$('<span>').addClass('product_item_no').text(nextTableNumber + '. 產品選擇')
				),
				$('<td>').append(
					$('<div>').addClass('text-right').append(
						$('<a>').addClass('btn btn-danger btn-sm delete_button d-none').attr('style', 'color: white;').append(
							$('<i>').addClass('fa fa-close')
						).on('click', function() {
							$(this).closest('table#banner_table').remove();
							var tables = $('table#banner_table');
							tables.each(function(index, table) {
								var number = index + 1;
								$(table).find('.product_item_no').text(number + '. 產品選擇');
							});
							if (tables.length <= 1) {
								$('table#banner_table').find('.delete_button').addClass('d-none');
							}
						})
					)
				)
			);

			// 新增表头tr（寬度、高度、每件(才數)、數量(件)、隐藏价格列）
			var paramHeaderRow = $('<tr>').addClass('table-active product_attribute_class tr_product_attribute_class').css({'padding-top': '7px', 'padding-bottom': '7px'});
			paramHeaderRow.append($('<th>').text('寬度(公分)').css('width', '16.66%'));
			paramHeaderRow.append($('<th>').text('高度(公分)').css('width', '16.66%'));
			paramHeaderRow.append($('<th>').text('每件(才數)').css('width', '16.66%'));
			paramHeaderRow.append($('<th>').text('數量(件)').css('width', '25%'));
			paramHeaderRow.append($('<th class="accessory-header-th" style="width:25%;">配件數量</th>'));
			/* paramHeaderRow.append($('<th>').addClass('d-none').text('產品價格(元)'));
			paramHeaderRow.append($('<th>').addClass('d-none').text('加工費(元)'));
			paramHeaderRow.append($('<th>').addClass('d-none').text('估價(元)'));
 */
			// 新增输入行（input/校验div），与表头一一对应
			var paramInputRow = $('<tr>').addClass('product_attribute_class input_row_class tr_product_attribute_class');
			// 寬度
			var newTd1 = $('<td>').css('width', '16.66%');
			var newInput1 = $('<input>').attr({type: 'text', class: 'form-control formula_calculation val_required size_class', id: 'param1', name: 'param1', placeholder: '寬度'}).css('width', '100%').on('input', function(e) {
				this.value = this.value.replace(/[^0-9.]/g, '').replace(/(\..*?)\..*/g, '$1');
			});
			var newDiv1 = $('<div>').addClass('invalid-feedback').text('必填');
			newTd1.append(newInput1).append(newDiv1);
			// 高度
			var newTd2 = $('<td>').css('width', '16.66%');
			var newInput2 = $('<input>').attr({type: 'text', class: 'form-control formula_calculation val_required size_class', id: 'param2', name: 'param2', placeholder: '高度'}).css('width', '100%').on('input', function(e) {
				this.value = this.value.replace(/[^0-9.]/g, '').replace(/(\..*?)\..*/g, '$1');
			});
			var newDiv2 = $('<div>').addClass('invalid-feedback').text('必填');
			newTd2.append(newInput2).append(newDiv2);
			// 每件(才數)
			var newTd3 = $('<td>').css('width', '16.66%').attr({'data-name': 'total_units'});
			var newInput3 = $('<input>').attr({type: 'text', readonly: '1', id: 'total_units', name: 'total_units', class: 'form-control formula_calculation val_required size_class', placeholder: '自動計算'}).css('width', '100%').on('input', function(e) {
				this.value = this.value.replace(/[^0-9]/g, '');
			});
			newTd3.append(newInput3);
			// 數量(件)
			var newTd4 = $('<td>').css('width', '25%').attr({'data-name': 'quantity'});
			var newInput4 = $('<input>').attr({type: 'text', class: 'form-control formula_calculation val_required quantity_class', id: 'quantity', name: 'quantity', placeholder: '數量'}).css('width', '100%').on('input', function(e) {
				this.value = this.value.replace(/[^0-9]/g, '');
			});
			var newDiv4 = $('<div>').addClass('invalid-feedback').text('請輸入數量');
			newTd4.append(newInput4).append(newDiv4);
			// 配件數量（动态显示/隐藏）
			var newTd5 = $('<td class="accessory-input-td" style="width:25%;" data-name="accessory_qty"></td>');
			var accessoryInput = $('<input>').attr({type: 'text', class: 'form-control formula_calculation quantity_class', id: 'accessory_qty', name: 'accessory_qty', disabled: true}).css('width', '100%');
			var accessoryDiv = $('<div>').addClass('invalid-feedback').text('請輸入配件數量');
			newTd5.append(accessoryInput).append(accessoryDiv);
			// 其余隐藏列
			/* var newTd6 = $('<td>').attr({'data-name': 'base_price', class: 'd-none'});
			var newInput6 = $('<input>').attr({type: 'text', readonly: '1', id: 'base_price', name: 'base_price', class: 'form-control-plaintext'});
			newTd6.append(newInput6);
			var newTd7 = $('<td>').attr({'data-name': 'product_cost', class: 'd-none'});
			var newInput7 = $('<input>').attr({type: 'text', readonly: '1', id: 'product_cost', name: 'product_cost', class: 'form-control-plaintext'});
			newTd7.append(newInput7);
			var newTd8 = $('<td>').attr({'data-name': 'processing_cost', class: 'd-none'});
			var newInput8 = $('<input>').attr({type: 'text', readonly: '1', id: 'processing_cost', name: 'processing_cost', class: 'form-control-plaintext'});
			newTd8.append(newInput8);
			var newTd9 = $('<td>').attr({'data-name': 'total_price', class: 'd-none'});
			var newInput9 = $('<input>').attr({type: 'text', readonly: '1', id: 'price', name: 'price', class: 'form-control-plaintext'});
			newTd9.append(newInput9); */
			// 组装输入行
			//paramInputRow.append(newTd1).append(newTd2).append(newTd3).append(newTd4).append(newTd5).append(newTd6).append(newTd7).append(newTd8).append(newTd9);
			paramInputRow.append(newTd1).append(newTd2).append(newTd3).append(newTd4).append(newTd5);

			var fileNameRow = $('<tr>').append(
				$('<td>').attr('colspan', '6').css('width', '100%').append(
					$('<div>').addClass('form-group').append(
						$('<input>').addClass('form-control').attr({type: 'text', name: 'project_product_name', id: 'project_product_name', placeholder: '檔案名稱'})
					)
				),
				$('<td>')
			);

            // 备注输入行，插入到檔案名稱下方
            var commentRow = $('<tr>').addClass('product_attribute_class tr_product_attribute_class');
            var commentTd = $('<td>').attr('colspan', '6');
            var commentDiv = $('<div>').addClass('form-group');
            var commentInput = $('<input>').attr({type: 'text', class: 'form-control', name: 'comment', placeholder: '備註'});
            commentDiv.append(commentInput);
            var hiddenCommentLabel = $('<label>').addClass('sr-only').attr('for', 'comment').text('備註');
            commentDiv.prepend(hiddenCommentLabel);
            commentTd.append(commentDiv);
            commentRow.append(commentTd);

			var uploadRow = $('<tr>').append(
				$('<td>').attr('colspan', '10').attr('style', 'text-align:left;').append(
					$('<div>').addClass('custom-file mb-3').css('margin-left', '0').append(
						$('<input>').attr({type: 'file', id: 'custom_file', name: 'custom_file', class: 'custom-file-input'}),
						$('<label>').addClass('custom-file-label').attr('for', 'custom_file')
							.html('限制500M，超過請聯繫管理員<br>'),
						$('<br>'),
						$('<label>').css({'font-size': '12px', 'color': '#888'}).html('自動匹配的文件名格式:檔案名稱-材質-屬性1-屬性2...屬性n-寬x高【可帶單位cm|mm】x數量 EX:檔案1-PVC-全透PVC-亮膜-彩白-110x110x1.ai'),
						$('<div>').addClass('invalid-feedback').text('請選擇需要上傳的檔案'),
						$('<input>').attr({type: 'text', class: 'custom_file_status d-none', name: 'custom_file_status', value: ''}),
						$('<div>').addClass('upload-status d-none').css({'color': 'green', 'font-weight': 'bold'}),
						$('<progress>').attr({class: 'uploadProgressBar', value: '0', max: '100'}).css({'width': '100%', 'display': 'none'})
					)
				)
			);

			var productSelectRow = $('<tr>').append(
				$('<td colspan="3">').css('width', '50%').append(
					$('<div>').addClass('form-group').append(
						$('<select>').addClass('form-control product_category')
							.append(
								$('<option>').attr({disabled: '1', selected: '1'}).text(' -- 請選擇產品類型 -- '),
								...categories.map(category => 
									$('<option>').val(category.id).text(category.name)
								)
							)
					)
				),
				$('<td>').addClass('d-none').attr('id', 'product_template')
			);

			// 原顺序：bannerTable.append(headerRow, paramHeaderRow, paramInputRow, uploadRow, fileNameRow, productSelectRow);
			// 新顺序如下：
			bannerTable.append(headerRow, uploadRow, fileNameRow, commentRow, paramHeaderRow, paramInputRow, productSelectRow);
			$('#add_product_table').parent().before(bannerTable);
			this.fetchSaleProductCategories(selectedCustomer.customclass_id[0]);
		},

        /* fetchUnitConversion: function() {
            rpc.query({
                model: 'dtsc.unit_conversion',
                method: 'search_read',
                args: [[]],
                kwargs: {
                    fields: ['name','rounding_method', 'conversion_formula'],
                },
            }).then(function(units) {
                var $selection = $('#unit-selection');
                $selection.empty();
                $.each(units, function(i, unit) {
                    $selection.append($('<option>').val(unit.id).text(unit.name).data('formula', unit.conversion_formula).data('rounding', unit.rounding_method));
                });

                // 添加事件监听
                $selection.change(calculateResult);
                $('#param1').change(calculateResult);
                $('#param2').change(calculateResult);
            });
        }, */
		fetchUnitConversion: function() {
			rpc.query({
				model: 'dtsc.unit_conversion',
				method: 'search_read',
				args: [[], ['name', 'rounding_method', 'conversion_formula'], 0, 1],  // 第三个参数为offset，第四个参数为limit
			}).then((units) => {  // 注意这里，我们使用箭头函数来确保this指向CheckoutWidget的实例
				if (units && units.length > 0) {
					this.rounding_method = units[0].rounding_method;
					this.conversion_formula = units[0].conversion_formula;
					debugLog("rounding_method", this.rounding_method);
					debugLog("conversion_formula", this.conversion_formula);
				} else {
					console.log('No records found.');
				}
			});
		},

        bindSearchInputEvent: function() {
            $('input[name="search"]').on('input', this.onSearchInput.bind(this));
        },
		generateTableContent: function() {
            // 预览弹框内容
            var self = this;
			var customerClassId = self.customer_class_id;
            var totalPriceAll = 0;
            var tableContent = `
                <table class="table table-striped table-borderless table-responsive-lg">
                    <thead>
                        <tr>
                            <th scope="col">項</th>
                            <th scope="col">產品名稱</th>
                            <th scope="col">製作尺寸</th>
                            <th scope="col">數量</th>
                            ${self.nop === false ? '<th scope="col">預估價錢</th>' : ''}
                        </tr>
                    </thead>
                    <tbody>
            `;

            var allRowsPromises = [];
            var rowContents = [];
			
            $('#banner_table tr.input_row_class').each(function(index, row) {
				var multipleIds = [];
                var fileName = $(row).closest('table').find('#project_product_name').val();
                let pp = [];
                $(row).closest('table').find("input[name='multiple[]']:checked").each(function() {
                    pp.push("'" + $(this).parent().text().trim() + "'");
					let multipleValue = $(this).val();
					multipleIds.push(multipleValue);
                });
				multipleIds = multipleIds.map(id => parseInt(id, 10));
				console.log("Collected multipleIds:", multipleIds);
                var ppString = pp.join(', ');
                var productSelection = $(row).closest('table').find('.product_category option:selected').text() + "_" +
                                       $(row).closest('table').find('.product_category_2 option:selected').text() + "_" +
                                       $(row).closest('table').find('.product_variant option:selected').filter(function() {return $(this).text() !== "無";}).text() + "_" +
                                       ppString + "_" +
                                       $(row).closest('table').find("input[type='text'].form-control[name='comment']").val();
                var width = $(row).find('#param1').val();
                var height = $(row).find('#param2').val();
                var productSize = `${width}x${height}`;
                var quantity = $(row).find('#quantity').val();
                var total_units = $(row).find('#total_units').val();
                var accessory_qty = $(row).find('#accessory_qty').val();
                var quotationId = $(row).closest('table').find('#quotation_id').val();
                var basePrice = $(row).closest('table').find('#base_price').val();
                debugLog("cai:", total_units);
                debugLog("Base Price:", basePrice);
                debugLog("Quotation ID:", quotationId);

                var totalPrice = 0;
                var isDoubleBiao = 0;
                var lengbiaoPrice = 0;
                var jiagongPrice = 0;
				var peijianPrice = 0;
				var houjiagongPrice1 = 0;
				var houjiagongPrice2 = 0;
                // 创建一个数组来保存每个 `product_variant` 的异步操作
                var rpcPromises = [];

                debugLog("NOP:", self.nop);
                debugLog("customer_class_id:", customerClassId);
                if (self.nop === false) {
                    debugLog("NOP is false");
                    // 遍历所有 product_variant select 控件
                    $(row).closest('table').find('.product_variant').each(function() {
                        var selectedValue = $(this).val();
                        var selectedText = $(this).find('option:selected').text();
                        var selectName = $(this).attr('name'); // 获取 select 的 name 作为组名

                        if (selectedText !== "無") {
                            rpcPromises.push(
                                rpcQuery('dtsc.quotationproductattributeprice', 'search_read', [
                                    ['quotation_id', '=', parseInt(quotationId)],
                                    ['attribute_value_id', '=', parseInt(selectedValue)]
                                ], ['price_cai', 'price_jian']).then(attributePrice => {
                                    let priceCai = attributePrice.length > 0 ? attributePrice[0].price_cai : 0;
                                    let priceJian = attributePrice.length > 0 ? attributePrice[0].price_jian : 0;

                                    debugLog("屬性:", selectName);
                                    debugLog("Price Cai:", priceCai);
                                    debugLog("Price Jian:", priceJian);

                                    // 额外查询 attribute_value_id 以获取 price_extra
                                    return rpcQuery('product.attribute.value', 'search_read', [
                                        ['id', '=', parseInt(selectedValue)]
                                    ], ['price_extra']).then(attributeValue => {
                                        if (attributeValue && attributeValue.length > 0) {
                                            let priceExtra = attributeValue[0].price_extra || 0;
                                            debugLog("Price Extra:", priceExtra);
                                            if (selectName == "是否需雙面貼板") {
                                                isDoubleBiao = 1;
                                            } else if (selectName == "冷裱") {
                                                lengbiaoPrice = total_units * (priceCai + priceExtra);
                                                jiagongPrice += total_units * (priceCai + priceExtra);
                                            } else if (selectName == "配件") {
                                                peijianPrice = accessory_qty * (priceJian + priceExtra);
                                            } else {
                                                jiagongPrice += total_units * (priceCai + priceExtra);
                                            }
                                        } else {
                                            console.warn(`${selectName} - No attribute value found for selected value: ${selectedValue}`);
                                        }
                                    }).catch(error => {
                                        console.error(`${selectName} - Error fetching attribute value:`, error);
                                    });
                                }).catch(error => {
                                    console.error(`${selectName} - Error fetching attribute price:`, error);
                                })
                            );
                        }
                    });
					if (multipleIds.length > 0) {
						rpcPromises.push(
							rpcQuery('dtsc.maketype', 'search_read', [['id', 'in', multipleIds]], ['price']).then(results => {
								console.log("RPC results for multipleIds:", results); // 打印查询结果
								
								results.forEach(result => {
									let price = result.price || 0;
									console.log(`Adding price1: ${price} for ID: ${result.id}`); // 打印每个价格和对应的 ID
									let quantityInputName = `quantity_${result.id}`; // 动态生成数量字段的 name
									console.log("quantityInputName----:", quantityInputName); 
									let quantityValue = $(row).closest('table').find(`input[name='${quantityInputName}']`).val() || 1; // 默认值为 1
									quantityValue = parseInt(quantityValue, 10); // 转换为整数

									console.log(`Row ID: ${result.id}, Price: ${price}, Quantity: ${quantityValue}`); // 打印每个价格、ID 和数量
									
									houjiagongPrice1 += price * quantityValue;
								});

								console.log("Updated houjiagongPrice1:", houjiagongPrice1); // 打印累加后的 houjiagongPrice
							}).catch(error => {
								console.error('Error fetching prices for multiple[] values:', error); // 打印错误信息
							})
						);
						console.log("Sending RPC with multipleIds:", multipleIds);
						console.log("Sending RPC with customerClassId:", customerClassId);
						rpcPromises.push(
							rpcQuery('dtsc.aftermakepricelist', 'search_read',[['name', 'in', multipleIds], ['customer_class_id', '=', customerClassId]], ['price','name']).then(results => {
								console.log("RPC results for multipleIds:", results); // 打印查询结果
								
								results.forEach(result => {
									let price = result.price || 0;
									console.log(`Adding price2: ${price} for ID: ${result.name}`); // 打印每个价格和对应的 ID

									let quantityInputName = `quantity_${result.name[0]}`; // 动态生成数量字段的 name
									console.log("quantityInputName===:", quantityInputName); 
									let quantityInput = $(row).closest('table').find(`input[name='${quantityInputName}']`);
									let quantityValue = quantityInput.val() || 1; // 默认值为 1
									quantityValue = parseInt(quantityValue, 10); // 转换为整数

									// 为 input 上层的 div 添加 id
									let parentDiv = quantityInput.closest('div'); // 找到上一层的 div
									if (parentDiv.length > 0) {
										parentDiv.attr('id', `aftermakepricelist_${result.id}`); // 设置 aftermakepricelist_id
										console.log(`Set parent div id: result_id_${result.id}`); // 打印已设置的 id
									}

									houjiagongPrice2 += price * quantityValue;
								});


								console.log("Updated houjiagongPrice2:", houjiagongPrice2); // 打印累加后的 houjiagongPrice
							}).catch(error => {
								console.error('Error fetching prices for multiple[] values:', error); // 打印错误信息
							})
						);
					}

                }

                allRowsPromises.push(
                    Promise.all(rpcPromises).then(() => {
                        if (self.nop === false) {
                            // 异步操作完成后计算总价
                            // if (isDoubleBiao)
                                // totalPrice = quantity * (jiagongPrice + basePrice * total_units * 2 + lengbiaoPrice) + peijianPrice;
                            // else
                            totalPrice = quantity * (jiagongPrice + basePrice * total_units) + peijianPrice + houjiagongPrice1 + houjiagongPrice2;

                            debugLog(totalPrice)
                        }
                        totalPriceAll += totalPrice;
                        // 更新表格内容
                        rowContents[index] = `
                            <tr>
                                <th scope="row">${index + 1}</th>
                                <td>檔名：${fileName}<br>${productSelection}</td>
                                <td>${productSize}</td>
                                <td>${quantity}</td>
                                ${self.nop === false ? `<td>${totalPrice}</td>` : ''}
                            </tr>
                        `;
                    }).catch(error => {
                        console.error('Error during RPC calls:', error);
                    })
                );
            });

            // 预览记录插入逻辑（合并自 order.js）
            if (self.isFixedCustomerMode) {
                require('web.rpc').query({
                    model: 'dtsc.order.preview',
                    method: 'create',
                    args: [{
                        customer_id: self.partner_id,
                        is_ordered: false
                    }],
                }).then(function(recordId) {
                    self.previewRecordId = recordId;
                    console.log('Preview record created with ID:', recordId);
                }).catch(function(error) {
                    console.error('Error creating preview record:', error);
                });
            }

            return Promise.all(allRowsPromises).then(() => {
                rowContents.forEach(rowContent => {
                    tableContent += rowContent;
                });
                if (self.nop === false) {
                    tableContent += `
                        <tr>
                            <td colspan="3"></td>
                            <td>預計總價(未稅)：</td>
                            <td>${totalPriceAll}</td>
                        </tr>
                    `;
                }
                tableContent += `
                    </tbody>
                </table>
                `;
                $('#ModelOrderLine .modal-body.summary_modal_content').html(tableContent);  // 将表格内容插入到模态框的 modal-body
                $('#ModelOrderLine').modal('show');
                //return tableContent;
            });
        },

		
		fetchSaleProductCategories: async function() {
			debugLog("选择的客户类别ID:", this.customer_class_id);
			if (!this.customer_class_id || this.customer_class_id === false || this.customer_class_id === 0) {
				alert('客户资料不完整，无法获取产品分类，请联系管理员！');
				return [];
			}
			const quotations = await rpcQuery('dtsc.quotation', 'search_read', [['customer_class_id', '=', this.customer_class_id]], ['product_id']);
			if (!quotations) return;
			const productIds = quotations.map(quote => quote.product_id?.[0]).filter(Boolean);
			const uniqueProductIds = [...new Set(productIds)];
			debugLog("产品ID:", productIds);
			debugLog("唯一产品ID:", uniqueProductIds);
			const products = await rpcQuery('product.template', 'search_read', [['id', 'in', uniqueProductIds]], ['categ_id']);
			debugLog('Products:', products);
			if (!products) return;
			const categoryIds = products.map(product => product.categ_id?.[0]).filter(Boolean);
			const uniqueCategoryIds = [...new Set(categoryIds)];
			debugLog("分类ID:", categoryIds);
			debugLog("唯一分类ID:", uniqueCategoryIds);
			const categories = await rpcQuery('product.category', 'search_read', [['id', 'in', uniqueCategoryIds]], ['name']);
			if (!categories) return;
			return categories;
		},


		
		showCustomerDetails: function(selectedCustomer) { 
            if (!selectedCustomer || selectedCustomer.error) {
                alert('客户信息无效，请重新选择客户！');
                return;
            }
            if (!this.customer_class_id || this.customer_class_id === false || this.customer_class_id === 0) {
                alert('客户资料不完整，无法下单，请联系管理员！');
                return;
            }
            debugLog('selectedCustomer',selectedCustomer);
            debugLog('partner_id',this.partner_id);
            debugLog('customer_class_id',this.customer_class_id);
            debugLog('custom_init_name',this.custom_init_name);
            debugLog('nop',this.nop);
            var self= this;
            $('.customer-detail').remove(); 
            debugLog('isInternalUser',self.isInternalUser);
            /* if (self.isInternalUser) {
                var tip = $('<h4 class="internal-user-search-tip"><b>請輸入客戶關鍵字並選擇客戶</b></h4>');
                $('input[name="search"]').before(tip);
            } */
            $('input[name="search"]').val(`${selectedCustomer.name}   ${selectedCustomer.mobile || ''}   ${selectedCustomer.phone || ''}`);
            // 在搜索框下方显示标签
            var nameLabel = $('<span class="detail-label">').text('姓名');
            var phoneLabel = $('<span class="detail-label">').text('電話');
            var mobileLabel = $('<span class="detail-label">').text('手機');
            var emailLabel = $('<span class="detail-label">').text('Email');
            var addressLabel = $('<span class="detail-label">').text('地址');
            
            var labelRow = $('<div class="detail-row customer-detail">').append(nameLabel, phoneLabel, mobileLabel, emailLabel);
            

            // 在搜索框下方显示输入框
            var nameInput = $('<input type="text" class="form-control form-control-plaintext" readonly="1">').val(selectedCustomer.name).addClass('detail-input');
            var phoneInput = $('<input type="text" class="form-control form-control-plaintext" readonly="1">').val(selectedCustomer.phone || '').addClass('detail-input');
            var mobileInput = $('<input type="text" class="form-control form-control-plaintext" readonly="1">').val(selectedCustomer.mobile || '').addClass('detail-input');
            var emailInput = $('<input type="text" class="form-control form-control-plaintext" readonly="1">').val(selectedCustomer.email || '').addClass('detail-input');
            var addressInput = $('<input type="text" class="form-control form-control-plaintext" readonly="1">').val(selectedCustomer.street || '').addClass('detail-input-full');
            
            var valueRow = $('<div class="detail-row customer-detail">').append(nameInput, phoneInput, mobileInput, emailInput);
            
            
            var labelRow_2 = $('<div class="detail-row customer-detail">').append(addressLabel);
            
            var valueRow_2 = $('<div class="detail-row customer-detail">').append(addressInput);
             
            $('input[name="search"]').after(labelRow, valueRow, labelRow_2, valueRow_2);
            
            ////////////////////
            var horizontalLine = $('<hr>').addClass('customer-detail');  // 新增的横线
            var projectTitle = $('<h4>').addClass('customer-detail').html('<b>請輸入案件摘要</b>');

            var projectInput = $('<div class="mb-3 customer-detail">').append(
                $('<input>').attr('name', 'project_name').attr('type', 'text').addClass('form-control')
            );

            var deliveryRow = $('<div class="form-row customer-detail mt-3">').append(  // mt-3增加上边距
                $('<div class="form-group col-md-12">').append(
                    $('<label>').attr('for', 'delivery_char').text('交貨方式'),
                    $('<input>').addClass('form-control val_required').attr({type: 'text', name: 'delivery_char', id: 'delivery_char', placeholder: '請輸入交貨方式:自取、快遞、貨運、施工，若無填寫一律為自取...等'}),
                    $('<div>').addClass('invalid-feedback').text('必填')
                )
            );

            var commentRow = $('<div class="form-row customer-detail mt-3 mb-3">').append(  // mt-3增加上边距
                $('<div class="form-group col-md-12">').append(
                    $('<label>').attr('for', 'delivery_comment').text('訂單備註'),
                    $('<input>').addClass('form-control').attr({type: 'text', name: 'delivery_comment', id: 'delivery_comment', placeholder: '請輸入收件聯絡人姓名+電話+地址或訂單備註...等'})
                )
            );
            
            ////////////////////////
            var projectTitle2 = $('<h4>').addClass('customer-detail mb-3').html('<b>產品清單</b>');
            $('input[name="search"]').after(labelRow, valueRow, labelRow_2, valueRow_2, horizontalLine, projectTitle, projectInput, deliveryRow, commentRow, projectTitle2);
            
            this.fetchSaleProductCategories().then(categories => {
                debugLog("categories", categories);
                
                var addButtonDiv = $('<div>').addClass('text-left customer-detail').append(
                    $('<button>').attr({id: 'add_product_table', type: 'button'}).addClass('btn btn-success').append(
                        $('<i>').addClass('fa fa-plus')
                    )
                );

                $('.customer-detail:last').after(addButtonDiv); 
                $('#add_product_table').off('click');
                $('#add_product_table').on('click', () => {
                    self.createBannerTable(selectedCustomer, categories);
                    $('a.d-none').removeClass('d-none');
                });
                
                self.createBannerTable(selectedCustomer, categories);
                
                /////////////////////////
                var horizontalSeparator = $('<hr>').addClass('customer-detail mb-4');
                //var placeholderParagraph = $('<p></p>'); 

                var warningModal = $('<div class="modal fade modal_shown" id="exampleModal" tabindex="-1" role="dialog" style="display: none;" aria-hidden="true">').append(
                    $('<div class="modal-dialog" role="document">').addClass('customer-detail').append(
                        $('<div class="modal-content">').append(
                            $('<div class="modal-header">').append(
                                $('<h5 class="modal-title" id="exampleModalLabel">').text('警告訊息'),
                                $('<button type="button" class="close" data-dismiss="modal" aria-label="Close">').append(
                                    $('<span>').text('X')
                                )
                            ),
                            $('<div class="modal-body">').append(
                                $('<p>').text('請填寫必填欄位:'),
                                $('<ul id="missingFieldsList">')
                            ),
                            $('<div class="modal-footer">').append(
                                $('<button type="button" class="btn btn-danger" data-dismiss="modal">').text('Close')
                            )
                        )
                    )
                );
                //预览前				
                $(document).off('click', '.btn.btn-primary.btn-lg.model_order_line').on('click', '.btn.btn-primary.btn-lg.model_order_line', function() {
                    var missingFields = []; // 用于存储缺失字段的数组

                    $('input.val_required').each(function() {
                        var $input = $(this);
                        var value = $input.val().trim();
                        
                        // 检查输入的值是否为空
                        if (!value) {
                            var labelText = $('label[for="'+ $input.attr('id') +'"]').text();
                            missingFields.push(labelText);
                            $input.next('.invalid-feedback').css('display', 'block');
                        } else {
                            $input.next('.invalid-feedback').css('display', 'none');
                        }
                    });

                     $('select').each(function() { 
                        var $select = $(this);
                        
                        if ($select.find('option:selected').attr('disabled')) {
                            var firstOptionText = $select.find('option').first().text();
                            missingFields.push(firstOptionText);
                        }
                    });

                    if (missingFields.length) {
                        var $list = $('#missingFieldsList');
                        $list.empty(); // 清空列表

                        // 为每个缺失的字段添加一个列表项
                        missingFields.forEach(function(field) {
                            $list.append('<li>' + field + '</li>');
                        });

                        if (!$('#exampleModal').length) {  // 如果模态框不存在则将其添加到body
                            $('body').append(warningModal);
                        }

                        $('#exampleModal').modal('show');
                    }
                    else
                    {
                        self.generateTableContent();
                        
                    }
                });

                $(document).off('click', '.modal-content .close').on('click', '.modal-content .close', function() {
                    $('#exampleModal').modal('hide');
                });
                $(document).off('click', '.modal-footer .btn-danger').on('click', '.modal-footer .btn-danger', function() {
                    $('#exampleModal').modal('hide');
                });

                var previewButtonDiv = $('<div class="text-center">').addClass('customer-detail').append(
                    $('<button class="btn btn-primary btn-lg model_order_line" type="button">').text('預覽明細')
                );

                $('#content').append(horizontalSeparator, warningModal, previewButtonDiv);
            });
            
            ///////////////////////////////预览后
            var modelOrderLineModal = `
                <div class="modal fade customer-detail" id="ModelOrderLine" tabindex="-1" role="dialog">
                    <div class="modal-dialog modal-dialog-centered modal-lg" role="document">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">訂單明細</h5>
                            </div>
                            <div class="modal-body summary_modal_content">
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-dismiss="modal">關閉預覽</button>
                                <button type="submit" class="btn btn-primary btn_checkout">確認訂購</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            $('#content').append(modelOrderLineModal);
            // 关闭模态框的按钮事件
            $(document).off('click', '#ModelOrderLine .btn-secondary').on('click', '#ModelOrderLine .btn-secondary', function() {
                $('#ModelOrderLine').modal('hide');
            });

            // 确认订购按钮事件
            $(document).off('click', '#ModelOrderLine .btn_checkout').on('click', '#ModelOrderLine .btn_checkout', function() {
                
                
                if (self.isSubmitting) {
                    return; // 如果正在提交中，直接返回
                }
                // 檢查是否有文件正在上傳
                var uploading = false;
                $('.banner_table').each(function() {
                    var $progressBar = $(this).find('.uploadProgressBar');
                    if ($progressBar.length > 0) {
                        $progressBar.each(function() {
                            var val = Number($(this).val());
                            if (val < 100) {
                                uploading = true;
                            }
                        });
                    }
                });
                if (uploading) {
                    alert('正在上傳文件，請耐心等待');
                }
                // 禁用按钮并改变文字
                var $submitBtn = $(this);
                $submitBtn.prop('disabled', true).text('訂單提交中...');
                
                // 设置提交状态
                self.isSubmitting = true;
                
                // 这里可以添加您的确认订购逻辑
                $('#ModelOrderLine').modal('hide');
                self.prepareCheckoutData().then(() => {
                    // 提交完成后重置状态
                    self.isSubmitting = false;
                    $submitBtn.prop('disabled', false).text('確認訂購');
                }).catch(error => {
                    // 发生错误时也要重置状态
                    console.error('訂單提交失敗:', error);
                    self.isSubmitting = false;
                    $submitBtn.prop('disabled', false).text('確認訂購');
                    alert('訂單提交失敗，請稍後重試');
                });
            });
            

            ////////
            $('.customer-list').remove(); 

        },

        
        onSearchInput: function() {
            var self = this;
            var keyword = $('input[name="search"]').val();
            if (keyword.length >= 1) {
                rpc.query({
                    model: 'res.partner',
                    method: 'search_read',
                    domain: [
                        '|', '|', 
                        ['name', 'ilike', keyword], 
                        ['mobile', 'ilike', keyword], 
                        ['phone', 'ilike', keyword],
                        ['customer_rank', '>', 0], // 添加的条件为客户
                        ['coin_can_cust', '=', true ]
                    ],
                    fields: ['id','name', 'mobile', 'phone', 'email', 'street','customclass_id','custom_init_name','nop'], 
                    limit: 10,
                }).then(function(customers) {
                    var customerList = $('<ul class="customer-list">');
                    $.each(customers, function(i, customer) {                        
                        var displayText = `${customer.name}   ${customer.mobile || ''}   ${customer.phone || ''}`; 
                        var listItem = $('<li>').text(displayText).data('customer', customer).off('click');
                        listItem.click(function() {
                            var selectedCustomer = $(this).data('customer');
                            if (!selectedCustomer || selectedCustomer.error) {
                                alert('无法获取客户信息，请重新登录或联系管理员！');
                                return;
                            }
                            self.partner_id = selectedCustomer.id;
                            self.customer_class_id = selectedCustomer.customclass_id[0];
                            self.custom_init_name = selectedCustomer.custom_init_name;
                            $('.customer-detail').remove(); 
                            self.showCustomerDetails(selectedCustomer); 
                            self.nop = selectedCustomer.nop;
                            debugLog("customer===",selectedCustomer);
                        });
                        customerList.append(listItem);
                    });
                    $('.customer-list').remove();
                    $('input[name="search"]').after(customerList);
                });
            }
        },
    });
	
	
    // 计算结果的函数
    /* function calculateResult() {
        var formula = $('#unit-selection option:selected').data('formula');
        var roundingMethod = $('#unit-selection option:selected').data('rounding');
        var param1 = Number($('#param1').val());
        var param2 = Number($('#param2').val());

        if (!formula || isNaN(param1) || isNaN(param2)) {
            return;
        }

        var result = eval(formula.replace('param1', param1).replace('param2', param2));

        switch (roundingMethod) {
            case 'round':
                result = Math.round(result);
                break;
            case 'up':
                result = Math.ceil(result);
                break;
            case 'down':
                result = Math.floor(result);
                break;
            default:
                break;
        }

        $('#result').text(result);
    } */

    $(document).ready(function() {
        // 页面加载时强制清空搜索框，防止刷新后残留
        $('input[name="search"]').val('');
        // 辅助函数定义，必须在最外层
        function waitAndSelectProductTemplate($table, productId, callback, retry = 0) {
            var $select = $table.find('.product_category_2');
            if ($select.length && $select.find('option[value="' + productId + '"]').length) {
                $select.val(productId).trigger('change');
                if (callback) callback();
            } else if (retry < 20) {
                setTimeout(function() {
                    waitAndSelectProductTemplate($table, productId, callback, retry + 1);
                }, 100);
            }
        }
        function waitAndSelectProductVariant($table, attrName, valueId, retry = 0) {
            var $select = $table.find('select.product_variant[name="' + attrName + '"]');
            if ($select.length && $select.find('option[value="' + valueId + '"]').length) {
                $select.val(valueId).trigger('change');
                // 已移除属性全选相关逻辑
            } else if (retry < 20) {
                setTimeout(function() {
                    waitAndSelectProductVariant($table, attrName, valueId, retry + 1);
                }, 100);
            }
        }
        if ($(".banner_service_form_public_web_order").length > 0) {
            var checkoutWidget = new CheckoutWidget();
            checkoutWidget.appendTo($(".banner_service_form_public_web_order"));
        }
        // 修正版：监听每个表格的文件选择，自动解析文件名并填充栏位
        $(document).on('change', '.custom-file-input', async function() {
            var $fileInput = $(this);
            // 健壮性判断，防止未选文件时报错
            if (!this.files || !this.files[0]) return;
            var fileName = this.files[0].name ? this.files[0].name.replace(/\.[^/.]+$/, "") : '';
            if (!fileName) return;
            console.log('文件已选择', fileName);
            var $table = $fileInput.closest('table');
            // 清空同一表格下的相关栏位
            $table.find('.product_category').each(function() {
                // 选中第一个disabled的option作为默认
                $(this).val($(this).find('option:disabled').first().val()).trigger('change');
            });
            $table.find('.product_category_2').val('').trigger('change');
            $table.find('select.product_variant').val('').trigger('change');
            $table.find('#param1').val('');
            $table.find('#param2').val('');
            $table.find('#total_units').val('');
            $table.find('#quantity').val('');
            $table.find('#project_product_name').val('');
           
            // 文件名格式：支持宽高任意一项带单位，如110x25cmx15、110cmx25x15、110cmx25cmx15、110x25x15
            var parts = fileName.split('-');
            if (parts.length < 4) return;
            var projectProductName = parts[0];
            var productTemplateName = parts[1];
            var attributes = parts.slice(2, parts.length - 1); // 属性数组
            // 修正 sizePart，去除空格和扩展名
            var sizePart = parts[parts.length - 1].replace(/\s*\.[^/.]+$/, '').replace(/\s+$/, '');
            debugLog('sizePart:', sizePart);
            // 解析尺寸、数量，支持宽高分别带单位，单位推断逻辑优化
            var sizeMatch = sizePart.match(/([0-9.]+)\s*(cm|mm)?[x×*]([0-9.]+)\s*(cm|mm)?[x×*]([0-9]+)/i);
            debugLog('sizeMatch:', sizeMatch);
            var quantityMatch = sizePart.match(/(\d+)張/i);
            debugLog('quantityMatch:', quantityMatch);
            var width = '', height = '', quantity = '';
            if (sizeMatch) {
                width = parseFloat(sizeMatch[1]);
                var widthUnit = sizeMatch[2] ? sizeMatch[2].toLowerCase() : null;
                height = parseFloat(sizeMatch[3]);
                var heightUnit = sizeMatch[4] ? sizeMatch[4].toLowerCase() : null;
                quantity = sizeMatch[5];
                // 单位推断逻辑
                let finalUnit = 'cm';
                if (widthUnit && !heightUnit) finalUnit = widthUnit;
                else if (!widthUnit && heightUnit) finalUnit = heightUnit;
                else if (widthUnit && heightUnit) finalUnit = widthUnit; // 若都写且不同，优先宽的
                // 统一转换
                if (finalUnit === 'mm') {
                    width = width / 10;
                    height = height / 10;
                }
                width = parseFloat(width.toFixed(1));
                height = parseFloat(height.toFixed(1));
                console.log('解析到 width:', width, 'height:', height, 'quantity:', quantity, '单位:', finalUnit);
            } else if (quantityMatch) {
                // 兼容"4130x75x1張"格式
                var sizeParts = sizePart.split(/[x×*]/i);
                if (sizeParts.length >= 3) {
                    width = sizeParts[0];
                    height = sizeParts[1];
                    quantity = sizeParts[2].replace(/[^\d]/g, '');
                    console.log('兼容模式解析到 width:', width, 'height:', height, 'quantity:', quantity);
                }
            }
            // 1. 檔案名稱
            $table.find('#project_product_name').val(projectProductName);
            // 2. 先在所有模板中模糊查找产品模板，反查出产品类型
            const all_products = await rpcQuery('product.template', 'search_read', [], ['id', 'name', 'categ_id']);
            // 优先全字匹配，其次前缀匹配，最后包含匹配，忽略空格和大小写
            let normName = (s) => (s || '').replace(/\s+/g, '').toLowerCase();
            let normTarget = normName(productTemplateName);
            let matchedProduct = all_products.find(p => normName(p.name) === normTarget);
            if (!matchedProduct) {
                matchedProduct = all_products.find(p => normName(p.name).startsWith(normTarget));
            }
            if (!matchedProduct) {
                matchedProduct = all_products.find(p => normName(p.name).indexOf(normTarget) !== -1);
            }
            if (matchedProduct) {
                let categoryId = matchedProduct.categ_id[0];
                // 自动选中产品类型
                $table.find('.product_category').val(categoryId).trigger('change');
                // 等待产品模板下拉框渲染并选中
                waitAndSelectProductTemplate($table, matchedProduct.id, function() {
                    setTimeout(async function() {
                        // 查询该模板的属性
                        const attributeLines = await rpcQuery('product.template.attribute.line', 'search_read', [['product_tmpl_id', '=', matchedProduct.id]], ['attribute_id','sequence']);
                        attributeLines.sort((a, b) => a.sequence - b.sequence);
                        
                        debugLog('文件名中的属性:', attributes);
                        debugLog('数据库中的属性行:', attributeLines.map(line => line.attribute_id[1]));
                        
                        // 为每个属性找到最佳匹配
                        for (let k = 0; k < attributeLines.length; k++) {
                            let attrName = attributeLines[k].attribute_id[1];
                            const attributeValues = await rpcQuery('product.template.attribute.value', 'search_read', [
                                ['attribute_id', '=', attributeLines[k].attribute_id[0]],
                                ['product_tmpl_id', '=', matchedProduct.id]
                            ], ['product_attribute_value_id', 'name']);
                            
                            debugLog(`属性 "${attrName}" 的所有值:`, attributeValues.map(v => v.name));
                            
                            let matchedValue = null;
                            let matchedAttribute = null;
                            
                            // 遍历文件名中的所有属性，找到最佳匹配
                            for (let attrIdx = 0; attrIdx < attributes.length; attrIdx++) {
                                for (let v = 0; v < attributeValues.length; v++) {
                                    let valueName = attributeValues[v].name;
                                    try {
                                        const nameObj = JSON.parse(valueName);
                                        valueName = nameObj['zh_TW'] || valueName;
                                    } catch (e) {}
                                    
                                    if (valueName.indexOf(attributes[attrIdx]) !== -1) {
                                        matchedValue = attributeValues[v].product_attribute_value_id[0];
                                        matchedAttribute = attributes[attrIdx];
                                        debugLog(`找到匹配: 属性 "${attrName}" 的值 "${valueName}" 匹配文件名中的 "${matchedAttribute}"`);
                                        break;
                                    }
                                }
                                if (matchedValue) break;
                            }
                            
                            if (matchedValue) {
                                // 自动填充属性时，确保触发change事件
                                waitAndSelectProductVariant($table, attrName, matchedValue);
                            } else {
                                debugLog(`属性 "${attrName}" 未找到匹配的值`);
                            }
                        }
                        // 填充尺寸和数量
                        if (width) $table.find('#param1').val(width);
                        if (height) $table.find('#param2').val(height);
                        if (quantity) $table.find('#quantity').val(quantity);
                        // 自动计算每件(才數)
                        if (width && height) {
                            $table.find('#param1').trigger('input');
                        }
                        debugLog('自动填充完成:', {projectProductName, productTemplateName, attributes, width, height, quantity});
                    }, 2000);
                });
            } else {
                debugLog('未能根据文件名自动匹配产品模板，请手动选择');
            }
        }); 
        // 原有文件大小校验
        $(document).on('change', '.custom-file-input', function() {
            if (!this.files || !this.files[0]) return;
            var fileSize = this.files[0].size / 1024 / 1024; // 转换为MB
            if (fileSize > 500) {
                alert('文件超過500M限制，請選擇其它文件或者聯繫管理員上傳。');
                this.value = ''; // 重置文件输入
            } else {
                // ...
            }
        });
        // 新增：点击文件输入控件时清空 upload-status
        $(document).on('click', '.custom-file-input', function() {
            var $fileInput = $(this);
            var $table = $fileInput.closest('table');
            $table.find('.upload-status').html('').addClass('d-none').css({color: '', 'font-weight': ''});
        });
    });

    return CheckoutWidget;
});
