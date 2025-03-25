odoo.define('dtsc.order', function (require) {
    "use strict";
	var debugMode = true;
	//var debugMode = false;
	//var session = require('web.session'); 
    var Widget = require('web.Widget');
    var rpc = require('web.rpc');
	
	var ajax = require('web.ajax');
	
	
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
			this.previewRecordId = null;
		},
        start: function () {
			this.conversion_formula="";
			this.rounding_method="";
            this._super.apply(this, arguments);
            this.fetchUnitConversion();
            /* this.bindSearchInputEvent(); */
			this.bindParamInputEvents(); 
			//this.prepareCheckoutData();
			this.fillCurrentUserInfo();
        },
        fillCurrentUserInfo: function () {
            var self = this;
            ajax.jsonRpc("/my/user_info_client", 'call', {})
            .then(function (userInfo) {
                if (userInfo) {
                    self.partner_id = userInfo.id; // 用户id
                    self.customer_class_id = userInfo.customclass_id; // 假设用户也有 customclass_id 字段
                    self.custom_init_name = userInfo.custom_init_name; // 假设用户也有 customclass_id 字段
                    self.nop = userInfo.nop; // 假设用户也有 customclass_id 字段
                    debugLog('userInfo',userInfo)
                    debugLog('partner_id',self.partner_id);
                    debugLog('customer_class_id',self.customer_class_id);
                    debugLog('custom_init_name',self.custom_init_name);
                    debugLog('nop',self.nop);
                    // 直接调用显示用户详细信息的方法
                    self.showCustomerDetails(userInfo);
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
                    var chunkSize = 100 * 1024 * 1024; // 分片大小，例如 100MB
                    var totalChunks = Math.ceil(file.size / chunkSize);

                    var file_extension = file.name.split('.').pop();
                    debugLog('file_extension:',file_extension)
                    for (var index = 0; index < totalChunks; index++) {
                        var start = index * chunkSize;
                        var end = Math.min(start + chunkSize, file.size);
                        var chunk = file.slice(start, end);

                        try {
                            let response = await this.uploadChunk(chunk, index, totalChunks, fileName, folder, file_extension);
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

        uploadFile: function($table) {
            return new Promise(async (resolve, reject) => {
                var uploadedFileName = "";
                var $fileInput = $table.find("input[type='file']");
                var fileName = $table.find('#project_product_name').val();
                var folder = this.custom_init_name;
                var file = $fileInput[0].files[0];

                if (file) {
                    var formData = new FormData();
                    formData.append('custom_file', file);
                    formData.append('filename', fileName);
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
                                console.log(response.message);
                                if (response.success) {
                                    // 更新上传状态消息并显示
                                    $uploadStatusDiv.text('File uploaded successfully').css('color', 'green').removeClass('d-none');
                                    $progressBar.hide(); // 隐藏进度条
                                    resolve(response.filename); // 文件上传成功
                                } else {
                                    // 更新上传状态消息并显示
                                    $uploadStatusDiv.text('Upload failed').css('color', 'red').removeClass('d-none');
                                    reject(response.error);
                                }
                            },
                            error: function(xhr, status, error) {
                                // 更新上传状态消息并显示
                                $uploadStatusDiv.text('Upload error').css('color', 'red').removeClass('d-none');
                                reject(error);
                            }
                        });
                    } catch (error) {
                        // 更新上传状态消息并显示
                        $uploadStatusDiv.text('File upload error').css('color', 'red').removeClass('d-none');
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
                    rpc.query({
                        model: 'dtsc.checkout',
                        method: 'create',
                        args: [vals],
                    }).then(function(new_id){
                        // 更新预览记录的状态
                        if (self.previewRecordId) {
                            rpc.query({
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
                        location.reload();  // 刷新页面
                    })
                    .catch(function(error){
                        console.error("Error:", error);
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
					$table.find('input[id="quantity"]').val(1);
				}
			});
		},
		createBannerTable:function(selectedCustomer,categories){
			
			var existingTablesCount = $('table#banner_table').length;
			var nextTableNumber = existingTablesCount + 1;
			
			var bannerTable = $('<table>').addClass('table customer-detail banner_table').attr('id', 'banner_table');

			var headerRow = $('<tr>').addClass('table-active').append(
				 $('<th>').attr('colspan', '5').css({'padding-top': '10px', 'padding-bottom': '10px','text-align':'unset'}).append(  
					$('<span>').addClass('product_item_no').text(nextTableNumber + '. 產品選擇')
				),
				$('<td>').append(
					$('<div>').addClass('text-right').append(
						$('<a>').addClass('btn btn-danger btn-sm delete_button d-none').attr('style', 'color: white;').append(
							$('<i>').addClass('fa fa-close')
						).on('click', function() {
							// 删除所在的整个table
							$(this).closest('table#banner_table').remove();

							// 重设所有table中的產品選擇前的数字
							var tables = $('table#banner_table');
							tables.each(function(index, table) {
								var number = index + 1;
								$(table).find('.product_item_no').text(number + '. 產品選擇');
							});

							// 如果只有一个表格，隐藏删除按钮
							if (tables.length <= 1) {
								$('table#banner_table').find('.delete_button').addClass('d-none');
							}
						})
					)
				)
			);
			
			var fileNameRow = $('<tr>').append(
				$('<td>').attr('colspan', '6').css('width', '100%').append(
					$('<div>').addClass('form-group').append(
						$('<input>').addClass('form-control').attr({type: 'text', name: 'project_product_name', id: 'project_product_name', placeholder: '檔案名稱'})
					)
				),
				$('<td>') // 这个是占位的td，可以考虑移除或留着
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
			
			bannerTable.append(headerRow, fileNameRow, productSelectRow);

			$('#add_product_table').parent().before(bannerTable);
			this.initProductCategoryChangeListener(selectedCustomer.customclass_id); 
			this.fetchSaleProductCategories(selectedCustomer.customclass_id);
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

        /* bindSearchInputEvent: function() {
            $('input[name="search"]').on('input', this.onSearchInput.bind(this));
        }, */
		checkAllSelected: function() {
			var allSelected = true;
			$(".product_variant").each(function() {
				if ($(this).val() === null || $(this).val() === "") {
					allSelected = false;
					return false; // 跳出循环
				}
			});
			return allSelected;
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

            // 在generateTableContent函数中，添加逻辑以在点击"预览"按钮时插入一条记录
            // 将日期时间格式转换为Odoo期望的格式
            /* var currentDateTime = new Date();
            var formattedDateTime = currentDateTime.getFullYear() + '-' +
                                    ('0' + (currentDateTime.getMonth() + 1)).slice(-2) + '-' +
                                    ('0' + currentDateTime.getDate()).slice(-2) + ' ' +
                                    ('0' + currentDateTime.getHours()).slice(-2) + ':' +
                                    ('0' + currentDateTime.getMinutes()).slice(-2) + ':' +
                                    ('0' + currentDateTime.getSeconds()).slice(-2);
 */
            rpc.query({
                model: 'dtsc.order.preview',
                method: 'create',
                args: [{
                    customer_id: self.partner_id,
                    // preview_time: formattedDateTime, // 移除此行，使用Odoo的create_date字段
                    is_ordered: false
                }],
            }).then(function(recordId) {
                self.previewRecordId = recordId;
                console.log('Preview record created with ID:', recordId);
            }).catch(function(error) {
                console.error('Error creating preview record:', error);
            });

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

		
		initProductVariantChangeListener: function(selectedProductId) {//產品變體選擇事件
			const outerSelf = this;
            debugLog("initProductVariantChangeListener->selectedProductId", selectedProductId);
			$(document).off('change', '.product_variant');
			$(document).on('change', '.product_variant', async function() {
				$(this).closest('table').find('.tr_product_attribute_class').closest('tr').remove();
				/* $(".tr_product_attribute_class").closest("tr").remove(); */
				if(outerSelf.checkAllSelected())
				{
                    
                    var accessory = false; 
                    let acc_value = $("select[name='配件'] option:selected").text();
                    debugLog("accessory:", acc_value);
                    if (acc_value && acc_value !== '不加配件') { 
                        accessory = true;
                    }
					var newTr1 = $('<tr>').addClass('table-active product_attribute_class tr_product_attribute_class').css({'padding-top': '7px', 'padding-bottom': '7px'});
					newTr1.append($('<th>').text('寬度(公分)'));
					newTr1.append($('<th>').text('高度(公分)'));
					newTr1.append($('<th>').text('每件(才數)'));
					newTr1.append($('<th>').text('數量(件)'));
                    if(accessory)
					{
                        newTr1.append($('<th>').text('配件數量'));
                    }
					else
					{
						newTr1.append($('<th>').text(''));
					}
					
					newTr1.append($('<th>').addClass('d-none').text('產品價格(元)'));
					newTr1.append($('<th>').addClass('d-none').text('加工費(元)'));
					newTr1.append($('<th>').addClass('d-none').text('估價(元)'));
					newTr1.append($('<th>').text('上傳檔案'));
					// ...更多的 <th> 或 <td>
					 $(this).closest('table').append(newTr1);
					
					// 创建第二个 <tr> 元素并添加到表格中
					var newTr2 = $('<tr>').addClass('product_attribute_class input_row_class tr_product_attribute_class');

					// 第一个 <td>
					var newTd1 = $('<td>');
					var newInput1 = $('<input>').attr({type: 'text', class: 'form-control formula_calculation val_required size_class', id: 'param1', name: 'param1'}).on('input', function(e) {
                        this.value = this.value.replace(/[^0-9.]/g, '').replace(/(\..*?)\..*/g, '$1');
                    });
					var newDiv1 = $('<div>').addClass('invalid-feedback').text('必填');
					newTd1.append(newInput1).append(newDiv1);

					// 第二个 <td>
					var newTd2 = $('<td>');
					var newInput2 = $('<input>').attr({type: 'text', class: 'form-control formula_calculation val_required size_class', id: 'param2', name: 'param2'}).on('input', function(e) {
                        this.value = this.value.replace(/[^0-9.]/g, '').replace(/(\..*?)\..*/g, '$1');
                    });
					var newDiv2 = $('<div>').addClass('invalid-feedback').text('必填');
					newTd2.append(newInput2).append(newDiv2);

					// 第三个 <td>
					var newTd3 = $('<td>').attr({'data-name': 'total_units'});
					var newInput3 = $('<input>').attr({type: 'text', readonly: '1', id: 'total_units', name: 'total_units', class: 'form-control formula_calculation val_required size_class'}).on('input', function(e) {
                        this.value = this.value.replace(/[^0-9]/g, '');
                    });
					newTd3.append(newInput3);

					// 第四个 <td>
                    var newTd4 = "";
                    if(accessory)
                    {
                        newTd4 = $('<td>').attr({'data-name': 'accessory_qty'});
                        var newInput4 = $('<input>').attr({type: 'text', class: 'form-control formula_calculation val_required quantity_class', id: 'accessory_qty', name: 'accessory_qty', value: '0'}).on('input', function(e) {
                        this.value = this.value.replace(/[^0-9]/g, '');
                        });
                        var newDiv4 = $('<div>').addClass('invalid-feedback').css('display', 'none').text('請輸入數量');
                        newTd4.append(newInput4).append(newDiv4);
                    }
					else
					{
						newTd4 = $('<td>').attr({'data-name': 'accessory_qty'});
					}

					// 第五个 <td>
					var newTd5 = $('<td>').attr({'data-name': 'quantity'});
					var newInput5 = $('<input>').attr({type: 'text', class: 'form-control formula_calculation val_required quantity_class', id: 'quantity', name: 'quantity', placeholder: ''}).on('input', function(e) {
                        this.value = this.value.replace(/[^0-9]/g, '');
                        });
					var newDiv5 = $('<div>').addClass('invalid-feedback').text('請輸入數量');
					newTd5.append(newInput5).append(newDiv5);

					// 第六个 <td>
                    var newTd6 = $('<td>').attr({'data-name': 'base_price', class: 'd-none'});
					var newInput6 = $('<input>').attr({type: 'text', readonly: '1', id: 'base_price', name: 'base_price', class: 'form-control-plaintext'});
					newTd6.append(newInput6);

					// 第七个 <td>
					var newTd7 = $('<td>').attr({'data-name': 'product_cost', class: 'd-none'});
					var newInput7 = $('<input>').attr({type: 'text', readonly: '1', id: 'product_cost', name: 'product_cost', class: 'form-control-plaintext'});
					newTd7.append(newInput7);

					// 第八个 <td>
					var newTd8 = $('<td>').attr({'data-name': 'processing_cost', class: 'd-none'});
					var newInput8 = $('<input>').attr({type: 'text', readonly: '1', id: 'processing_cost', name: 'processing_cost', class: 'form-control-plaintext'});
					newTd8.append(newInput8);

					// 第九个 <td>
					var newTd9 = $('<td>').attr({'data-name': 'total_price', class: 'd-none'});
					var newInput9 = $('<input>').attr({type: 'text', readonly: '1', id: 'price', name: 'price', class: 'form-control-plaintext'});
					newTd9.append(newInput9);

					// 第十个 <td>
					var newTd10 = $('<td>').attr({'data-name': 'file'});
					var newDiv10 = $('<div>').addClass('custom-file mb-3');
					var newInput10 = $('<input>').attr({type: 'file', id: 'custom_file', name: 'custom_file', class: 'custom-file-input'});
					var newLabel10 = $('<label>')
					.addClass('custom-file-label')
					.attr('for', 'custom_file')
					.html('&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;限制500M，超過請聯繫管理員');
					var newDiv10_2 = $('<div>').addClass('invalid-feedback').text('請選擇需要上傳的檔案');
					var newInput10_2 = $('<input>').attr({type: 'text', class: 'custom_file_status d-none', name: 'custom_file_status', value: ''});
					newDiv10.append(newInput10).append(newLabel10).append(newDiv10_2).append(newInput10_2);
					newTd10.append(newDiv10); 
                    
                    //进度条
                    var uploadStatusDiv = $('<div>').addClass('upload-status d-none').css({'color': 'green', 'font-weight': 'bold'});
                    var progressBar = $('<progress>').attr({class: 'uploadProgressBar', value: '0', max: '100'}).css({'width': '100%', 'display': 'none'});
                    newDiv10.append(newInput10).append(newLabel10).append(newDiv10_2).append(uploadStatusDiv).append(progressBar);

                    newTd10.append(newDiv10);

					// 将所有的 <td> 元素添加到 <tr> 中
					newTr2.append(newTd1).append(newTd2).append(newTd3).append(newTd5).append(newTd4).append(newTd6).append(newTd7).append(newTd8).append(newTd9).append(newTd10);
					//newTr2.append(newTd1).append(newTd2).append(newTd3).append(newTd4).append(newTd5).append(newTd6).append(newTd7).append(newTd8).append(newTd9);
					
					 $(this).closest('table').append(newTr2);
					///
					debugLog("Selected Product ID:", selectedProductId);
					if (selectedProductId) {
						try {
							const productMakeTypeRelResults = await rpcQuery(
								'product.maketype.rel', 
								'search_read', 
								[['product_id', '=', parseInt(selectedProductId)]], 
								['make_type_id', 'sequence'], 
								{ order: 'sequence ASC, id ASC' } // 添加排序条件
							);
							debugLog("productMakeTypeRelResults:", productMakeTypeRelResults);
							if (!productMakeTypeRelResults) {
								console.error("无法获取 product_maketype_rel 数据"); 
							}
							if (productMakeTypeRelResults && productMakeTypeRelResults.length > 0) {
								productMakeTypeRelResults.sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
								// 添加标题行
								var headerTr = $('<tr>').addClass('table-active product_attribute_class tr_product_attribute_class');
								var headerTh = $('<th>').css('text-align','unset').attr('colspan', '6').text('後加工方式, 此區塊估價將由業務人員與您討論後提供');
								headerTr.append(headerTh);
								 $(this).closest('table').append(headerTr);
								let currentRow;
								for (let i = 0; i < productMakeTypeRelResults.length; i++) {
									const postProcess = productMakeTypeRelResults[i];
									debugLog("後加工",postProcess.make_type_id[1]);
									
									if (i % 3 === 0) {
										currentRow = $('<tr>').addClass('product_attribute_checkboxs tr_product_attribute_class');
										$(this).closest('table').append(currentRow);
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
						}catch (error) {
							console.error("An error occurred:", error);
						}
					}
					var newCommentRow = $('<tr>').addClass('product_attribute_class tr_product_attribute_class');
					var newCommentTd = $('<td>').attr('colspan', '6');
					var newCommentDiv = $('<div>').addClass('form-group');
					var newCommentInput = $('<input>').attr({type: 'text', class: 'form-control', name: 'comment', placeholder: '備註'});
					newCommentDiv.append(newCommentInput);
					///
					// 为 param1 创建隐藏的标签
					var hiddenLabel1 = $('<label>').addClass('sr-only').attr('for', 'param1').text('寬度(公分)');
					newTd1.prepend(hiddenLabel1);

					// 为 param2 创建隐藏的标签
					var hiddenLabel2 = $('<label>').addClass('sr-only').attr('for', 'param2').text('高度(公分)');
					newTd2.prepend(hiddenLabel2);

					// 为 accessory_qty 创建隐藏的标签
                    if(accessory)
                    {
                        var hiddenLabel4 = $('<label>').addClass('sr-only').attr('for', 'accessory_qty').text('配件數量');
                        newTd4.prepend(hiddenLabel4);
                    }
					else
					{
						var hiddenLabel4 = $('<label>').addClass('sr-only').attr('for', 'accessory_qty').text('');
                        newTd4.prepend(hiddenLabel4);
					}
					

					// 为 quantity 创建隐藏的标签
					var hiddenLabel5 = $('<label>').addClass('sr-only').attr('for', 'quantity').text('數量(件)');
					newTd5.prepend(hiddenLabel5);

					// 为 comment 创建隐藏的标签
					var hiddenCommentLabel = $('<label>').addClass('sr-only').attr('for', 'comment').text('備註');
					newCommentDiv.prepend(hiddenCommentLabel);
					///
					newCommentTd.append(newCommentDiv);
					newCommentRow.append(newCommentTd);
					
					// 将新行添加到表格
					 $(this).closest('table').append(newCommentRow); 
				}
			});
		},
		
		initProductCategory2ChangeListener: function(selectedCustomerClassId) {
            const outerSelf = this;
            $(document).off('change', '.product_category_2');
            $(document).on('change', '.product_category_2', async function() {
                $(this).closest('table').find('.product_variant').closest('td').remove();
                $(this).closest('table').find('.tr_product_attribute_class').closest('tr').remove();

                var selectedProductId = $(this).val();
                debugLog("Selected Product ID:", selectedProductId);

                // 清除当前行中已有的变体下拉框
                $(this).closest('tr').find('td').has('.product_variant').remove();
                $(this).closest('tr').find('input[type="hidden"]').remove();

                if (selectedProductId) {
                    try {
                        // 查询 dtsc.quotation 中 base_price 和 id 栏位
                        const quotations = await rpcQuery('dtsc.quotation', 'search_read', [
                            ['customer_class_id', '=', selectedCustomerClassId],
                            ['product_id', '=', parseInt(selectedProductId)]
                        ], ['id', 'base_price']);

                        let basePrice = quotations.length > 0 ? quotations[0].base_price : null;
                        let quotationId = quotations.length > 0 ? quotations[0].id : null;
                        

                        // 新增两个隐藏的控件来记录 base_price 和 id
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

						let tdCount = 2; // 每行 td 计数
						let currentTr = $(this).closest('tr'); // 当前的 tr

                        for (let line of attributeLines) {
							var attributeId = line.attribute_id[0];
							debugLog("attributeId:", attributeId);

							// 获取过滤后的属性值
							const attributeValues = await rpcQuery('product.template.attribute.value', 'search_read', [
								['attribute_id', '=', attributeId],
								['product_tmpl_id', '=', parseInt(selectedProductId)]
							], ['product_attribute_value_id', 'name']);

							let filteredValues = [];
							for (let value of attributeValues) {
								let attributeValueDetail = await rpcQuery('product.attribute.value', 'search_read', [
									['id', '=', value.product_attribute_value_id[0]]
								], ['sequence', 'is_visible_on_order'], { order: 'sequence ASC, id ASC' });

								// 解析 JSON 并提取 zh_TW
								let nameZhTW;
								try {
									const nameObj = JSON.parse(value.name);
									nameZhTW = nameObj['zh_TW'] || value.name; // 如果有 zh_TW 则使用，没有则保留原值
								} catch (error) {
									// 如果解析失败，直接使用原始值
									nameZhTW = value.name;
								}

								// 仅保留 is_visible_on_order 为 true 的值
								if (attributeValueDetail.length > 0 && attributeValueDetail[0].is_visible_on_order) {
									filteredValues.push({
										id: value.product_attribute_value_id[0],
										name: nameZhTW,
										sequence: attributeValueDetail[0].sequence || 0 // 默认为 0 防止未定义
									});
								}
							}

							// 按照 sequence 升序排序
							filteredValues.sort((a, b) => a.sequence - b.sequence);

							debugLog("Filtered and sorted by sequence attributeValues:", filteredValues);

							// 新增 variant 下拉框
							var variantSelect = $('<select>').addClass('form-control product_variant');
							variantSelect.attr('name', line.attribute_id[1]);

							var newTd = $('<td colspan="3">').css('width', '50%').append(
								$('<div>').addClass('form-group').append(variantSelect)
							);

							// 默认选项
							var defaultOptionText = ` -- 請選擇${line.attribute_id[1]}屬性 -- `;
							variantSelect.append($('<option>').attr({ disabled: '1', selected: '1' }).text(defaultOptionText));

							// 添加选项到下拉框
							$.each(filteredValues, function (j, value) {
								variantSelect.append($('<option>').val(value.id).text(value.name)); // 使用解析后的 zh_TW 值
							});

							// 如果当前行的 td 已经达到 3，换行并添加新的 tr
							if (tdCount >= 2) {
								currentTr = $('<tr>'); // 创建新 tr
								$(this).closest('table').append(currentTr); // 添加到表格
								tdCount = 0; // 重置计数
							}

							currentTr.append(newTd); // 在当前行添加 td
							tdCount++; // 计数 +1

							outerSelf.initProductVariantChangeListener(selectedProductId);
						}

                    } catch (error) {
                        console.error("An error occurred:", error);
                    }
                }
            });
        },


		
		initProductCategoryChangeListener: function(selectedCustomerClassId) {//產品類別選擇事件
			const self = this;
			$(document).off('change', '.product_category');
			$(document).on('change', '.product_category', async function() {
				$(this).closest('table').find('.product_category_2').closest('td').remove();
				$(this).closest('table').find('.product_variant').closest('td').remove();
				$(this).closest('table').find('.tr_product_attribute_class').closest('tr').remove();
				/* $(".product_category_2").closest("td").remove();
				$(".product_variant").closest("td").remove();
				$(".tr_product_attribute_class").closest("tr").remove(); */
				var selectedCategId = $(this).val();
				// ...（其他代码保持不变）
				debugLog("initProductCategoryChangeListener=>:selectedCategId:", selectedCategId);
				$(this).closest('tr').find('td').has('.product_category_2').remove();
				if (selectedCategId) {
					// 创建新的下拉框
					var productCategory2 = $('<select>').addClass('form-control product_category_2');
		
					// 创建新的td元素来容纳新的下拉框
					var newTd = $('<td colspan="3">').css('width', '50%').append(
						$('<div>').addClass('form-group').append(productCategory2)
					);
		
					// 将新的td元素添加到产品选择的同一行
					$(this).closest('tr').append(newTd);
		
					// 清空现有的 product_category_2 下拉列表
					productCategory2.empty();
					productCategory2.append($('<option>').attr({disabled: '1', selected: '1'}).text(' -- 請選擇產品模板 -- '));
					try {
						// 第一步：从 dtsc_quotation 获取所有相关的 product_id
						const dtsc_products = await rpcQuery('dtsc.quotation', 'search_read', [['customer_class_id', '=', selectedCustomerClassId]], ['product_id']);
                        console.table(dtsc_products);
						var productIds = dtsc_products.map(item => item.product_id[0]);  // 假设 product_id 是一个 (id, name) 元组
                        
						// 第二步：使用这些 product_id 去查询 product.template 表，找到匹配的 categ_id
						const all_products = await rpcQuery('product.template', 'search_read', [['id', 'in', productIds]], ['name', 'categ_id']);
						
						// 第三步：检查 categ_id，如果匹配就添加到 product_category_2 的选项中
						$.each(all_products, function(i, product) {
							if (product.categ_id[0] === parseInt(selectedCategId)) {
								productCategory2.append($('<option>').val(product.id).text(product.name));
							}
						});                        
						self.initProductCategory2ChangeListener(selectedCustomerClassId);
					} catch (error) {
						console.error("发生错误：", error);
					}
				}
			});
		},

		
		fetchSaleProductCategories: async function(selectedCustomerClassId) {
			debugLog("选择的客户类别ID:", selectedCustomerClassId);
	
			if (!selectedCustomerClassId) return;
	
			const quotations = await rpcQuery('dtsc.quotation', 'search_read', [['customer_class_id', '=', selectedCustomerClassId]], ['product_id']);
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
			/* const $categoryDropdown = $('.product_category');
			categories.forEach(category => $categoryDropdown.append($('<option>').val(category.id).text(category.name)));
			$categoryDropdown.find('option:contains("All")').remove();
			this.initProductCategoryChangeListener(selectedCustomerClassId); */
		},


		
		showCustomerDetails: function(selectedCustomer) { 
            debugLog('selectedCustomer',selectedCustomer);
            debugLog('partner_id',this.partner_id);
            debugLog('customer_class_id',this.customer_class_id);
            debugLog('custom_init_name',this.custom_init_name);
            debugLog('nop',this.nop);
			var self= this;
			$('.customer-detail').remove(); 
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
					$('<input>').addClass('form-control val_required').attr({type: 'text', name: 'delivery_char', id: 'delivery_char', placeholder: '請輸入交貨方式:自取、快遞(科影代叫)、貨運、施工，若無填寫一律為自取...等'}),
					$('<div>').addClass('invalid-feedback').text('必填')
				)
			);

			var commentRow = $('<div class="form-row customer-detail mt-3 mb-3">').append(  // mt-3增加上边距
				$('<div class="form-group col-md-12">').append(
					$('<label>').attr('for', 'delivery_comment').text('訂單備註'),
					$('<input>').addClass('form-control').attr({type: 'text', name: 'delivery_comment', id: 'delivery_comment', placeholder: '請輸入收件聯絡人姓名+電話+地址或訂單備註...等'})
				)
			);
			
			//////////////////////
			var projectTitle2 = $('<h4>').addClass('customer-detail mb-3').html('<b>產品清單</b>');
			$('input[name="search"]').after(labelRow, valueRow, labelRow_2, valueRow_2, horizontalLine, projectTitle, projectInput, deliveryRow, commentRow, projectTitle2);
			
			this.fetchSaleProductCategories(this.customer_class_id).then(categories => {
				debugLog("categories", categories);
				
				var addButtonDiv = $('<div>').addClass('text-left customer-detail').append(
					$('<button>').attr({id: 'add_product_table', type: 'button'}).addClass('btn btn-success').append(
						$('<i>').addClass('fa fa-plus')
					)
				);

				$('.customer-detail:last').after(addButtonDiv); 
				$('#add_product_table').off('click');
				$('#add_product_table').on('click', () => {
					this.createBannerTable(selectedCustomer, categories);
					$('a.d-none').removeClass('d-none');
				});
				
				this.createBannerTable(selectedCustomer, categories);
				
				///////////////////////
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
			
			////////////////////////////////预览后
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
				// 这里可以添加您的确认订购逻辑
				$('#ModelOrderLine').modal('hide');
				self.prepareCheckoutData();
			});
			

			//////
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
							self.partner_id = customer.id//客户id
							self.customer_class_id = customer.customclass_id[0]//客户分类id
							self.custom_init_name = customer.custom_init_name//客户簡稱
                            $('.customer-detail').remove(); 
                            var selectedCustomer = $(this).data('customer');
							self.showCustomerDetails(selectedCustomer); 
							self.nop = customer.nop;
							debugLog("customer===",customer);
                            // 查询 dtsc.customclass 中的 nop
                            /* rpcQuery('dtsc.customclass', 'search_read', [
                                ['id', '=', self.customer_class_id]
                            ], ['nop']).then(customClass => {
                                if (customClass && customClass.length > 0) {
                                    self.nop = customClass[0].nop;
                                    debugLog("NOP:", self.nop);
                                } else {
                                    console.warn('No custom class found for id:', self.customer_class_id);
                                }
                            }).catch(error => {
                                console.error('Error fetching custom class:', error);
                            }); */
                        });

                        customerList.append(listItem);
                    });
                    $('.customer-list').remove();
                    $('input[name="search"]').after(customerList);
                });
            }
        }
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
        if ($(".banner_service_form_order").length > 0) {
            var checkoutWidget = new CheckoutWidget();
            checkoutWidget.appendTo($(".banner_service_form_order"));
        }
        $(document).on('change', '.custom-file-input', function() {
            var fileSize = this.files[0].size / 1024 / 1024; // 转换为MB
            if (fileSize > 500) {
                alert('文件超過500M限制，請選擇其它文件或者聯繫管理員上傳。');
                this.value = ''; // 重置文件输入
                /* $(this).next('.upload-status').addClass('d-none'); // 隐藏上传状态
                $(this).nextAll('.uploadProgressBar').hide(); // 隐藏进度条 */
            } else {
                /* $(this).next('.upload-status').removeClass('d-none').text('文件大小合适，可以上传。'); // 显示上传状态
                $(this).nextAll('.uploadProgressBar').show(); // 显示进度条 */
            }
        });
    });

    return CheckoutWidget;
});
