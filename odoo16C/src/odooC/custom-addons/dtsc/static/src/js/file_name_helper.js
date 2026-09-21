odoo.define('dtsc.file_name_helper', function (require) {
    'use strict';

    function _getExtension(originalFilename) {
        if (originalFilename && originalFilename.includes('.')) {
            return originalFilename.substring(originalFilename.lastIndexOf('.'));
        }
        return '.unknown';
    }

    function _sanitizeFilename(filename) {
        return (filename || '').replace(/[<>:"/\\|?*\s]/g, '_');
    }

    function _trimFilenameLength(filename, extension, maxLength) {
        if (!filename || filename.length <= maxLength) {
            return filename;
        }
        var ext = extension || '';
        var nameWithoutExt = filename.substring(0, filename.lastIndexOf('.'));
        nameWithoutExt = nameWithoutExt.substring(0, maxLength - ext.length);
        return nameWithoutExt + ext;
    }

    function buildCustomFileName(parts, originalFilename) {
        var cleanParts = (parts || []).filter(function (part) {
            return part !== undefined && part !== null && String(part).trim();
        }).map(function (part) {
            return String(part).trim();
        });

        if (!cleanParts.length) {
            cleanParts.push('unnamed');
        }

        var extension = _getExtension(originalFilename);
        var customFileName = cleanParts.join('-') + extension;
        customFileName = _sanitizeFilename(customFileName);
        customFileName = _trimFilenameLength(customFileName, extension, 200);

        return customFileName;
    }

    return {
        buildCustomFileName: buildCustomFileName,
    };
});
