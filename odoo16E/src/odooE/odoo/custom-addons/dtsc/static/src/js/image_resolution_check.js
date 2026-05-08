odoo.define('dtsc.image_resolution_check', function (require) {
    'use strict';

    var publicWidget = require('web.public.widget');

    var PDF_JS_URL = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js';
    var PDF_WORKER_URL = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    var UTIF_URL = 'https://cdn.jsdelivr.net/npm/utif@3.1.0/UTIF.min.js';
    var DEFAULT_DPI = 72;
    var CM_PER_INCH = 2.54;

    var scriptPromises = {};

    function loadScript(src, globalName) {
        if (globalName && window[globalName]) {
            return Promise.resolve(window[globalName]);
        }
        if (scriptPromises[src]) {
            return scriptPromises[src];
        }

        scriptPromises[src] = new Promise(function (resolve, reject) {
            var script = document.createElement('script');
            script.src = src;
            script.async = true;
            script.onload = function () {
                resolve(globalName ? window[globalName] : true);
            };
            script.onerror = function () {
                reject(new Error('Failed to load ' + src));
            };
            document.head.appendChild(script);
        });
        return scriptPromises[src];
    }

    publicWidget.registry.DtscImageResolutionCheck = publicWidget.Widget.extend({
        selector: '.o_dtsc_resolution_check',
        events: {
            'change .o_resolution_file_input': '_onFileInputChange',
            'input .o_resolution_target_width': '_onTargetWidthInput',
            'dragenter .o_resolution_drop_zone': '_preventDefaults',
            'dragover .o_resolution_drop_zone': '_onDragOver',
            'dragleave .o_resolution_drop_zone': '_onDragLeave',
            'drop .o_resolution_drop_zone': '_onDrop',
            'mousedown .o_resolution_preview_container': '_onPreviewMouseDown',
            'mouseleave .o_resolution_preview_container': '_onPreviewMouseLeave',
            'mouseup .o_resolution_preview_container': '_onPreviewMouseUp',
            'mousemove .o_resolution_preview_container': '_onPreviewMouseMove',
        },

        start: function () {
            this.originalWidthPx = 0;
            this.originalHeightPx = 0;
            this.isDraggingPreview = false;
            this.startX = 0;
            this.startY = 0;
            this.scrollLeft = 0;
            this.scrollTop = 0;

            this.$dropZone = this.$('.o_resolution_drop_zone');
            this.$fileInput = this.$('.o_resolution_file_input');
            this.$targetWidth = this.$('.o_resolution_target_width');
            this.$targetHeight = this.$('.o_resolution_target_height');
            this.$infoBox = this.$('.o_resolution_info_box');
            this.$fileSize = this.$('.o_resolution_file_size');
            this.$originalRes = this.$('.o_resolution_original_res');
            this.$originalCm = this.$('.o_resolution_original_cm');
            this.$dpi = this.$('.o_resolution_dpi');
            this.$loading = this.$('.o_resolution_loading');
            this.$warning = this.$('.o_resolution_warning');
            this.$previewContainer = this.$('.o_resolution_preview_container');
            this.$imagePreview = this.$('.o_resolution_image_preview');

            return this._super.apply(this, arguments);
        },

        _preventDefaults: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        },

        _onDragOver: function (ev) {
            this._preventDefaults(ev);
            this.$dropZone.addClass('dragover');
        },

        _onDragLeave: function (ev) {
            this._preventDefaults(ev);
            this.$dropZone.removeClass('dragover');
        },

        _onDrop: function (ev) {
            this._preventDefaults(ev);
            this.$dropZone.removeClass('dragover');
            var files = ev.originalEvent.dataTransfer && ev.originalEvent.dataTransfer.files;
            if (files && files.length) {
                this._processFile(files[0]);
            }
        },

        _onFileInputChange: function (ev) {
            var file = ev.currentTarget.files && ev.currentTarget.files[0];
            if (file) {
                this._processFile(file);
            }
        },

        _onTargetWidthInput: function () {
            this._updatePreview();
        },

        _processFile: function (file) {
            var self = this;
            this._resetTool();
            this.$loading.show();

            this._readFile(file).then(function () {
                self._displayFileInfo(file);
            }).catch(function (error) {
                console.error(error);
                window.alert('處理檔案時發生錯誤，請確認檔案格式是否正確。');
            }).finally(function () {
                self.$loading.hide();
            });
        },

        _readFile: function (file) {
            var fileType = file.type || '';
            var fileName = (file.name || '').toLowerCase();

            if (fileType === 'application/pdf' || fileName.endsWith('.pdf')) {
                return this._processPDF(file);
            }
            if (fileType.indexOf('tiff') !== -1 || fileName.endsWith('.tif') || fileName.endsWith('.tiff')) {
                return this._processTIFF(file);
            }
            return this._processStandardImage(file);
        },

        _processStandardImage: function (file) {
            var self = this;
            return new Promise(function (resolve, reject) {
                var reader = new FileReader();
                reader.onload = function (ev) {
                    var img = new Image();
                    img.onload = function () {
                        self.originalWidthPx = img.naturalWidth;
                        self.originalHeightPx = img.naturalHeight;
                        self.$imagePreview.attr('src', ev.target.result);
                        resolve();
                    };
                    img.onerror = reject;
                    img.src = ev.target.result;
                };
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
        },

        _processPDF: function (file) {
            var self = this;
            return loadScript(PDF_JS_URL, 'pdfjsLib').then(function (pdfjsLib) {
                pdfjsLib.GlobalWorkerOptions.workerSrc = PDF_WORKER_URL;
                return file.arrayBuffer().then(function (arrayBuffer) {
                    return pdfjsLib.getDocument({data: arrayBuffer}).promise;
                }).then(function (pdf) {
                    return pdf.getPage(1);
                }).then(function (page) {
                    var viewport = page.getViewport({scale: 2.0});
                    var canvas = document.createElement('canvas');
                    var context = canvas.getContext('2d');
                    canvas.height = viewport.height;
                    canvas.width = viewport.width;
                    return page.render({
                        canvasContext: context,
                        viewport: viewport,
                    }).promise.then(function () {
                        self.originalWidthPx = viewport.width;
                        self.originalHeightPx = viewport.height;
                        self.$imagePreview.attr('src', canvas.toDataURL('image/png'));
                    });
                });
            });
        },

        _processTIFF: function (file) {
            var self = this;
            return loadScript(UTIF_URL, 'UTIF').then(function (UTIF) {
                return file.arrayBuffer().then(function (arrayBuffer) {
                    var ifds = UTIF.decode(arrayBuffer);
                    UTIF.decodeImage(arrayBuffer, ifds[0]);
                    var rgba = UTIF.toRGBA8(ifds[0]);
                    var canvas = document.createElement('canvas');
                    canvas.width = ifds[0].width;
                    canvas.height = ifds[0].height;
                    var ctx = canvas.getContext('2d');
                    var imgData = ctx.createImageData(canvas.width, canvas.height);
                    imgData.data.set(rgba);
                    ctx.putImageData(imgData, 0, 0);

                    self.originalWidthPx = ifds[0].width;
                    self.originalHeightPx = ifds[0].height;
                    self.$imagePreview.attr('src', canvas.toDataURL('image/png'));
                });
            });
        },

        _displayFileInfo: function (file) {
            var originalWidthCm = (this.originalWidthPx / DEFAULT_DPI) * CM_PER_INCH;
            var originalHeightCm = (this.originalHeightPx / DEFAULT_DPI) * CM_PER_INCH;

            this.$infoBox.css('display', 'grid');
            this.$fileSize.text((file.size / 1024 / 1024).toFixed(2) + ' MB');
            this.$originalRes.text(this.originalWidthPx + ' x ' + this.originalHeightPx + ' px');
            this.$originalCm.text(originalWidthCm.toFixed(1) + ' x ' + originalHeightCm.toFixed(1) + ' cm');
            this.$dpi.text(DEFAULT_DPI + ' (預設值)');
            this.$targetWidth.val(originalWidthCm.toFixed(1));
            this._updatePreview();
        },

        _updatePreview: function () {
            if (!this.originalWidthPx || !this.$targetWidth.val()) {
                return;
            }

            var targetWidthCm = parseFloat(this.$targetWidth.val());
            if (isNaN(targetWidthCm) || targetWidthCm <= 0) {
                this.$targetHeight.val('');
                return;
            }

            var ratio = this.originalHeightPx / this.originalWidthPx;
            var targetHeightCm = targetWidthCm * ratio;
            var targetWidthPx = (targetWidthCm / CM_PER_INCH) * DEFAULT_DPI;
            var targetHeightPx = (targetHeightCm / CM_PER_INCH) * DEFAULT_DPI;

            this.$targetHeight.val(targetHeightCm.toFixed(2));
            this.$imagePreview.css({
                width: targetWidthPx + 'px',
                height: targetHeightPx + 'px',
            });

            if (targetWidthPx > this.originalWidthPx || targetHeightPx > this.originalHeightPx) {
                this.$warning.show();
            } else {
                this.$warning.hide();
            }
        },

        _resetTool: function () {
            this.originalWidthPx = 0;
            this.originalHeightPx = 0;
            this.$infoBox.hide();
            this.$imagePreview.attr('src', '').css({
                width: '',
                height: '',
            });
            this.$targetWidth.val('');
            this.$targetHeight.val('');
            this.$warning.hide();
            this.$previewContainer.scrollLeft(0);
            this.$previewContainer.scrollTop(0);
        },

        _onPreviewMouseDown: function (ev) {
            this.isDraggingPreview = true;
            this.$previewContainer.addClass('active');
            this.startX = ev.pageX - this.$previewContainer.offset().left;
            this.startY = ev.pageY - this.$previewContainer.offset().top;
            this.scrollLeft = this.$previewContainer.scrollLeft();
            this.scrollTop = this.$previewContainer.scrollTop();
        },

        _onPreviewMouseLeave: function () {
            this.isDraggingPreview = false;
            this.$previewContainer.removeClass('active');
        },

        _onPreviewMouseUp: function () {
            this.isDraggingPreview = false;
            this.$previewContainer.removeClass('active');
        },

        _onPreviewMouseMove: function (ev) {
            if (!this.isDraggingPreview) {
                return;
            }
            ev.preventDefault();
            var x = ev.pageX - this.$previewContainer.offset().left;
            var y = ev.pageY - this.$previewContainer.offset().top;
            this.$previewContainer.scrollLeft(this.scrollLeft - (x - this.startX));
            this.$previewContainer.scrollTop(this.scrollTop - (y - this.startY));
        },
    });
});
