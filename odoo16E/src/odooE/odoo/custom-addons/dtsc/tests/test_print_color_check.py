"""Run directly with python3 -B; no Odoo registry, database or uploads required."""
import ast
import importlib.util
import io
import logging
from pathlib import Path
import unittest

from PIL import Image
try:
    from PyPDF2 import PdfWriter
except ImportError:
    from PyPDF2 import PdfFileWriter as PdfWriter
from PyPDF2.generic import (
    ArrayObject, BooleanObject, DecodedStreamObject, DictionaryObject,
    NameObject, NumberObject,
)

ADDON = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('print_color_check', ADDON / 'utils/print_color_check.py')
COLORS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COLORS)


def dictionary(**values):
    return DictionaryObject({NameObject('/' + key): value for key, value in values.items()})


def stream(data, **values):
    obj = DecodedStreamObject()
    setter = getattr(obj, 'set_data', None) or obj.setData
    setter(data)
    obj.update(dictionary(**values))
    return obj


def pdf(pages):
    writer = PdfWriter()
    add_page = getattr(writer, 'add_blank_page', None) or writer.addBlankPage
    add_object = getattr(writer, '_add_object', None) or writer._addObject
    for content, resources, extras in pages:
        add_page(width=100, height=100)
        page = writer.pages[-1] if hasattr(writer, 'pages') else writer.getPage(writer.getNumPages() - 1)
        page[NameObject('/Contents')] = add_object(stream(content))
        page[NameObject('/Resources')] = resources
        page.update(extras)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image(space, mask=False):
    return stream(b'\x00\x00\x00', Type=NameObject('/XObject'), Subtype=NameObject('/Image'),
                  ColorSpace=space, Width=NumberObject(1), Height=NumberObject(1),
                  BitsPerComponent=NumberObject(8), ImageMask=BooleanObject(mask))


def icc(signature):
    header = bytearray(128)
    header[16:20] = signature
    header[36:40] = b'acsp'
    return ArrayObject([NameObject('/ICCBased'), stream(bytes(header), N=NumberObject(3 if signature == b'RGB ' else 4))])


class ColorChecks(unittest.TestCase):
    def check_pdf(self, content, resources=None, extras=None):
        return COLORS.check_print_colors(pdf([(content, resources or dictionary(), extras or dictionary())]), '.ai')

    def test_raster_modes(self):
        for mode, fmt, blocked in [('RGB', 'JPEG', True), ('CMYK', 'JPEG', False),
                                   ('RGB', 'TIFF', True), ('CMYK', 'TIFF', False),
                                   ('RGBA', 'PNG', True), ('L', 'PNG', False), ('P', 'PNG', True)]:
            with self.subTest(mode=mode, fmt=fmt):
                output = io.BytesIO()
                img = Image.new(mode, (10, 10))
                if mode == 'P':
                    img.putpalette([255, 0, 0] * 256)
                img.save(output, format=fmt)
                self.assertEqual(COLORS.check_print_colors(output.getvalue(), '.' + fmt.lower())['success'], not blocked)

    def test_multipage_tiff_rgb(self):
        output = io.BytesIO()
        Image.new('CMYK', (10, 10)).save(output, format='TIFF', save_all=True,
                                       append_images=[Image.new('RGB', (10, 10))])
        result = COLORS.check_print_colors(output.getvalue(), '.tiff')
        self.assertFalse(result['success'])
        self.assertEqual(result['image_info']['color_mode'], 'RGB/CMYK')

    def test_all_pages_and_mixed_colors(self):
        data = pdf([(b'0 1 0 0 k 0 0 10 10 re f', dictionary(), dictionary()),
                    (b'1 0 0 rg 0 0 10 10 re f', dictionary(), dictionary())])
        result = COLORS.check_print_colors(data, '.pdf')
        self.assertFalse(result['success'])
        self.assertEqual(result['image_info']['rgb_pages'], [2])
        self.assertEqual(result['image_info']['color_mode'], 'RGB/CMYK')

    def test_unused_resources_thumbnail_and_unpainted_rgb(self):
        resources = dictionary(ColorSpace=dictionary(Unused=NameObject('/DeviceRGB')),
                               XObject=dictionary(UnusedImage=image(NameObject('/DeviceRGB'))))
        result = self.check_pdf(b'1 0 0 rg 0 1 0 0 k 0 0 10 10 re f', resources,
                                dictionary(Thumb=image(NameObject('/DeviceRGB'))))
        self.assertTrue(result['success'])

    def test_rgb_image_in_cmyk_page_and_false_image_mask(self):
        resources = dictionary(XObject=dictionary(Im=image(NameObject('/DeviceRGB'))))
        self.assertFalse(self.check_pdf(b'0 1 0 0 k 0 0 10 10 re f /Im Do', resources)['success'])

    def test_indexed_icc_image(self):
        indexed = ArrayObject([NameObject('/Indexed'), icc(b'RGB '), NumberObject(1), NameObject('/Palette')])
        self.assertFalse(self.check_pdf(b'/Im Do', dictionary(XObject=dictionary(Im=image(indexed))))['success'])

    def test_cmyk_icc_and_gray_soft_mask(self):
        obj = image(icc(b'CMYK'))
        obj[NameObject('/SMask')] = image(NameObject('/DeviceGray'))
        self.assertTrue(self.check_pdf(b'/Im Do', dictionary(XObject=dictionary(Im=obj)))['success'])

    def test_spot_rgb_alternate_is_not_rgb_artwork(self):
        spot = ArrayObject([NameObject('/Separation'), NameObject('/SpotRed'),
                            NameObject('/DeviceRGB'), dictionary()])
        self.assertTrue(self.check_pdf(b'/Spot cs 1 scn 0 0 10 10 re f',
                                      dictionary(ColorSpace=dictionary(Spot=spot)))['success'])

    def test_nested_form_and_inherited_graphics_state(self):
        form = stream(b'0 0 10 10 re f', Type=NameObject('/XObject'), Subtype=NameObject('/Form'))
        resources = dictionary(XObject=dictionary(Form=form))
        self.assertFalse(self.check_pdf(b'1 0 0 rg /Form Do', resources)['success'])
        self.assertTrue(self.check_pdf(b'0 1 0 0 k /Form Do', resources)['success'])

    def test_graphics_state_restore(self):
        self.assertTrue(self.check_pdf(b'0 1 0 0 k q 1 0 0 rg Q 0 0 10 10 re f')['success'])

    def test_stroke_text_and_shading(self):
        for content in (b'1 0 0 RG 0 0 10 10 re S', b'1 0 0 rg BT (test) Tj ET'):
            self.assertFalse(self.check_pdf(content)['success'])
        resources = dictionary(Shading=dictionary(Gradient=dictionary(ColorSpace=NameObject('/DeviceRGB'))))
        self.assertFalse(self.check_pdf(b'/Gradient sh', resources)['success'])

    def test_tiling_pattern(self):
        pattern = stream(b'1 0 0 rg 0 0 10 10 re f', PatternType=NumberObject(1), Resources=dictionary())
        resources = dictionary(Pattern=dictionary(P=pattern))
        self.assertFalse(self.check_pdf(b'/Pattern cs /P scn 0 0 10 10 re f', resources)['success'])

    def test_inline_image(self):
        self.assertFalse(self.check_pdf(b'BI /W 1 /H 1 /BPC 8 /CS /RGB ID \xff\x00\x00 EI\n')['success'])

    def test_unknown_preserves_existing_validation(self):
        with self.assertLogs(COLORS._logger, level='WARNING'):
            self.assertEqual(COLORS.check_print_colors(b'not a PDF', '.ai'), {'success': True})
        self.assertEqual(COLORS.check_print_colors(b'<svg/>', '.svg'), {'success': True})

    def test_supplied_ai_files_when_available(self):
        workspace = next((path for path in ADDON.parents if (path / 'temporary/封鎖線_o.ai').is_file()), None)
        if workspace is None:
            self.skipTest('Local customer samples are not present')
        for name, expected in [('封鎖線_o.ai', False), ('壓克力牌印刷 - 估價.ai', True)]:
            with self.subTest(filename=name):
                self.assertEqual(COLORS.check_print_colors((workspace / 'temporary' / name).read_bytes(), '.ai')['success'], expected)


class ControllerOrderChecks(unittest.TestCase):
    def setUp(self):
        # Load only the two pure coordinator methods, without importing Odoo.
        tree = ast.parse((ADDON / 'controllers/upload_ftp.py').read_text())
        methods = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                   and node.name in ('check_image', 'check_multi_artboard_ai')]
        namespace = {'check_print_colors': COLORS.check_print_colors,
                     '_logger': logging.getLogger(__name__)}
        exec(compile(ast.Module(body=methods, type_ignores=[]), '<controller methods>', 'exec'), namespace)
        self.controller = type('Controller', (), {method.name: namespace[method.name] for method in methods})()
        self.calls = []
        self.controller.check_ai_outline_legacy = lambda *args: self.record('outline', {'success': True})
        self.controller.check_image_size = lambda *args, **kwargs: self.record('size', {'success': True, 'image_info': {'width_mm': 100}})
        self.controller.check_is_multi_artboard_ai = lambda *args: self.record('multi', {'success': True, 'image_info': {'page_count': 2}})

    def record(self, name, result):
        self.calls.append(name)
        return result

    def artwork(self, mode):
        return pdf([(b'1 0 0 rg 0 0 10 10 re f' if mode == 'RGB' else b'0 1 0 0 k 0 0 10 10 re f',
                     dictionary(), dictionary())])

    def test_rgb_stops_both_paths_before_other_checks(self):
        self.assertFalse(self.controller.check_image(self.artwork('RGB'), '.ai', 'missing-size.ai')['success'])
        self.assertFalse(self.controller.check_multi_artboard_ai(self.artwork('RGB'), '.ai')['success'])
        self.assertEqual(self.calls, [])

    def test_cmyk_keeps_original_normal_success(self):
        self.assertEqual(self.controller.check_image(self.artwork('CMYK'), '.ai', 'x.ai'),
                         {'success': True, 'width_mm': 100})
        self.assertEqual(self.calls, ['outline', 'size'])

    def test_cmyk_keeps_original_multi_success(self):
        self.assertEqual(self.controller.check_multi_artboard_ai(self.artwork('CMYK'), '.ai'),
                         {'success': True, 'page_count': 2})
        self.assertEqual(self.calls, ['multi', 'outline'])

    def test_existing_errors_are_still_aggregated(self):
        self.controller.check_ai_outline_legacy = lambda *args: self.record('outline', {'success': False, 'errors': ['outline error']})
        self.controller.check_image_size = lambda *args, **kwargs: self.record('size', {'success': False, 'errors': ['size error']})
        result = self.controller.check_image(self.artwork('CMYK'), '.ai', 'x.ai')
        self.assertEqual(result['errors'], ['outline error', 'size error'])
        self.assertEqual(self.calls, ['outline', 'size'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
