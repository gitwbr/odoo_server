odoo.define('dtsc.ai_file_check', function (require) {
    'use strict';

    var publicWidget = require('web.public.widget');
    var core = require('web.core');
    var fileNameHelper = require('dtsc.file_name_helper');
    var ajax = require('web.ajax');

    var _t = core._t;

    publicWidget.registry.DtscAiFileCheck = publicWidget.Widget.extend({
        selector: '.o_dtsc_ai_check_form',
        events: {
            'change .o_dtsc_ai_file': '_onChangeFile',
            'submit': '_onSubmit',
        },

        start: function () {
            this.$submit = this.$('.o_dtsc_ai_submit');
            this.$error = this.$el.parent().find('.o_dtsc_ai_result_error');
            this.$success = this.$el.parent().find('.o_dtsc_ai_result_success');
            this.$info = this.$el.parent().find('.o_dtsc_ai_result_info');
            this.$customerName = this.$el.parent().find('.o_dtsc_ai_customer_name');
            this._bindInputFilters();
            this._prefillCustomerName();
            return this._super.apply(this, arguments);
        },

        _onChangeFile: function (ev) {
            var file = ev.currentTarget.files && ev.currentTarget.files[0];
            var $fileLabel = this.$('.custom-file-label');
            if (file && $fileLabel.length) {
                $fileLabel.html(file.name);
            }
        },

        _bindInputFilters: function () {
            this.$('.o_dtsc_ai_width, .o_dtsc_ai_height').on('input', function () {
                this.value = this.value.replace(/[^0-9.]/g, '').replace(/(\..*?)\..*/g, '$1');
            });
        },

        _prefillCustomerName: function () {
            var self = this;
            ajax.jsonRpc('/my/user_info', 'call', {}).then(function (userInfo) {
                if (!userInfo || userInfo.error) {
                    return;
                }
                var displayName = (userInfo.name || '').trim();
                if (displayName && !self.$customerName.val().trim()) {
                    self.$customerName.val(displayName);
                }
            });
        },

        _onSubmit: function (ev) {
            ev.preventDefault();

            var self = this;
            var fileInput = this.$('.o_dtsc_ai_file')[0];
            var file = fileInput && fileInput.files && fileInput.files[0];
            var width = this.$('.o_dtsc_ai_width').val().trim();
            var height = this.$('.o_dtsc_ai_height').val().trim();

            if (!file) {
                this._showError(_t('請先選擇檔案'));
                return;
            }

            if (!width || !height) {
                this._showError(_t('請先輸入寬度、高度'));
                return;
            }

            this._setLoading(true);
            this._resetResult();

            var requestedFilename = fileNameHelper.buildCustomFileName([
                'check',
                width + 'x' + height + 'x1',
            ], file.name);

            var formData = new FormData();
            formData.append('custom_file', file);
            formData.append('filename', requestedFilename);
            formData.append('customer_name', this.$customerName.val().trim());
            formData.append('width', width);
            formData.append('height', height);

            $.ajax({
                url: this.$el.data('check-url'),
                type: 'POST',
                data: formData,
                contentType: false,
                processData: false,
                dataType: 'json',
            }).done(function (response) {
                if (!response.success) {
                    self._showError(response.message || _t('檔案檢測失敗'));
                    self._renderInfo(response.checked_filename, response.image_info || {});
                    return;
                }
                self._showSuccess(response.message || _t('檔案檢測通過'));
                self._renderInfo(response.checked_filename, response.image_info || {});
            }).fail(function (xhr) {
                var message = _t('檔案檢測失敗');
                if (xhr.responseJSON && xhr.responseJSON.message) {
                    message = xhr.responseJSON.message;
                }
                self._showError(message);
            }).always(function () {
                self._setLoading(false);
            });
        },

        _setLoading: function (isLoading) {
            this.$submit.prop('disabled', isLoading);
            this.$submit.text(isLoading ? _t('檢測中...') : _t('檢測檔案'));
        },

        _resetResult: function () {
            this.$error.addClass('d-none').text('');
            this.$success.addClass('d-none').text('');
            this.$info.addClass('d-none');
            this.$info.find('.o_dtsc_ai_checked_filename').text('');
            this.$info.find('.o_dtsc_ai_actual_width_mm').text('-');
            this.$info.find('.o_dtsc_ai_actual_height_mm').text('-');
            this.$info.find('.o_dtsc_ai_actual_pixels').text('-');
            this.$info.find('.o_dtsc_ai_expected_width_mm').text('-');
            this.$info.find('.o_dtsc_ai_expected_height_mm').text('-');
        },

        _showError: function (message) {
            this.$error.removeClass('d-none').text(message);
        },

        _showSuccess: function (message) {
            this.$success.removeClass('d-none').text(message);
        },

        _renderInfo: function (checkedFilename, imageInfo) {
            if (!checkedFilename && !imageInfo) {
                return;
            }

            var expected = imageInfo.filename_size || {};
            var pixelText = '-';
            if (imageInfo.width_px !== undefined && imageInfo.height_px !== undefined) {
                pixelText = imageInfo.width_px + ' x ' + imageInfo.height_px;
            }

            this.$info.removeClass('d-none');
            this.$info.find('.o_dtsc_ai_checked_filename').text(checkedFilename || '-');
            this.$info.find('.o_dtsc_ai_actual_width_mm').text(this._roundMaybe(imageInfo.width_mm));
            this.$info.find('.o_dtsc_ai_actual_height_mm').text(this._roundMaybe(imageInfo.height_mm));
            this.$info.find('.o_dtsc_ai_actual_pixels').text(pixelText);
            this.$info.find('.o_dtsc_ai_expected_width_mm').text(this._roundMaybe(expected.width_mm));
            this.$info.find('.o_dtsc_ai_expected_height_mm').text(this._roundMaybe(expected.height_mm));
        },

        _roundMaybe: function (value) {
            if (value === undefined || value === null || value === '') {
                return '-';
            }
            return Math.round(value * 100) / 100;
        },
    });
});
