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
            'click .o_ai_member_batch_pick_btn': '_onBatchPickClick',
            'change .o_ai_member_batch_file_input': '_onBatchFilesSelected',
            'click .o_ai_member_multi_artboard_btn': '_onMultiArtboardBatchDetect',
            'click .o_ai_member_confirm_upload_btn': '_onConfirmUpload',
            'click .o_ai_member_cancel_upload_btn': '_onCancelUpload',
        },

        start: function () {
            this.$customerName = this.$('.o_ai_member_customer_input');
            this.$items = this.$('.o_ai_member_item');
            this.$selectAll = this.$('.o_ai_member_select_all');
            this.$batchButton = this.$('.o_ai_member_batch_detect_btn');
            this.$batchPickButton = this.$('.o_ai_member_batch_pick_btn');
            this.$batchFileInput = this.$('.o_ai_member_batch_file_input');
            this.$multiArtboardButton = this.$('.o_ai_member_multi_artboard_btn');
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

        _clearItemCheckState: function ($item) {
            this._resetResult($item);
            $item.find('.o_ai_member_status_text').text('');
            var $button = $item.find('.o_ai_member_detect_btn');
            if (!$button.prop('disabled')) {
                $button.text(_t('檢測並上傳'));
            }
        },

        _onChangeFile: function (ev) {
            var file = ev.currentTarget.files && ev.currentTarget.files[0];
            var $item = $(ev.currentTarget).closest('.o_ai_member_item');
            var $fileName = $item.find('.o_ai_member_file_name');

            this._clearItemCheckState($item);

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

        _parseItemNoFromFilename: function (filename) {
            var base = String(filename || '').replace(/\.[^.]+$/, '');
            if (!/^\d+$/.test(base)) {
                return null;
            }
            return parseInt(base, 10);
        },

        _getItemMapByNo: function () {
            var map = {};
            this.$items.each(function () {
                var $item = $(this);
                var itemNo = parseInt(String($item.data('itemNo') || ''), 10);
                if (!isNaN(itemNo)) {
                    map[itemNo] = $item;
                }
            });
            return map;
        },

        _assignFileToItem: function ($item, file) {
            var fileInput = $item.find('.o_ai_member_file_input')[0];
            if (!fileInput || !file || typeof DataTransfer === 'undefined') {
                return false;
            }
            var transfer = new DataTransfer();
            transfer.items.add(file);
            fileInput.files = transfer.files;
            $item.find('.o_ai_member_file_name').text(file.name);
            this._refreshGeneratedFilename($item, file.name);
            this._clearItemCheckState($item);
            return true;
        },

        _mapBatchFiles: function (files) {
            var itemMap = this._getItemMapByNo();
            var usedItemNos = {};
            var mapped = [];
            var warnings = [];

            Array.prototype.forEach.call(files || [], function (file) {
                var itemNo = this._parseItemNoFromFilename(file.name);
                if (itemNo === null) {
                    warnings.push(_t('檔名無法對應項次：') + file.name);
                    return;
                }
                if (!itemMap[itemNo]) {
                    warnings.push(_t('找不到項次 ') + itemNo + _t('：') + file.name);
                    return;
                }
                if (usedItemNos[itemNo]) {
                    warnings.push(_t('項次 ') + itemNo + _t(' 已有檔案，略過：') + file.name);
                    return;
                }
                if (!this._assignFileToItem(itemMap[itemNo], file)) {
                    warnings.push(_t('無法指派檔案至項次 ') + itemNo + _t('：') + file.name);
                    return;
                }
                usedItemNos[itemNo] = true;
                mapped.push({
                    itemNo: itemNo,
                    $item: itemMap[itemNo],
                    filename: file.name,
                });
            }, this);

            mapped.sort(function (a, b) {
                return a.itemNo - b.itemNo;
            });

            return {
                mapped: mapped,
                warnings: warnings,
            };
        },

        _normalizeSubmitResult: function (result) {
            if (result && typeof result === 'object' && 'success' in result) {
                return result;
            }
            return { success: !!result, needsConfirm: false };
        },

        _buildBatchSummary: function (stats) {
            var parts = [
                _t('批量完成：成功 ') + stats.successCount + _t(' 項，失敗 ') + stats.failedCount + _t(' 項'),
            ];
            if (stats.confirmCount) {
                parts.push(_t('（含需確認 ') + stats.confirmCount + _t(' 項）'));
            }
            if (stats.warningCount) {
                parts.push(_t('，略過 ') + stats.warningCount + _t(' 個檔案'));
            }
            return parts.join('');
        },

        _runBatchItems: function (items, progressPrefix, options) {
            options = options || {};
            var self = this;
            var deferred = $.Deferred();
            var successCount = 0;
            var failedCount = 0;
            var confirmCount = 0;
            var index = 0;

            if (!items.length) {
                deferred.resolve({
                    successCount: 0,
                    failedCount: 0,
                    confirmCount: 0,
                });
                return deferred.promise();
            }

            this._isBatchRunning = true;
            this._renderBatchState(progressPrefix + ' ' + 1 + '/' + items.length);

            var runNext = function () {
                if (index >= items.length) {
                    self._isBatchRunning = false;
                    self._syncSelectAllState();
                    deferred.resolve({
                        successCount: successCount,
                        failedCount: failedCount,
                        confirmCount: confirmCount,
                    });
                    return;
                }

                var $item = items[index];
                index += 1;
                self._renderBatchState(progressPrefix + ' ' + index + '/' + items.length);
                self._submitItem($item, options).then(function (result) {
                    result = self._normalizeSubmitResult(result);
                    if (result.success) {
                        successCount += 1;
                    } else {
                        failedCount += 1;
                        if (result.needsConfirm) {
                            confirmCount += 1;
                        }
                    }
                    runNext();
                });
            };

            runNext();
            return deferred.promise();
        },

        _onBatchPickClick: function (ev) {
            ev.preventDefault();
            if (this._isBatchRunning) {
                return;
            }
            this.$batchFileInput.val('');
            this.$batchFileInput.trigger('click');
        },

        _buildBatchPickSummary: function (mapping) {
            if (!mapping.mapped.length) {
                return mapping.warnings.join('；') || _t('沒有可對應的檔案');
            }

            var itemNos = mapping.mapped.map(function (row) {
                return row.itemNo;
            }).join('、');
            var parts = [
                _t('已指派 ') + mapping.mapped.length + _t(' 個檔案並勾選項次 ') + itemNos,
                _t('，請按「批量檢測並上傳」'),
            ];
            if (mapping.warnings.length) {
                parts.push('；' + mapping.warnings.join('；'));
            }
            return parts.join('');
        },

        _checkMappedBatchItems: function (mapped) {
            mapped.forEach(function (row) {
                row.$item.find('.o_ai_member_item_checkbox').prop('checked', true);
            });
            this._syncSelectAllState();
        },

        _onBatchFilesSelected: function (ev) {
            var files = ev.currentTarget.files;
            if (!files || !files.length || this._isBatchRunning) {
                return;
            }

            var mapping = this._mapBatchFiles(files);
            if (mapping.mapped.length) {
                this._checkMappedBatchItems(mapping.mapped);
            }
            this._renderBatchState(this._buildBatchPickSummary(mapping));
        },

        _onMultiArtboardBatchDetect: function (ev) {
            ev.preventDefault();

            var self = this;
            var items = this._getSelectedItems().toArray().map(function (item) {
                return $(item);
            });

            if (!items.length) {
                this._renderBatchState(_t('請先勾選要多圖簡易檢測的項目'));
                return;
            }

            this._runBatchItems(items, _t('多圖簡易檢測中'), {
                checkMode: 'multi_artboard',
            }).then(function (stats) {
                stats.warningCount = 0;
                self._renderBatchState(self._buildBatchSummary(stats));
            });
        },

        _getSelectedItems: function () {
            return this.$items.filter(function () {
                return $(this).find('.o_ai_member_item_checkbox').is(':checked');
            });
        },

        _isBatchStatusAlert: function (message) {
            if (!message) {
                return false;
            }
            return /請按「批量檢測並上傳」|無法對應|略過|找不到項次|沒有可處理|沒有可對應|請先勾選|不是多圖|多畫板|未轉外框|僅適用/.test(message);
        },

        _renderBatchState: function (message) {
            var selectedCount = this._getSelectedItems().length;

            this.$batchButton
                .prop('disabled', this._isBatchRunning || !selectedCount)
                .text(this._isBatchRunning ? _t('批量檢測並上傳中...') : _t('批量檢測並上傳'));

            this.$batchPickButton
                .prop('disabled', this._isBatchRunning)
                .text(_t('批量選檔'));

            this.$multiArtboardButton
                .prop('disabled', this._isBatchRunning || !selectedCount)
                .text(this._isBatchRunning ? _t('多圖簡易檢測中...') : _t('多圖批量簡易檢測並上傳'));

            this.$selectAll.prop('disabled', this._isBatchRunning);
            this.$items.find('.o_ai_member_item_checkbox').prop('disabled', this._isBatchRunning);

            if (message !== undefined) {
                this.$batchStatus
                    .toggleClass('o_ai_member_batch_status--alert', this._isBatchStatusAlert(message))
                    .text(message);
                return;
            }

            this.$batchStatus
                .removeClass('o_ai_member_batch_status--alert')
                .text(selectedCount ? (_t('已勾選 ') + selectedCount + _t(' 項')) : _t('尚未勾選項目'));
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

        _submitItem: function ($item, options) {
            options = options || {};
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

            if (options.checkMode === 'multi_artboard' && !/\.ai$/i.test(file.name || '')) {
                this._showResult($item, false, _t('多圖簡易檢測僅適用 .ai 檔案'));
                deferred.resolve({ success: false, needsConfirm: false });
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

            this._setItemLoading($item, true, options);
            if (!options.confirmBlurUpload) {
                this._resetResult($item);
            } else {
                this._setConfirmUploadLoading($item, true);
            }

            var formData = new FormData();
            formData.append('custom_file', file);
            formData.append('line_id', lineId);
            formData.append('filename', generatedFilename);
            formData.append('customer_name', this._safeTrim(this.$customerName.val()));
            if (options.confirmBlurUpload) {
                formData.append('confirm_blur_upload', '1');
            }
            if (options.checkMode) {
                formData.append('check_mode', options.checkMode);
            }

            $.ajax({
                url: this.$el.data('checkUrl'),
                type: 'POST',
                data: formData,
                contentType: false,
                processData: false,
                dataType: 'json',
            }).done(function (response) {
                response = response || {};
                self._setConfirmUploadLoading($item, false);

                if (response.can_confirm_upload) {
                    self._showResult(
                        $item,
                        false,
                        response.message || _t('檔案檢測失敗'),
                        response.upload_filename || response.checked_filename,
                        response.image_info || {},
                        response.blur_check || {}
                    );
                    self._showConfirmUpload($item);
                    deferred.resolve({ success: false, needsConfirm: true });
                    return;
                }

                self._hideConfirmUpload($item);
                self._showResult(
                    $item,
                    !!response.success,
                    response.message || (response.success ? _t('檔案檢測通過並已上傳') : _t('檔案檢測失敗')),
                    response.upload_filename || response.checked_filename,
                    response.image_info || {},
                    response.blur_check || {}
                );
                if (response.upload_filename) {
                    $item.find('.o_ai_member_uploaded_filename').text(response.upload_filename);
                    $item.find('.o_ai_member_filename').val(response.upload_filename);
                }

                if (response.success) {
                    var resultEl = $item.find('.o_ai_member_result_box')[0];
                    if (resultEl && resultEl.scrollIntoView) {
                        resultEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                }

                if (response.redirect_url) {
                    window.location.href = response.redirect_url;
                    deferred.resolve({ success: false, needsConfirm: false });
                    return;
                }
                deferred.resolve({
                    success: !!response.success,
                    needsConfirm: false,
                });
            }).fail(function (xhr) {
                self._setConfirmUploadLoading($item, false);
                var message = _t('檔案檢測失敗');
                var redirectUrl = '';
                if (xhr.responseJSON) {
                    if (xhr.responseJSON.message) {
                        message = xhr.responseJSON.message;
                    }
                    redirectUrl = xhr.responseJSON.redirect_url || '';
                }
                self._hideConfirmUpload($item);
                self._showResult($item, false, message);
                if (redirectUrl) {
                    window.location.href = redirectUrl;
                }
                deferred.resolve({ success: false, needsConfirm: false });
            }).always(function () {
                self._setItemLoading($item, false);
            });

            return deferred.promise();
        },

        _onConfirmUpload: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var $item = $(ev.currentTarget).closest('.o_ai_member_item');
            if (!$item.length) {
                return;
            }
            this._submitItem($item, { confirmBlurUpload: true });
        },

        _onCancelUpload: function (ev) {
            ev.preventDefault();
            var $item = $(ev.currentTarget).closest('.o_ai_member_item');
            this._hideConfirmUpload($item);
        },

        _showConfirmUpload: function ($item) {
            $item.find('.o_ai_member_confirm_upload').addClass('is-visible');
        },

        _hideConfirmUpload: function ($item) {
            var $confirm = $item.find('.o_ai_member_confirm_upload');
            $confirm.removeClass('is-visible is-loading');
            $confirm.find('.o_ai_member_confirm_upload_btn, .o_ai_member_cancel_upload_btn')
                .prop('disabled', false);
            $confirm.find('.o_ai_member_confirm_upload_status').text('');
        },

        _setConfirmUploadLoading: function ($item, isLoading) {
            var $confirm = $item.find('.o_ai_member_confirm_upload');
            if (!$confirm.length) {
                return;
            }
            $confirm.addClass('is-visible');
            $confirm.toggleClass('is-loading', !!isLoading);
            $confirm.find('.o_ai_member_confirm_upload_btn, .o_ai_member_cancel_upload_btn')
                .prop('disabled', !!isLoading);
            $confirm.find('.o_ai_member_confirm_upload_status').text(
                isLoading ? _t('正在確認上傳...') : ''
            );
        },

        _onBatchDetect: function (ev) {
            ev.preventDefault();

            var self = this;
            var items = this._getSelectedItems().toArray().map(function (item) {
                return $(item);
            });

            if (!items.length) {
                this._renderBatchState(_t('請先勾選要批量處理的項目'));
                return;
            }

            this._runBatchItems(items, _t('批量處理中')).then(function (stats) {
                stats.warningCount = 0;
                self._renderBatchState(self._buildBatchSummary(stats));
            });
        },

        _setItemLoading: function ($item, isLoading, options) {
            options = options || {};
            var $button = $item.find('.o_ai_member_detect_btn');
            var $status = $item.find('.o_ai_member_status_text');
            $button.prop('disabled', isLoading);
            if (isLoading) {
                if (options.confirmBlurUpload) {
                    $button.text(_t('確認上傳中...'));
                    $status.text(_t('正在確認上傳這一項'));
                } else if (options.checkMode === 'multi_artboard') {
                    $button.text(_t('簡易檢測中...'));
                    $status.text(_t('正在進行多圖簡易檢測（轉外框），通過後會直接上傳'));
                } else {
                    $button.text(_t('檢測並上傳中...'));
                    $status.text(_t('正在檢測，通過後會直接上傳這一項'));
                }
            } else {
                $button.text(_t('檢測並上傳'));
                $status.text('');
            }
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
            this._resetBlurPreview($item);
            this._hideConfirmUpload($item);
        },

        _resetBlurPreview: function ($item) {
            var $blur = $item.find('.o_ai_member_blur_preview');
            $blur.removeClass('is-visible');
            $blur.find('.o_ai_member_blur_image').attr('src', '');
            $blur.find('.o_ai_member_blur_ratio').text('-');
            $blur.find('.o_ai_member_blur_threshold').text('-');
            $blur.find('.o_ai_member_blur_avg_score').text('-');
            $blur.find('.o_ai_member_blur_min_score').text('-');
            $blur.find('.o_ai_member_blur_issues').removeClass('is-visible').empty();
            $blur.find('.o_ai_member_blur_zoom_label').text('100%');
            this._unbindBlurPan($blur);
        },

        _bindBlurPan: function ($blur) {
            var self = this;
            var $wrap = $blur.find('.o_ai_member_blur_image_wrap');
            var $img = $blur.find('.o_ai_member_blur_image');
            this._unbindBlurPan($blur);
            if (!$wrap.length || !$img.length) {
                return;
            }

            var state = { scale: 1, baseScale: 1, tx: 0, ty: 0, natW: 0, natH: 0 };
            $blur.data('blurViewState', state);

            var apply = function () {
                $img.css('transform', 'translate(' + state.tx + 'px,' + state.ty + 'px) scale(' + state.scale + ')');
                $blur.find('.o_ai_member_blur_zoom_label').text(
                    Math.round(state.scale / state.baseScale * 100) + '%'
                );
            };

            var clamp = function () {
                var wrapW = $wrap.width();
                var wrapH = $wrap.height();
                var imgW = state.natW * state.scale;
                var imgH = state.natH * state.scale;
                if (imgW <= wrapW) {
                    state.tx = (wrapW - imgW) / 2;
                } else {
                    state.tx = Math.min(0, Math.max(wrapW - imgW, state.tx));
                }
                if (imgH <= wrapH) {
                    state.ty = (wrapH - imgH) / 2;
                } else {
                    state.ty = Math.min(0, Math.max(wrapH - imgH, state.ty));
                }
            };

            var fit = function () {
                state.natW = $img[0].naturalWidth || $img.width();
                state.natH = $img[0].naturalHeight || $img.height();
                var wrapW = $wrap.width();
                var wrapH = $wrap.height();
                if (!state.natW || !state.natH || !wrapW || !wrapH) {
                    return;
                }
                state.baseScale = Math.min(wrapW / state.natW, wrapH / state.natH);
                state.scale = state.baseScale;
                clamp();
                apply();
            };

            state.fit = fit;
            state.zoomBy = function (factor, cx, cy) {
                var wrapW = $wrap.width();
                var wrapH = $wrap.height();
                if (cx === undefined) { cx = wrapW / 2; }
                if (cy === undefined) { cy = wrapH / 2; }
                var newScale = Math.min(state.baseScale * 8, Math.max(state.baseScale, state.scale * factor));
                var ratio = newScale / state.scale;
                state.tx = cx - ratio * (cx - state.tx);
                state.ty = cy - ratio * (cy - state.ty);
                state.scale = newScale;
                clamp();
                apply();
            };

            if ($img[0].complete && $img[0].naturalWidth) {
                fit();
            } else {
                $img.one('load.blurPan', fit);
            }

            var isPanning = false;
            var startX = 0;
            var startY = 0;
            var baseTx = 0;
            var baseTy = 0;

            $wrap.on('mousedown.blurPan', function (ev) {
                if (ev.button !== 0) { return; }
                isPanning = true;
                $wrap.addClass('is-dragging');
                startX = ev.pageX;
                startY = ev.pageY;
                baseTx = state.tx;
                baseTy = state.ty;
                ev.preventDefault();
            });

            $(document).on('mousemove.blurPan' + ($blur.attr('data-pan-id') || ''), function (ev) {
                if (!isPanning) { return; }
                state.tx = baseTx + (ev.pageX - startX);
                state.ty = baseTy + (ev.pageY - startY);
                clamp();
                apply();
                ev.preventDefault();
            });

            $(document).on('mouseup.blurPan' + ($blur.attr('data-pan-id') || ''), function () {
                isPanning = false;
                $wrap.removeClass('is-dragging');
            });

            $wrap.on('wheel.blurPan', function (ev) {
                ev.preventDefault();
                var oe = ev.originalEvent;
                var rect = $wrap[0].getBoundingClientRect();
                var cx = oe.clientX - rect.left;
                var cy = oe.clientY - rect.top;
                state.zoomBy(oe.deltaY < 0 ? 1.2 : 1 / 1.2, cx, cy);
            });

            $blur.find('.o_ai_member_blur_zoom_in').on('click.blurPan', function () { state.zoomBy(1.25); });
            $blur.find('.o_ai_member_blur_zoom_out').on('click.blurPan', function () { state.zoomBy(1 / 1.25); });
            $blur.find('.o_ai_member_blur_zoom_reset').on('click.blurPan', function () { fit(); });
        },

        _unbindBlurPan: function ($blur) {
            $blur.find('.o_ai_member_blur_image_wrap').off('.blurPan').removeClass('is-dragging');
            $blur.find('.o_ai_member_blur_image').off('.blurPan');
            $blur.find('.o_ai_member_blur_zoom_in, .o_ai_member_blur_zoom_out, .o_ai_member_blur_zoom_reset').off('.blurPan');
            $(document).off('mousemove.blurPan mouseup.blurPan');
            $blur.removeData('blurViewState');
        },

        _renderBlurIssues: function ($blur, blurCheck) {
            var $issues = $blur.find('.o_ai_member_blur_issues');
            var rows = blurCheck.low_dpi_issues || [];
            $issues.empty();
            if (!rows.length) {
                $issues.removeClass('is-visible');
                return;
            }

            rows.forEach(function (issue, index) {
                $issues.append(
                    $('<div/>', {
                        class: 'o_ai_member_blur_issue_item',
                        text: (
                            '低解析度位圖 #' + (index + 1) +
                            '：' + issue.width_px + ' x ' + issue.height_px + ' px，' +
                            '有效 DPI 約 ' + issue.effective_dpi +
                            '，佔版 ' + issue.coverage_ratio + '%'
                        ),
                    })
                );
            });
            $issues.addClass('is-visible');
        },

        _renderBlurPreview: function ($item, blurCheck) {
            blurCheck = blurCheck || {};
            var $blur = $item.find('.o_ai_member_blur_preview');
            if (!blurCheck.overlay_image_base64) {
                this._resetBlurPreview($item);
                return;
            }

            $blur.addClass('is-visible');
            $blur.find('.o_ai_member_blur_image').attr('src', blurCheck.overlay_image_base64);
            this._bindBlurPan($blur);
            this._renderBlurIssues($blur, blurCheck);
            $blur.find('.o_ai_member_blur_ratio').text(
                this._formatPercent(blurCheck.blur_area_ratio) +
                (blurCheck.blur_findings && blurCheck.blur_findings.length
                    ? ('（' + blurCheck.blur_findings.length + ' 處）')
                    : '')
            );
            $blur.find('.o_ai_member_blur_threshold').text(
                blurCheck.threshold !== undefined ? blurCheck.threshold : '-'
            );
            $blur.find('.o_ai_member_blur_avg_score').text(this._formatScore(blurCheck.avg_score));
            $blur.find('.o_ai_member_blur_min_score').text(this._formatScore(blurCheck.min_score));
        },

        _showResult: function ($item, success, message, checkedFilename, imageInfo, blurCheck) {
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
            if (!success && blurCheck && blurCheck.overlay_image_base64) {
                this._renderBlurPreview($item, blurCheck);
            } else {
                this._resetBlurPreview($item);
            }
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

        _formatPercent: function (value) {
            if (value === undefined || value === null || value === '') {
                return '-';
            }
            return this._roundMaybe(value) + '%';
        },

        _formatScore: function (value) {
            if (value === undefined || value === null || value === '') {
                return '-';
            }
            return this._roundMaybe(value);
        },
    });
});
