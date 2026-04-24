odoo.define('dtsc.ai_member_check', function (require) {
    'use strict';

    var publicWidget = require('web.public.widget');
    var ajax = require('web.ajax');
    var core = require('web.core');

    var _t = core._t;

    publicWidget.registry.DtscAiMemberCheck = publicWidget.Widget.extend({
        selector: '.o_dtsc_ai_member_page',
        events: {
            'change .o_ai_member_file_input': '_onChangeFile',
            'change .o_ai_member_select_all': '_onToggleSelectAll',
            'change .o_ai_member_item_checkbox': '_onToggleItem',
            'click .o_ai_member_detect_btn': '_onDetectItem',
            'click .o_ai_member_batch_detect_btn': '_onBatchDetect',
        },

        start: function () {
            this.$customerName = this.$('.o_ai_member_customer_input');
            this.$items = this.$('.o_ai_member_item');
            this.$selectAll = this.$('.o_ai_member_select_all');
            this.$batchButton = this.$('.o_ai_member_batch_detect_btn');
            this.$batchStatus = this.$('.o_ai_member_batch_status');
            this._isBatchRunning = false;
            this._prefillCustomerName();
            this._initGeneratedFilenames();
            this._renderBatchState();
            return this._super.apply(this, arguments);
        },

        _safeTrim: function (value) {
            return String(value || '').trim();
        },

        _initGeneratedFilenames: function () {
            var self = this;
            this.$items.each(function () {
                self._refreshGeneratedFilename($(this));
            });
        },

        _prefillCustomerName: function () {
            var self = this;
            ajax.jsonRpc('/my/user_info_client', 'call', {}).then(function (userInfo) {
                if (!userInfo || userInfo.error) {
                    return;
                }
                var displayName = self._safeTrim(userInfo.name);
                if (displayName && !self._safeTrim(self.$customerName.val())) {
                    self.$customerName.val(displayName);
                }
            });
        },

        _onChangeFile: function (ev) {
            var file = ev.currentTarget.files && ev.currentTarget.files[0];
            var $item = $(ev.currentTarget).closest('.o_ai_member_item');
            var $fileName = $item.find('.o_ai_member_file_name');

            if (file) {
                $fileName.text(file.name);
                this._refreshGeneratedFilename($item, file.name);
            } else {
                $fileName.text(_t('尚未選擇檔案'));
                this._refreshGeneratedFilename($item);
            }
        },

        _refreshGeneratedFilename: function ($item, originalFilename) {
            $item.find('.o_ai_member_filename').val(
                this._buildUploadFilename($item, originalFilename || '')
            );
        },

        _getSelectedItems: function () {
            return this.$items.filter(function () {
                return $(this).find('.o_ai_member_item_checkbox').is(':checked');
            });
        },

        _renderBatchState: function (message) {
            var selectedCount = this._getSelectedItems().length;

            this.$batchButton
                .prop('disabled', this._isBatchRunning || !selectedCount)
                .text(this._isBatchRunning ? _t('批量檢測並上傳中...') : _t('批量檢測並上傳'));

            this.$selectAll.prop('disabled', this._isBatchRunning);
            this.$items.find('.o_ai_member_item_checkbox').prop('disabled', this._isBatchRunning);

            if (message !== undefined) {
                this.$batchStatus.text(message);
                return;
            }

            this.$batchStatus.text(selectedCount ? (_t('已勾選 ') + selectedCount + _t(' 項')) : _t('尚未勾選項目'));
        },

        _syncSelectAllState: function () {
            var itemCount = this.$items.length;
            var selectedCount = this._getSelectedItems().length;
            this.$selectAll.prop('checked', !!itemCount && itemCount === selectedCount);
        },

        _onToggleSelectAll: function (ev) {
            var checked = !!$(ev.currentTarget).prop('checked');
            this.$items.find('.o_ai_member_item_checkbox').prop('checked', checked);
            this._renderBatchState();
        },

        _onToggleItem: function () {
            this._syncSelectAllState();
            this._renderBatchState();
        },

        _buildUploadFilename: function ($item, originalFilename) {
            var orderName = String($item.data('orderName') || '').trim() || 'A_ORDER';
            var itemNo = String($item.data('itemNo') || $item.data('itemIndex') || '').trim() || '1';
            var width = String($item.data('width') || '').trim();
            var height = String($item.data('height') || '').trim();
            var sourceName = originalFilename || String($item.data('projectName') || '').trim() || 'file';
            var ext = '';
            var base = sourceName;

            if (sourceName.indexOf('.') !== -1) {
                ext = sourceName.substring(sourceName.lastIndexOf('.'));
                base = sourceName.substring(0, sourceName.lastIndexOf('.'));
            }

            var root = [
                orderName,
                '項次' + itemNo,
                base || 'file',
                width + 'x' + height,
            ].join('-');

            root = root.replace(/[<>:"/\\|?*\s]/g, '_');
            return root + ext;
        },

        _onDetectItem: function (ev) {
            ev.preventDefault();
            var $button = $(ev.currentTarget);
            var $item = $button.closest('.o_ai_member_item');
            this._submitItem($item);
        },

        _submitItem: function ($item) {
            var self = this;
            var deferred = $.Deferred();
            var fileInput = $item.find('.o_ai_member_file_input')[0];
            var file = fileInput && fileInput.files && fileInput.files[0];
            var lineId = Number($item.data('lineId') || 0);
            var width = String($item.data('width') || '').trim();
            var height = String($item.data('height') || '').trim();
            var generatedFilename = this._safeTrim($item.find('.o_ai_member_filename').val());

            if (!file) {
                this._showResult($item, false, _t('請先選擇檔案'));
                deferred.resolve(false);
                return deferred.promise();
            }

            if (!lineId) {
                this._showResult($item, false, _t('缺少訂單項目資料'));
                deferred.resolve(false);
                return deferred.promise();
            }

            if (!width || !height) {
                this._showResult($item, false, _t('此訂單項目沒有設定尺寸'));
                deferred.resolve(false);
                return deferred.promise();
            }

            this._setItemLoading($item, true);
            this._resetResult($item);

            var formData = new FormData();
            formData.append('custom_file', file);
            formData.append('line_id', lineId);
            formData.append('filename', generatedFilename);
            formData.append('customer_name', this._safeTrim(this.$customerName.val()));

            $.ajax({
                url: this.$el.data('checkUrl'),
                type: 'POST',
                data: formData,
                contentType: false,
                processData: false,
                dataType: 'json',
            }).done(function (response) {
                self._showResult(
                    $item,
                    !!response.success,
                    response.message || (response.success ? _t('檔案檢測通過並已上傳') : _t('檔案檢測失敗')),
                    response.upload_filename || response.checked_filename,
                    response.image_info || {}
                );
                if (response.upload_filename) {
                    $item.find('.o_ai_member_uploaded_filename').text(response.upload_filename);
                    $item.find('.o_ai_member_filename').val(response.upload_filename);
                }

                if (response.redirect_url) {
                    window.location.href = response.redirect_url;
                    deferred.resolve(false);
                    return;
                }
                deferred.resolve(!!response.success);
            }).fail(function (xhr) {
                var message = _t('檔案檢測失敗');
                var redirectUrl = '';
                if (xhr.responseJSON) {
                    if (xhr.responseJSON.message) {
                        message = xhr.responseJSON.message;
                    }
                    redirectUrl = xhr.responseJSON.redirect_url || '';
                }
                self._showResult($item, false, message);
                if (redirectUrl) {
                    window.location.href = redirectUrl;
                }
                deferred.resolve(false);
            }).always(function () {
                self._setItemLoading($item, false);
            });

            return deferred.promise();
        },

        _onBatchDetect: function (ev) {
            ev.preventDefault();

            var self = this;
            var items = this._getSelectedItems().toArray().map(function (item) {
                return $(item);
            });
            var successCount = 0;
            var failedCount = 0;

            if (!items.length) {
                this._renderBatchState(_t('請先勾選要批量處理的項目'));
                return;
            }

            this._isBatchRunning = true;
            this._renderBatchState(_t('批量處理中 ') + 1 + '/' + items.length);

            var runNext = function (index) {
                if (index >= items.length) {
                    self._isBatchRunning = false;
                    self._syncSelectAllState();
                    self._renderBatchState(_t('批量處理完成：成功 ') + successCount + _t(' 項，失敗 ') + failedCount + _t(' 項'));
                    return;
                }

                self._renderBatchState(_t('批量處理中 ') + (index + 1) + '/' + items.length);
                self._submitItem(items[index]).then(function (success) {
                    if (success) {
                        successCount += 1;
                    } else {
                        failedCount += 1;
                    }
                    runNext(index + 1);
                });
            };

            runNext(0);
        },

        _setItemLoading: function ($item, isLoading) {
            var $button = $item.find('.o_ai_member_detect_btn');
            var $status = $item.find('.o_ai_member_status_text');
            $button.prop('disabled', isLoading);
            $button.text(isLoading ? _t('檢測並上傳中...') : _t('檢測並上傳'));
            $status.text(isLoading ? _t('正在檢測，通過後會直接上傳這一項') : '');
        },

        _resetResult: function ($item) {
            var $box = $item.find('.o_ai_member_result_box');
            $box.removeClass('is-visible o_ai_member_result--success o_ai_member_result--error');
            $box.find('.o_ai_member_result_title').text('');
            $box.find('.o_ai_member_result_message').text('');
            $box.find('.o_ai_member_checked_filename').text('-');
            $box.find('.o_ai_member_actual_size').text('-');
            $box.find('.o_ai_member_actual_pixels').text('-');
            $box.find('.o_ai_member_expected_size').text('-');
        },

        _showResult: function ($item, success, message, checkedFilename, imageInfo) {
            imageInfo = imageInfo || {};
            var expected = imageInfo.filename_size || {};
            var pixelText = '-';
            var $box = $item.find('.o_ai_member_result_box');

            if (imageInfo.width_px !== undefined && imageInfo.height_px !== undefined) {
                pixelText = imageInfo.width_px + ' x ' + imageInfo.height_px;
            }

            $box
                .addClass('is-visible')
                .removeClass('o_ai_member_result--success o_ai_member_result--error')
                .addClass(success ? 'o_ai_member_result--success' : 'o_ai_member_result--error');

            $box.find('.o_ai_member_result_title').text(success ? _t('檢測通過') : _t('檢測失敗'));
            $box.find('.o_ai_member_result_message').text(message || '');
            $box.find('.o_ai_member_checked_filename').text(checkedFilename || '-');
            $box.find('.o_ai_member_actual_size').text(this._formatSize(imageInfo.width_mm, imageInfo.height_mm));
            $box.find('.o_ai_member_actual_pixels').text(pixelText);
            $box.find('.o_ai_member_expected_size').text(this._formatSize(expected.width_mm, expected.height_mm));
        },

        _formatSize: function (width, height) {
            if (width === undefined || width === null || width === '' || height === undefined || height === null || height === '') {
                return '-';
            }
            return this._roundMaybe(width) + ' x ' + this._roundMaybe(height) + ' mm';
        },

        _roundMaybe: function (value) {
            if (value === undefined || value === null || value === '') {
                return '-';
            }
            return Math.round(value * 100) / 100;
        },
    });
});
