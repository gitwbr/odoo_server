# -*- coding: utf-8 -*-
"""Read original artwork colors without rendering or changing the uploaded file.

This is an RGB gate, not a complete PDF/X or spot-color preflight. Unknown
formats/colors keep the existing validation path; only confirmed RGB is blocked.
"""
import io
import logging
import re

import fitz
from PIL import Image
try:
    from PyPDF2 import PdfReader
except ImportError:  # Odoo 16 also supports PyPDF2 1.26.
    from PyPDF2 import PdfFileReader as PdfReader
try:
    from PyPDF2.generic import ContentStream
except ImportError:
    from PyPDF2.pdf import ContentStream

_logger = logging.getLogger(__name__)


def _object(value):
    if hasattr(value, 'get_object'):
        return value.get_object()
    if hasattr(value, 'getObject'):
        return value.getObject()
    return value


def _data(stream):
    return stream.get_data() if hasattr(stream, 'get_data') else stream.getData()


def _true(value):
    # PyPDF2 BooleanObject(False) is truthy on some supported versions.
    return getattr(value, 'value', value) is True


class _PdfColors:
    def __init__(self, reader):
        self.reader = reader
        self.modes = set()
        self.rgb_pages = set()
        self.icc_modes = {}

    def space(self, value, resources, depth=0):
        if depth > 20:
            return {'UNKNOWN'}
        value = _object(value)
        if isinstance(value, str):
            direct = {
                '/DeviceRGB': 'RGB', '/RGB': 'RGB', '/CalRGB': 'RGB',
                '/DeviceCMYK': 'CMYK', '/CMYK': 'CMYK',
                '/DeviceGray': 'GRAY', '/G': 'GRAY', '/CalGray': 'GRAY',
            }
            spaces = _object(resources.get('/ColorSpace', {}))
            default = {'/DeviceRGB': '/DefaultRGB', '/DeviceCMYK': '/DefaultCMYK',
                       '/DeviceGray': '/DefaultGray'}.get(value)
            if default and default in spaces:
                return self.space(spaces[default], resources, depth + 1)
            if value in direct:
                return {direct[value]}
            if value in spaces:
                return self.space(spaces[value], resources, depth + 1)
            return {'UNKNOWN'}
        if isinstance(value, (list, tuple)) and value:
            kind = str(value[0])
            if kind == '/ICCBased':
                profile = _object(value[1])
                key = id(profile)
                if key not in self.icc_modes:
                    header = _data(profile)[:128]
                    self.icc_modes[key] = ({b'RGB ': 'RGB', b'CMYK': 'CMYK',
                                            b'GRAY': 'GRAY'}.get(header[16:20], 'UNKNOWN')
                                           if header[36:40] == b'acsp' else 'UNKNOWN')
                return {self.icc_modes[key]}
            if kind in ('/Indexed', '/I'):
                return self.space(value[1], resources, depth + 1)
            if kind == '/Pattern':
                return self.space(value[1], resources, depth + 1) if len(value) > 1 else set()
            if kind in ('/Separation', '/DeviceN'):
                # A spot color is not RGB merely because its preview alternate is RGB.
                return {'SPOT'}
            return self.space(kind, resources, depth + 1)
        return {'UNKNOWN'}

    def record(self, modes, page_number):
        self.modes.update(modes)
        if 'RGB' in modes:
            self.rgb_pages.add(page_number)

    def paint(self, color, resources, page_number, depth):
        space, pattern_name = color
        self.record(self.space(space, resources), page_number)
        if pattern_name:
            patterns = _object(resources.get('/Pattern', {}))
            pattern = _object(patterns.get(pattern_name))
            if not pattern:
                self.modes.add('UNKNOWN')
            elif pattern.get('/PatternType') == 1:
                self.scan(pattern, _object(pattern.get('/Resources', resources)),
                          page_number, depth + 1)
            elif pattern.get('/PatternType') == 2:
                shading = _object(pattern.get('/Shading', {}))
                self.record(self.space(shading.get('/ColorSpace'), resources), page_number)

    def scan(self, stream, resources, page_number, depth=0, initial_state=None):
        if depth > 20:
            self.modes.add('UNKNOWN')
            return
        if stream is None:
            return
        state = dict(initial_state or {
            'fill': ('/DeviceGray', None), 'stroke': ('/DeviceGray', None), 'text': 0,
        })
        stack = []
        for operands, operator in ContentStream(_object(stream), self.reader).operations:
            if operator == b'q':
                stack.append(dict(state))
            elif operator == b'Q':
                if stack:
                    state = stack.pop()
            elif operator in (b'cs', b'CS'):
                state['fill' if operator == b'cs' else 'stroke'] = (operands[0], None)
            elif operator in (b'rg', b'RG', b'k', b'K', b'g', b'G'):
                space = {b'rg': '/DeviceRGB', b'k': '/DeviceCMYK', b'g': '/DeviceGray'}[operator.lower()]
                state['fill' if operator.islower() else 'stroke'] = (space, None)
            elif operator in (b'scn', b'SCN'):
                key = 'fill' if operator == b'scn' else 'stroke'
                pattern = operands[-1] if operands and str(operands[-1]).startswith('/') else None
                state[key] = (state[key][0], pattern)
            elif operator in (b'f', b'F', b'f*', b'S', b's', b'B', b'B*', b'b', b'b*'):
                if operator not in (b'S', b's'):
                    self.paint(state['fill'], resources, page_number, depth)
                if operator not in (b'f', b'F', b'f*'):
                    self.paint(state['stroke'], resources, page_number, depth)
            elif operator == b'Tr':
                state['text'] = int(operands[0])
            elif operator in (b'Tj', b'TJ', b"'", b'"'):
                if state['text'] in (0, 2, 4, 6):
                    self.paint(state['fill'], resources, page_number, depth)
                if state['text'] in (1, 2, 5, 6):
                    self.paint(state['stroke'], resources, page_number, depth)
            elif operator == b'Do':
                obj = _object(_object(resources.get('/XObject', {})).get(operands[0]))
                if obj is None:
                    self.modes.add('UNKNOWN')
                elif obj.get('/Subtype') == '/Form':
                    self.scan(obj, _object(obj.get('/Resources', resources)),
                              page_number, depth + 1, state)
                elif obj.get('/Subtype') == '/Image':
                    if _true(obj.get('/ImageMask')):
                        self.paint(state['fill'], resources, page_number, depth)
                    else:
                        self.record(self.space(obj.get('/ColorSpace'), resources), page_number)
                    # /SMask is opacity, not an additional artwork color space.
            elif operator == b'sh':
                shading = _object(_object(resources.get('/Shading', {})).get(operands[0], {}))
                self.record(self.space(shading.get('/ColorSpace'), resources), page_number)
            elif operator == b'INLINE IMAGE':
                settings = operands['settings']
                if _true(settings.get('/IM')) or _true(settings.get('/ImageMask')):
                    self.paint(state['fill'], resources, page_number, depth)
                else:
                    self.record(self.space(settings.get('/CS', settings.get('/ColorSpace')), resources), page_number)


def check_print_colors(file_content, file_extension):
    """Return the existing controller error shape only when RGB is confirmed."""
    extension = (file_extension or '').lower()
    modes = set()
    rgb_pages = set()
    try:
        if extension in ('.ai', '.pdf'):
            reader = PdfReader(io.BytesIO(file_content), strict=False)
            inspector = _PdfColors(reader)
            modes = inspector.modes
            rgb_pages = inspector.rgb_pages
            for number, page in enumerate(reader.pages, 1):
                try:
                    inspector.scan(page.get('/Contents'), _object(page.get('/Resources', {})), number)
                except Exception:
                    modes.add('UNKNOWN')
                    _logger.warning('第 %s 頁色彩檢查未完成，保留原有檢測流程', number, exc_info=True)
                    # PyPDF2 1.26 cannot parse some valid inline-image endings.
                    # Recover original image spaces with the existing PDF library;
                    # never use a rendered RGB preview to infer source colors.
                    try:
                        with fitz.open(stream=file_content, filetype='pdf') as doc:
                            for info in doc[number - 1].get_image_info():
                                name = info.get('cs-name', '')
                                if re.search(r'(?:^|[,(])(?:DeviceRGB|CalRGB|RGB)(?:$|[,)])', name):
                                    inspector.record({'RGB'}, number)
                    except Exception:
                        _logger.warning('第 %s 頁無法補充讀取圖片色彩', number, exc_info=True)
        elif extension == '.svg':
            modes.add('UNKNOWN')
        else:
            with Image.open(io.BytesIO(file_content)) as img:
                for index in range(getattr(img, 'n_frames', 1)):
                    img.seek(index)
                    mode = img.mode
                    if mode in ('P', 'PA') and img.palette:
                        mode = img.palette.mode
                    if mode in ('RGB', 'RGBA', 'RGBX', 'RGBa', 'YCbCr'):
                        modes.add('RGB')
                    elif mode == 'CMYK':
                        modes.add('CMYK')
                    elif mode in ('1', 'L', 'LA', 'I', 'F') or mode.startswith('I;16'):
                        modes.add('GRAY')
                    else:
                        modes.add('UNKNOWN')
    except Exception:
        modes.add('UNKNOWN')
        _logger.warning('無法完整判斷原檔色彩，保留原有檢測流程', exc_info=True)

    if 'RGB' not in modes:
        return {'success': True}

    mixed = 'CMYK' in modes
    message = ('檔案同時包含 RGB 與 CMYK 色彩，暫時無法上傳。' if mixed else
               '檔案含有 RGB 色彩，暫時無法上傳。')
    if rgb_pages:
        message += ' RGB 內容位於第 %s 頁／畫板。' % '、'.join(map(str, sorted(rgb_pages)))
    return {
        'success': False, 'error': message, 'errors': [message],
        'image_info': {'color_mode': 'RGB/CMYK' if mixed else 'RGB',
                       'color_spaces': sorted(modes), 'rgb_pages': sorted(rgb_pages)},
    }
