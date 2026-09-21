odoo.define('dtsc.checkout', function (require) {
    "use strict";
	var debugMode = true;
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
		},
        start: function () {
			this.conversion_formula="";
			this.rounding_method="";
            this._super.apply(this, arguments);
            this.fetchUnitConversion();
            this.bindSearchInputEvent();
			this.bindParamInputEvents(); 
			//this.prepareCheckoutData();
        },
        
        uploadFile: function($table) {
            return new Promise(async (resolve, reject) => {
                var uploadedFileName = "";
                var $fileInput = $table.find("input[type='file']");
                var fileName = $table.find('#project_product_name').val();
                var Folder = this.custom_init_name
                var file = $fileInput[0].files[0]; // 获取选中的文件
                if (file) {
                    var formData = new FormData();
                    formData.append('custom_file', file); // 'custom_file' 是文件输入框的 name 属性值
                    formData.append('fileName', encodeURIComponent(fileName));
                    formData.append('folder', encodeURIComponent(Folder));
                    debugLog('fileName',encodeURIComponent(fileName));
                    debugLog('Folder',encodeURIComponent(Folder));
                    /* formData.append('fileName', fileName);
                    formData.append('folder', Folder);
                    alert(fileName)
                    alert(Folder)  */
                    try {
                        let response = await $.ajax({  
                            url: 'http://43.156.27.132/upload.php',
                            type: 'POST',
                            data: formData,
                            contentType: false,
                            processData: false,
                        });
                        var result = JSON.parse(response);
                        if (result.success) {
                            uploadedFileName = result.fileName;
                            debugLog('Uploaded file name:', uploadedFileName);
                            resolve(uploadedFileName); // Resolve the promise with the file name
                        } else {
                            console.error('Upload failed:', result.error);
                            reject(result.error);
                        }
                    } catch (error) {
                        console.error('File upload error:', error);
                        reject(error);
                    }
                } else {
                    resolve(""); // Resolve the promise with an empty string if there is no file
                }
            });
        },

		
		prepareCheckoutData: async function() {
			var self = this; 
            var uploadPromises = [];
            var customer_class_id_p = this.customer_class_id
			let vals = {
				project_name: $("input[name='project_name']").val(),
				customer_id : this.partner_id,
				delivery_carrier : $("input[name='delivery_char']").val(),
				//estimated_date : fields.Date(string='預計使用日期')
				//checkout_order_state
				customer_class_id : customer_class_id_p,
				comment :  $("#delivery_comment").val(),
				//quantity : fields.Integer(string="總數量"),
				//unit_all : fields.Integer(string="總才數"),
				//total_price : fields.Integer(string="訂單總價"),
				//user_id : session.uid,
				//create_date : fields.Datetime(string="進單日")
				//payment_first : fields.Boolean("先收款再製作"),
				//create_id : fields.Many2one('res.users',string="訂單建立者", default=lambda self: self.env.user),
				product_ids: []
			};
			$(".banner_table").each(function() {
				var $table = $(this);
				
                /* // 新增: 上传文件
                var uploadedFileName = "";
                var $fileInput = $table.find("input[type='file']");
                var file = $fileInput[0].files[0]; // 获取选中的文件
                if (file) {
                    var formData = new FormData();
                    formData.append('custom_file', file); // 'custom_file' 是文件输入框的 name 属性值

                    try {
                        let response = await $.ajax({  // 添加 await 关键字
                            url: 'http://43.156.27.132/upload.php',
                            type: 'POST',
                            data: formData,
                            contentType: false, // 不要设置内容类型，让浏览器自动设置
                            processData: false, // 不要处理数据
                        });
                        var result = JSON.parse(response);
                        if (result.success) {
                            uploadedFileName = result.fileName;
                            console.log('Uploaded file name:', uploadedFileName);
                        } else {
                            console.error('Upload failed:', result.error);
                        }
                    } catch (error) {
                        console.error('File upload error:', error);
                    }
                } */
                uploadPromises.push(self.uploadFile($table));

                
				let pp = [];
				$table.find("input[name='multiple[]']:checked").each(function() {
					pp.push("'" + $(this).parent().text().trim() + "'");
				});
				//var ppString = '[' + pp.join(', ') + ']';
				var ppString = pp.join(', ');
				
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
					//image_url : uploadedFileName,  
					//peijian_price : fields.Float("配件加價")
					//units_price : $table.find("#base_price").val(),
					//product_total_price : fields.Float("產品總價")
					//total_make_price : fields.Float("加工總價")
					//price = fields.Float("價錢") 
				}]);
			}); 
            try {
                var uploadedFileNames = await Promise.all(uploadPromises);
                console.log('All files uploaded:', uploadedFileNames);
            
                uploadedFileNames.forEach((uploadedFileName, index) => {
                    // 使用 uploadedFileName 更新 vals.product_ids 中相应的 image_url 属性
                     if (uploadedFileName) {  // 添加判断条件，只有当 uploadedFileName 不为空时，才更新 image_url
                        vals.product_ids[index][2].image_url = uploadedFileName;   
                    }
                });

                debugLog("vals:",vals);
                rpc.query({
                    model: 'dtsc.checkout',
                    method: 'create',
                    args: [vals],
                })
                .then(function(new_id){
                    debugLog("New record ID:", new_id);
                    alert("感謝您的訂購！！");
                    location.reload();  // 刷新页面
                })
                .catch(function(error){
                    console.error("Error:", error);
                });
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
				 $('<th>').attr('colspan', '12').css({'padding-top': '10px', 'padding-bottom': '10px'}).append(  
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
				$('<td>').attr('colspan', '8').append(
					$('<div>').addClass('form-group').append(
						$('<input>').addClass('form-control').attr({type: 'text', name: 'project_product_name', id: 'project_product_name', placeholder: '檔案名稱'})
					)
				),
				$('<td>') // 这个是占位的td，可以考虑移除或留着
			);

			var productSelectRow = $('<tr>').append(
				$('<td>').append(
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
			this.initProductCategoryChangeListener(selectedCustomer.customclass_id[0]); 
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
		
		generateTableContent:function() {//预览弹框内容
			var tableContent = `
				<table class="table table-striped table-borderless table-responsive-lg">
					<thead>
						<tr>
							<th scope="col">項</th>
							<th scope="col">產品名稱</th>
							<th scope="col">製作尺寸</th>
							<th scope="col">數量</th>
						</tr>
					</thead>
					<tbody>
			`;

			$('#banner_table tr.input_row_class').each(function (index, row) {
				var fileName = $(row).closest('table').find('#project_product_name').val();
				/* var productSelection = $(row).closest('table').find('.product_category option:selected').text() + "_" + $(row).closest('table').find('.product_category_2 option:selected').text() + "_" + $(row).closest('table').find('.product_variant option:selected').text(); */
                ///
                let pp = [];
				$(row).closest('table').find("input[name='multiple[]']:checked").each(function() {
					pp.push("'" + $(this).parent().text().trim() + "'");
				});
				//var ppString = '[' + pp.join(', ') + ']';
				var ppString = pp.join(', ');
                ///
				var productSelection = $(row).closest('table').find('.product_category option:selected').text() + "_" + $(row).closest('table').find('.product_category_2 option:selected').text() + "_" + $(row).closest('table').find('.product_variant option:selected').filter(function() {return $(this).text() !== "無";}).text()+ "_" + ppString + "_" + $(row).closest('table').find("input[type='text'].form-control[name='comment']").val();
				var width = $(row).find('#param1').val();
				var height = $(row).find('#param2').val();
				var productSize = `${width}x${height}`;
				var quantity = $(row).find('#quantity').val();

				tableContent += `
					<tr>
						<th scope="row">${index + 1}</th>
						<td>檔名：${fileName}<br>${productSelection}</td>
						<td>${productSize}</td>
						<td>${quantity}</td>
					</tr>
				`;
			});

			tableContent += `
					</tbody>
				</table>
			`;

    return tableContent;
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
                    let acc_value = $("select[name='accessory'] option:selected").text();
                    debugLog("accessory:", acc_value);
                    if (acc_value && acc_value !== '不加配件') { 
                        accessory = true;
                    }
					var newTr1 = $('<tr>').addClass('table-active product_attribute_class tr_product_attribute_class').css({'padding-top': '7px', 'padding-bottom': '7px'});
					newTr1.append($('<th>').text('寬度(公分)'));
					newTr1.append($('<th>').text('高度(公分)'));
					newTr1.append($('<th>').text('每件(才數)'));
                    if(accessory)
					{
                        newTr1.append($('<th>').text('配件數量'));
                    }
					newTr1.append($('<th>').text('數量(件)'));
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
					var newInput3 = $('<input>').attr({type: 'text', readonly: '1', id: 'total_units', name: 'total_units', class: 'form-control-plaintext'}).on('input', function(e) {
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
					var newLabel10 = $('<label>').addClass('custom-file-label').attr('for', 'custom_file').text('選擇檔案');
					var newDiv10_2 = $('<div>').addClass('invalid-feedback').text('請選擇需要上傳的檔案');
					var newInput10_2 = $('<input>').attr({type: 'text', class: 'custom_file_status d-none', name: 'custom_file_status', value: ''});
					newDiv10.append(newInput10).append(newLabel10).append(newDiv10_2).append(newInput10_2);
					newTd10.append(newDiv10); 

					// 将所有的 <td> 元素添加到 <tr> 中
					newTr2.append(newTd1).append(newTd2).append(newTd3).append(newTd4).append(newTd5).append(newTd6).append(newTd7).append(newTd8).append(newTd9).append(newTd10);
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
								['make_type_id']
							);
							debugLog("productMakeTypeRelResults:", productMakeTypeRelResults);
							if (!productMakeTypeRelResults) {
								console.error("无法获取 product_maketype_rel 数据"); 
							}
							if (productMakeTypeRelResults && productMakeTypeRelResults.length > 0) {
								// 添加标题行
								var headerTr = $('<tr>').addClass('table-active product_attribute_class tr_product_attribute_class');
								var headerTh = $('<th>').attr('colspan', '12').text('後加工方式, 此區塊估價將由業務人員與您討論後提供');
								headerTr.append(headerTh);
								 $(this).closest('table').append(headerTr);
								for (const postProcess of productMakeTypeRelResults) {
									debugLog("後加工",postProcess.make_type_id[1]);
									var newCheckboxTr = $('<tr>').addClass('product_attribute_checkboxs tr_product_attribute_class');
									var newTdCheckbox = $('<td>').attr('colspan', '12');
									var newDivCheckbox = $('<div>').addClass('form-check');
									var newLabelCheckbox = $('<label>').addClass('form-check-label');
									var newInputCheckbox = $('<input>').css({'margin': '0 10px 0 0'}).attr({ type: 'checkbox', name: 'multiple[]', value: postProcess.id, id: postProcess.id });

									newLabelCheckbox.append(newInputCheckbox).append(postProcess.make_type_id[1]);
									newDivCheckbox.append(newLabelCheckbox);
									newTdCheckbox.append(newDivCheckbox);
									newCheckboxTr.append(newTdCheckbox);

									$(this).closest('table').append(newCheckboxTr);
								}
							}
						}catch (error) {
							console.error("An error occurred:", error);
						}
					}
					var newCommentRow = $('<tr>').addClass('product_attribute_class tr_product_attribute_class');
					var newCommentTd = $('<td>').attr('colspan', '8');
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
		
		initProductCategory2ChangeListener: function() {
            const outerSelf = this;
            $(document).off('change', '.product_category_2');
            $(document).on('change', '.product_category_2', async function() {
                $(this).closest('table').find('.product_variant').closest('td').remove();
                $(this).closest('table').find('.tr_product_attribute_class').closest('tr').remove();

                var selectedProductId = $(this).val();
                debugLog("Selected Product ID:", selectedProductId);

                // 清除当前行中已有的变体下拉框
                $(this).closest('tr').find('td').has('.product_variant').remove();

                if (selectedProductId) {
                    try {
                        const attributeLines = await rpcQuery('product.template.attribute.line', 'search_read', [['product_tmpl_id', '=', parseInt(selectedProductId)]], ['attribute_id','sequence']);
                        attributeLines.sort((a, b) => a.sequence - b.sequence);
                        debugLog("attributeLines:", attributeLines);

                        for (let line of attributeLines) {
                            var attributeId = line.attribute_id[0];
                            debugLog("attributeId:", attributeId);
                            const attributeValues = await rpcQuery('product.template.attribute.value', 'search_read', [
                                ['attribute_id', '=', attributeId],
                                ['product_tmpl_id', '=', parseInt(selectedProductId)]
                            ], ['product_attribute_value_id', 'name']);

                            debugLog("attributeValues:", attributeValues);
                            var variantSelect = $('<select>').addClass('form-control product_variant');
                            if(line.attribute_id[1] === "配件") {
                                variantSelect.attr('name', 'accessory');
                            }

                            var newTd = $('<td>').append(
                                $('<div>').addClass('form-group').append(variantSelect)
                            );

                            $(this).closest('tr').append(newTd);

                            var defaultOptionText = ` -- 請選擇${line.attribute_id[1]}屬性 -- `;
                            variantSelect.append($('<option>').attr({disabled: '1', selected: '1'}).text(defaultOptionText));

                            $.each(attributeValues, function(j, value) {
                                variantSelect.append($('<option>').val(value.product_attribute_value_id[0]).text(value.name));
                            });

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
					var newTd = $('<td>').append(
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
						self.initProductCategory2ChangeListener();
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
			var addressInput = $('<input type="text" class="form-control form-control-plaintext" readonly="1">').val(selectedCustomer.contact_address_complete || '').addClass('detail-input-full');
			
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
					$('<label>').attr('for', 'delivery_char').text('運送方式'),
					$('<input>').addClass('form-control val_required').attr({type: 'text', name: 'delivery_char', id: 'delivery_char', placeholder: '請輸入運送方式:自取、快遞(科影代叫)、貨運、施工，若無填寫一律為自取...等'}),
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
			
			this.fetchSaleProductCategories(selectedCustomer.customclass_id[0]).then(categories => {
				debugLog("categories", categories);
				
				var addButtonDiv = $('<div>').addClass('text-right customer-detail').append(
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
						var tableContent = self.generateTableContent();
						$('#ModelOrderLine .modal-body.summary_modal_content').html(tableContent);  // 将表格内容插入到模态框的 modal-body
						$('#ModelOrderLine').modal('show');
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
                        ['customer_rank', '>', 0] // 添加的条件为客户
                    ],
                    fields: ['id','name', 'mobile', 'phone', 'email', 'contact_address_complete','customclass_id','custom_init_name'], 
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
        if ($(".banner_service_form_checkout").length > 0) {
            var checkoutWidget = new CheckoutWidget();
            checkoutWidget.appendTo($(".banner_service_form_checkout"));
        }
    });

    return CheckoutWidget;
});
