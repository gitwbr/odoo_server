odoo.define('dtsc.website_sale_extra_info', function (require) {
    'use strict';

    var core = require('web.core');
    var publicWidget = require('web.public.widget');

    var _t = core._t;

    publicWidget.registry.DtscWebsiteSaleExtraInfo = publicWidget.Widget.extend({
        selector: '.o_dtsc_shop_line_upload, .o_dtsc_shop_extra_info_form',
        events: {
            'click .o_dtsc_upload_btn': '_onClickUpload',
            'click .o_dtsc_cancel_file': '_onClickCancelFile',
            'change .o_dtsc_line_file': '_onChangeFile',
            'submit': '_onSubmit',
        },

        start: function () {
            this._activeUploads = 0;
            this._boundRefreshButtons = this._refreshButtonsAfterPaymentChange.bind(this);
            this._boundPaymentSubmitClick = this._onPaymentSubmitClick.bind(this);
            this._boundPaymentFormSubmit = this._onPaymentFormSubmit.bind(this);
            $(document).on(
                'change.dtscShopUpload',
                'form[name="o_payment_checkout"] input[name="o_payment_radio"]',
                this._boundRefreshButtons
            );
            $(document).on(
                'click.dtscShopUpload',
                'button[name="o_payment_submit_button"]',
                this._boundPaymentSubmitClick
            );
            $(document).on(
                'submit.dtscShopUpload',
                'form[name="o_payment_checkout"]',
                this._boundPaymentFormSubmit
            );
            this._toggleCheckoutButtons();
            return this._super.apply(this, arguments);
        },

        destroy: function () {
            $(document).off(
                'change.dtscShopUpload',
                'form[name="o_payment_checkout"] input[name="o_payment_radio"]',
                this._boundRefreshButtons
            );
            $(document).off(
                'click.dtscShopUpload',
                'button[name="o_payment_submit_button"]',
                this._boundPaymentSubmitClick
            );
            $(document).off(
                'submit.dtscShopUpload',
                'form[name="o_payment_checkout"]',
                this._boundPaymentFormSubmit
            );
            return this._super.apply(this, arguments);
        },

        _onChangeFile: function (ev) {
            var $line = $(ev.currentTarget).closest('.o_dtsc_upload_line');
            var $nameInput = $line.find('.o_dtsc_project_product_name');
            var file = ev.currentTarget.files[0];

            $line.attr('data-file-dirty', file ? '1' : '0');
            $line.find('.o_dtsc_cancel_file').toggleClass('d-none', !file);
            this._setStatus($line, '', '', true);
            this._toggleCheckoutButtons();

            if (file && !$nameInput.val().trim()) {
                var defaultName = $line.data('default-name') || file.name.replace(/\.[^/.]+$/, '');
                $nameInput.val(defaultName);
            }
        },

        _onClickCancelFile: function (ev) {
            ev.preventDefault();
            var $line = $(ev.currentTarget).closest('.o_dtsc_upload_line');
            var $fileInput = $line.find('.o_dtsc_line_file');
            var $progress = $line.find('.uploadProgressBar');

            $fileInput.val('');
            $line.attr('data-file-dirty', '0');
            $(ev.currentTarget).addClass('d-none');
            $progress.hide().val(0);
            this._setStatus($line, '', '', true);
            this._toggleCheckoutButtons();
        },

        _onClickUpload: function (ev) {
            ev.preventDefault();
            var self = this;
            var $button = $(ev.currentTarget);
            var $line = $button.closest('.o_dtsc_upload_line');
            var $fileInput = $line.find('.o_dtsc_line_file');
            var file = $fileInput[0].files[0];

            if (!file) {
                this._setStatus($line, _t('請先選擇檔案'), 'danger');
                return;
            }

            this._activeUploads += 1;
            this._toggleCheckoutButtons();
            $button.prop('disabled', true);
            $line.find('.o_dtsc_cancel_file').prop('disabled', true);

            this._uploadLine($line).always(function () {
                self._activeUploads -= 1;
                self._toggleCheckoutButtons();
                $button.prop('disabled', false);
                $line.find('.o_dtsc_cancel_file').prop('disabled', false);
            });
        },

        _onSubmit: function (ev) {
            if (this._activeUploads > 0) {
                ev.preventDefault();
                window.alert(_t('檔案仍在上傳中，請稍候。'));
                return;
            }

            if (this.$('.o_dtsc_upload_line[data-file-dirty="1"]').length) {
                ev.preventDefault();
                window.alert(_t('有已選擇但尚未上傳的檔案，請先完成上傳。'));
            }
        },

        _uploadLine: function ($line) {
            var self = this;
            var $fileInput = $line.find('.o_dtsc_line_file');
            var $nameInput = $line.find('.o_dtsc_project_product_name');
            var $progress = $line.find('.uploadProgressBar');
            var file = $fileInput[0].files[0];
            var formData = new FormData();

            formData.append('line_id', $line.data('line-id'));
            formData.append('project_product_name', $nameInput.val().trim());
            formData.append('custom_file', file);

            this._setStatus($line, _t('上傳中...'), 'muted');
            $progress.val(0).show();

            return $.ajax({
                url: this.$el.data('upload-url'),
                type: 'POST',
                data: formData,
                contentType: false,
                processData: false,
                dataType: 'json',
                xhr: function () {
                    var xhr = new window.XMLHttpRequest();
                    xhr.upload.addEventListener('progress', function (evt) {
                        if (evt.lengthComputable) {
                            $progress.val((evt.loaded / evt.total) * 100);
                        }
                    }, false);
                    return xhr;
                },
            }).done(function (response) {
                if (!response.success) {
                    self._setStatus($line, response.message || response.error || _t('上傳失敗'), 'danger');
                    return;
                }

                $line.attr('data-file-dirty', '0');
                $line.find('.o_dtsc_cancel_file').addClass('d-none');
                $fileInput.val('');
                $line.find('.o_dtsc_current_filename_text').text(response.filename || _t('已上傳'));
                self._setStatus($line, _t('檔案上傳成功'), 'success');
            }).fail(function (xhr) {
                var message = _t('上傳失敗');
                if (xhr.responseJSON && xhr.responseJSON.message) {
                    message = xhr.responseJSON.message;
                }
                self._setStatus($line, message, 'danger');
            }).always(function () {
                $progress.hide();
            });
        },

        _setStatus: function ($line, message, tone, hidden) {
            var $status = $line.find('.upload-status');

            $status
                .removeClass('d-none text-success text-danger text-muted')
                .addClass('text-' + (tone || 'muted'))
                .text(message || '');

            if (hidden) {
                $status.addClass('d-none').text('');
            }
        },

        _toggleCheckoutButtons: function () {
            var disabled = this._isUploadLocked();
            this.$('.o_dtsc_extra_info_next').prop('disabled', disabled);

            $('button[name="o_payment_submit_button"]').each(function () {
                var $button = $(this);
                if (disabled) {
                    $button
                        .attr('data-dtsc-upload-lock', '1')
                        .prop('disabled', true)
                        .addClass('disabled')
                        .css('pointer-events', 'none');
                } else if ($button.attr('data-dtsc-upload-lock') === '1') {
                    var inPaymentForm = $button.closest('form[name="o_payment_checkout"]').length > 0;
                    var hasSelectedOption = $('form[name="o_payment_checkout"] input[name="o_payment_radio"]:checked').length > 0;
                    $button
                        .removeAttr('data-dtsc-upload-lock')
                        .prop('disabled', inPaymentForm ? !hasSelectedOption : false)
                        .removeClass('disabled')
                        .css('pointer-events', '');
                }
            });
        },

        _refreshButtonsAfterPaymentChange: function () {
            var self = this;
            [0, 50, 150, 300].forEach(function (delay) {
                window.setTimeout(function () {
                    self._toggleCheckoutButtons();
                }, delay);
            });
        },

        _isUploadLocked: function () {
            return this._activeUploads > 0 || this.$('.o_dtsc_upload_line[data-file-dirty="1"]').length > 0;
        },

        _onPaymentSubmitClick: function (ev) {
            if (!this._isUploadLocked()) {
                return;
            }
            ev.preventDefault();
            ev.stopImmediatePropagation();
            window.alert(this._activeUploads > 0 ? _t('檔案仍在上傳中，請稍候。') : _t('有已選擇但尚未上傳的檔案，請先完成上傳。'));
        },

        _onPaymentFormSubmit: function (ev) {
            if (!this._isUploadLocked()) {
                return;
            }
            ev.preventDefault();
            ev.stopImmediatePropagation();
            window.alert(this._activeUploads > 0 ? _t('檔案仍在上傳中，請稍候。') : _t('有已選擇但尚未上傳的檔案，請先完成上傳。'));
        },
    });
});
