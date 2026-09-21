# -*- coding: utf-8 -*-
import base64
import io
import logging

import fitz
import numpy as np
from PIL import Image

_logger = logging.getLogger(__name__)

try:
    import cv2
except ImportError:
    cv2 = None


class AiBlurDetector:
    """Blur / low-resolution detection for `/my/ai-check` only."""

    CONFIG_PREFIX = 'dtsc.ai_blur_check.'
    DEFAULTS = {
        'enabled': 'True',
        'blur_threshold': '80',
        'blur_percentile': '0',
        'tile_size': '64',
        'tile_step': '0',
        'min_texture_threshold': '8',
        'min_nonwhite_ratio': '0.02',
        'min_mean_gray': '20',
        'edge_threshold': '12',
        'min_edge_density': '0',
        'max_blur_findings': '5',
        'max_overlap': '0.35',
        'crop_padding': '40',
        'overlay_alpha': '0.45',
        'morph_kernel_size': '9',
        'max_blur_area_ratio': '5',
        'max_embedded_overlay_coverage': '30',
        'render_dpi': '150',
        'max_render_edge_px': '3200',
        'preview_max_edge_px': '1200',
        'min_embedded_dpi': '72',
        'min_embedded_area_ratio': '1',
    }
    RASTER_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.webp'}
    VECTOR_RENDER_EXTENSIONS = {'.ai', '.pdf'}

    def __init__(self, env):
        self.env = env
        self.params = self._load_params()

    def _load_params(self):
        icp = self.env['ir.config_parameter'].sudo()
        params = {}
        for key, default in self.DEFAULTS.items():
            raw = icp.get_param(f'{self.CONFIG_PREFIX}{key}', default)
            params[key] = raw
        percentile = float(params['blur_percentile'])
        tile_size = int(params['tile_size'])
        tile_step = int(params['tile_step'])
        return {
            'enabled': str(params['enabled']).lower() in ('1', 'true', 'yes', 'on'),
            'blur_threshold': float(params['blur_threshold']),
            'blur_percentile': percentile,
            'use_percentile_cutoff': percentile > 0,
            'tile_size': tile_size,
            'tile_step': tile_step if tile_step > 0 else tile_size,
            'min_texture_threshold': float(params['min_texture_threshold']),
            'min_nonwhite_ratio': float(params['min_nonwhite_ratio']),
            'min_mean_gray': float(params['min_mean_gray']),
            'edge_threshold': float(params['edge_threshold']),
            'min_edge_density': float(params['min_edge_density']),
            'max_blur_findings': int(params['max_blur_findings']),
            'max_overlap': float(params['max_overlap']),
            'crop_padding': int(params['crop_padding']),
            'overlay_alpha': float(params['overlay_alpha']),
            'morph_kernel_size': int(params['morph_kernel_size']),
            'max_blur_area_ratio': float(params['max_blur_area_ratio']),
            'max_embedded_overlay_coverage': float(params['max_embedded_overlay_coverage']),
            'render_dpi': float(params['render_dpi']),
            'max_render_edge_px': int(params['max_render_edge_px']),
            'preview_max_edge_px': int(params['preview_max_edge_px']),
            'min_embedded_dpi': float(params['min_embedded_dpi']),
            'min_embedded_area_ratio': float(params['min_embedded_area_ratio']),
        }

    def validate(self, file_content, file_extension, width_cm='', height_cm=''):
        if not self.params['enabled']:
            return {
                'success': True,
                'message': '',
                'errors': [],
                'blur_check': {'enabled': False, 'skipped': True, 'reason': 'disabled'},
            }

        if cv2 is None:
            _logger.warning('opencv-python 未安裝，跳過模糊檢測')
            return {
                'success': True,
                'message': '',
                'errors': [],
                'blur_check': {
                    'enabled': True,
                    'skipped': True,
                    'reason': 'opencv_not_installed',
                },
            }

        ext = (file_extension or '').lower()
        if ext not in self.RASTER_EXTENSIONS and ext not in self.VECTOR_RENDER_EXTENSIONS:
            return {
                'success': True,
                'message': '',
                'errors': [],
                'blur_check': {
                    'enabled': True,
                    'skipped': True,
                    'reason': 'unsupported_format',
                    'file_extension': ext,
                },
            }

        try:
            if ext in self.VECTOR_RENDER_EXTENSIONS:
                return self._validate_vector(file_content)
            return self._validate_raster(file_content)
        except Exception as exc:
            _logger.exception('模糊檢測失敗: %s', exc)
            return {
                'success': True,
                'message': '',
                'errors': [],
                'blur_check': {
                    'enabled': True,
                    'skipped': True,
                    'reason': 'error',
                    'error': str(exc),
                },
            }

    def _validate_raster(self, file_content):
        image = self._decode_raster_to_bgr(file_content)
        if image is None:
            return {
                'success': True,
                'message': '',
                'errors': [],
                'blur_check': {
                    'enabled': True,
                    'skipped': True,
                    'reason': 'decode_failed',
                },
            }
        return self._finalize_detection(image, embedded_issues=[])

    def _validate_vector(self, file_content):
        doc = fitz.open(stream=file_content, filetype='pdf')
        try:
            if doc.page_count <= 0:
                return self._skip_result('render_failed')

            page = doc[0]
            render_rect = page.rect
            image, render_zoom = self._render_page(page, render_rect)
            if image is None:
                return self._skip_result('render_failed')

            embedded_issues = self._check_embedded_images(doc, page, render_rect, render_zoom)
            return self._finalize_detection(
                image,
                embedded_issues=embedded_issues,
                work_rect=render_rect,
                render_zoom=render_zoom,
            )
        finally:
            doc.close()

    def _skip_result(self, reason):
        return {
            'success': True,
            'message': '',
            'errors': [],
            'blur_check': {'enabled': True, 'skipped': True, 'reason': reason},
        }

    def _finalize_detection(
        self,
        image,
        embedded_issues=None,
        work_rect=None,
        render_zoom=None,
    ):
        embedded_issues = embedded_issues or []
        blur_mask, blur_findings, cutoff, laplacian_stats = self._detect_blur_regions(image)
        blur_area_ratio = laplacian_stats['blur_area_ratio']

        overlay = self._draw_annotations(
            image,
            blur_mask=blur_mask,
            blur_findings=blur_findings,
            embedded_issues=embedded_issues,
            work_rect=work_rect,
            render_zoom=render_zoom,
        )
        preview_overlay, preview_stats = self._build_preview_image(overlay)

        embedded_summary = self._summarize_issues(embedded_issues)
        worst_embedded_dpi = embedded_summary['worst_embedded_dpi']

        laplacian_failed = blur_area_ratio > self.params['max_blur_area_ratio']
        embedded_failed = bool(embedded_issues)
        if embedded_failed and laplacian_failed:
            check_mode = 'both'
        elif laplacian_failed:
            check_mode = 'laplacian'
        elif embedded_failed:
            check_mode = 'embedded_dpi'
        else:
            check_mode = 'none'

        blur_check = {
            'enabled': True,
            'skipped': False,
            'check_mode': check_mode,
            'blur_area_ratio': blur_area_ratio,
            'effective_blur_cutoff': cutoff,
            'blur_findings': [
                {
                    'rank': item['rank'],
                    'x0': item['x0'],
                    'y0': item['y0'],
                    'x1': item['x1'],
                    'y1': item['y1'],
                    'laplacian_var': item['laplacian_var'],
                    'gray_std': item['gray_std'],
                }
                for item in blur_findings
            ],
            'low_dpi_issue_count': embedded_summary['issue_count'],
            'worst_embedded_dpi': worst_embedded_dpi,
            'low_dpi_issues': [
                {
                    'xref': issue['xref'],
                    'width_px': issue['width_px'],
                    'height_px': issue['height_px'],
                    'effective_dpi': issue['effective_dpi'],
                    'coverage_ratio': issue['coverage_ratio'],
                }
                for issue in embedded_issues
            ],
            'avg_score': laplacian_stats['avg_score'],
            'min_score': laplacian_stats['min_score'],
            'tile_count': laplacian_stats['tile_count'],
            'threshold': cutoff if cutoff is not None else self.params['blur_threshold'],
            'min_embedded_dpi': self.params['min_embedded_dpi'],
            'max_blur_area_ratio': self.params['max_blur_area_ratio'],
            'params': dict(self.params),
            'preview_width': preview_stats['width'],
            'preview_height': preview_stats['height'],
            'overlay_image_base64': preview_stats['overlay_image_base64'],
        }

        errors = []
        if laplacian_failed:
            message = (
                '檢測到模糊區域占比 {ratio:.2f}%（允許上限 {limit:.2f}%）。'
                '預覽圖紅色半透明區域標示模糊位置。'
            ).format(
                ratio=blur_area_ratio,
                limit=self.params['max_blur_area_ratio'],
            )
            errors.append(message)
        if embedded_failed:
            worst = embedded_issues[0]
            message = (
                '嵌入位圖解析度不足：{count} 張，最低約 {dpi:.1f} DPI'
                '（要求 ≥ {limit:.0f} DPI）。'
            ).format(
                count=len(embedded_issues),
                dpi=worst['effective_dpi'],
                limit=self.params['min_embedded_dpi'],
            )
            errors.append(message)

        if errors:
            return {
                'success': False,
                'message': errors[0],
                'errors': errors,
                'blur_check': blur_check,
                'image_info': {
                    'blur_area_ratio': blur_area_ratio,
                    'avg_blur_score': laplacian_stats['avg_score'],
                    'min_blur_score': laplacian_stats['min_score'],
                    'worst_embedded_dpi': worst_embedded_dpi,
                },
            }

        return {
            'success': True,
            'message': '',
            'errors': [],
            'blur_check': blur_check,
        }

    def _render_page(self, page, render_rect):
        zoom = self.params['render_dpi'] / 72.0
        target_w = render_rect.width * zoom
        target_h = render_rect.height * zoom
        max_edge = self.params['max_render_edge_px']
        if max(target_w, target_h) > max_edge:
            scale = max_edge / max(target_w, target_h)
            zoom *= scale
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            bgr = cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        elif pix.n == 1:
            bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        else:
            return None, zoom
        render_zoom = pix.width / render_rect.width if render_rect.width > 0 else zoom
        return bgr, render_zoom

    def _check_embedded_images(self, doc, page, render_rect, render_zoom):
        work_area = render_rect.width * render_rect.height
        if work_area <= 0:
            return []

        min_ppi = self.params['min_embedded_dpi']
        min_area = self.params['min_embedded_area_ratio']
        seen_xrefs = set()
        issues = []

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if not xref or xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            try:
                pix = fitz.Pixmap(doc, xref)
                width_px = int(pix.width)
                height_px = int(pix.height)
                pix = None
            except Exception:
                continue

            if width_px < 16 or height_px < 16:
                continue

            for rect in page.get_image_rects(xref):
                if rect.width <= 0 or rect.height <= 0:
                    continue
                intersect = rect & render_rect
                if intersect.is_empty or intersect.width <= 0 or intersect.height <= 0:
                    continue

                coverage_ratio = float(intersect.width * intersect.height / work_area * 100)
                if coverage_ratio < min_area:
                    continue

                visible_w_px = width_px * (intersect.width / rect.width)
                visible_h_px = height_px * (intersect.height / rect.height)
                width_in = intersect.width / 72.0
                height_in = intersect.height / 72.0
                ppi_x = visible_w_px / width_in if width_in > 0 else 0.0
                ppi_y = visible_h_px / height_in if height_in > 0 else 0.0
                effective_dpi = min(ppi_x, ppi_y)

                if effective_dpi >= min_ppi:
                    continue

                issues.append({
                    'xref': xref,
                    'width_px': width_px,
                    'height_px': height_px,
                    'effective_dpi': round(effective_dpi, 1),
                    'coverage_ratio': round(coverage_ratio, 2),
                    'intersect': intersect,
                })
                break

        issues.sort(key=lambda row: (row['coverage_ratio'], -row['effective_dpi']), reverse=True)
        return issues

    def _summarize_issues(self, embedded_issues):
        if not embedded_issues:
            return {
                'placement_ratio': 0.0,
                'issue_count': 0,
                'worst_embedded_dpi': None,
            }
        return {
            'placement_ratio': round(max(issue['coverage_ratio'] for issue in embedded_issues), 2),
            'issue_count': len(embedded_issues),
            'worst_embedded_dpi': min(issue['effective_dpi'] for issue in embedded_issues),
        }

    def _compute_tile_metrics(self, gray_patch):
        lap = cv2.Laplacian(gray_patch, cv2.CV_64F)
        lap_var = float(lap.var())
        gray_std = float(gray_patch.std())
        gray_mean = float(gray_patch.mean())
        nonwhite_ratio = float(np.mean(gray_patch < 245))

        gx = cv2.Sobel(gray_patch, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray_patch, cv2.CV_64F, 0, 1, ksize=3)
        mag = np.sqrt(gx * gx + gy * gy)
        edge_density = float(np.mean(mag > self.params['edge_threshold']))

        return lap_var, gray_std, gray_mean, nonwhite_ratio, edge_density

    def _is_valid_tile(self, gray_std, gray_mean, nonwhite_ratio, edge_density):
        return gray_std >= self.params['min_texture_threshold']

    def _rect_iou(self, rect_a, rect_b):
        ax0, ay0, ax1, ay1 = rect_a
        bx0, by0, bx1, by1 = rect_b
        ix0 = max(ax0, bx0)
        iy0 = max(ay0, by0)
        ix1 = min(ax1, bx1)
        iy1 = min(ay1, by1)
        iw = max(0, ix1 - ix0)
        ih = max(0, iy1 - iy0)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        area_a = max(0, ax1 - ax0) * max(0, ay1 - ay0)
        area_b = max(0, bx1 - bx0) * max(0, by1 - by0)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _detect_blur_regions(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape[:2]
        tile_size = max(16, min(self.params['tile_size'], width, height))
        step = max(tile_size, self.params['tile_step'] or tile_size)

        blur_mask = np.zeros((height, width), dtype=np.uint8)
        scores = []
        tile_records = []

        for y0 in range(0, height, step):
            for x0 in range(0, width, step):
                y1 = min(height, y0 + tile_size)
                x1 = min(width, x0 + tile_size)
                if y1 <= y0 or x1 <= x0:
                    continue
                patch = gray[y0:y1, x0:x1]

                lap_var, gray_std, gray_mean, nonwhite_ratio, edge_density = self._compute_tile_metrics(patch)
                if not self._is_valid_tile(gray_std, gray_mean, nonwhite_ratio, edge_density):
                    continue

                scores.append(lap_var)
                tile_records.append({
                    'rect': (x0, y0, x1, y1),
                    'laplacian_var': lap_var,
                    'gray_std': gray_std,
                })

        stats = {
            'blur_area_ratio': 0.0,
            'avg_score': float(np.mean(scores)) if scores else 0.0,
            'min_score': float(np.min(scores)) if scores else 0.0,
            'tile_count': len(scores),
        }

        if not tile_records:
            return blur_mask, [], self.params['blur_threshold'], stats

        if self.params['use_percentile_cutoff']:
            cutoff = float(np.percentile(np.array(scores, dtype=np.float64), self.params['blur_percentile']))
        else:
            cutoff = self.params['blur_threshold']

        for record in tile_records:
            if record['laplacian_var'] <= cutoff:
                x0, y0, x1, y1 = record['rect']
                blur_mask[y0:y1, x0:x1] = 255

        kernel_size = max(3, self.params['morph_kernel_size'] | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        blur_mask = cv2.morphologyEx(blur_mask, cv2.MORPH_CLOSE, kernel)

        if height and width:
            stats['blur_area_ratio'] = float(np.sum(blur_mask > 0) / (height * width) * 100)

        blur_findings = self._extract_blur_findings(blur_mask, tile_records, cutoff)
        return blur_mask, blur_findings, cutoff, stats

    def _extract_blur_findings(self, blur_mask, tile_records, cutoff):
        if not np.any(blur_mask):
            return []

        contours, _ = cv2.findContours(blur_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        ranked = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w <= 0 or h <= 0:
                continue
            area = w * h
            region_tiles = [
                tile for tile in tile_records
                if tile['laplacian_var'] <= cutoff
                and not (
                    tile['rect'][2] <= x
                    or tile['rect'][0] >= x + w
                    or tile['rect'][3] <= y
                    or tile['rect'][1] >= y + h
                )
            ]
            laplacian_var = min((tile['laplacian_var'] for tile in region_tiles), default=0.0)
            gray_std = min((tile['gray_std'] for tile in region_tiles), default=0.0)
            ranked.append({
                'rect': (x, y, x + w, y + h),
                'laplacian_var': laplacian_var,
                'gray_std': gray_std,
                'area': area,
            })

        ranked.sort(key=lambda item: (item['area'], item['laplacian_var']), reverse=True)

        selected = []
        max_overlap = self.params['max_overlap']
        for candidate in ranked:
            rect = candidate['rect']
            if all(self._rect_iou(rect, item['rect']) <= max_overlap for item in selected):
                selected.append(candidate)
            if len(selected) >= self.params['max_blur_findings']:
                break

        findings = []
        for rank, item in enumerate(selected, start=1):
            x0, y0, x1, y1 = item['rect']
            findings.append({
                'rank': rank,
                'x0': x0,
                'y0': y0,
                'x1': x1,
                'y1': y1,
                'laplacian_var': round(item['laplacian_var'], 2),
                'gray_std': round(item['gray_std'], 2),
            })
        return findings

    def _attach_crop_images(self, image, findings):
        height, width = image.shape[:2]
        padding = self.params['crop_padding']
        for item in findings:
            cx0 = max(0, item['x0'] - padding)
            cy0 = max(0, item['y0'] - padding)
            cx1 = min(width, item['x1'] + padding)
            cy1 = min(height, item['y1'] + padding)
            crop = image[cy0:cy1, cx0:cx1]
            item['crop_image_base64'] = self._encode_image_base64(crop, max_edge=360)

    def _draw_annotations(self, image, blur_mask, blur_findings, embedded_issues, work_rect, render_zoom):
        overlay = image.copy()
        alpha = self.params['overlay_alpha']
        if blur_mask is not None and np.any(blur_mask):
            red = np.array([0, 0, 255], dtype=np.float32)
            mask_bool = blur_mask > 0
            blended = overlay.astype(np.float32)
            blended[mask_bool] = blended[mask_bool] * (1.0 - alpha) + red * alpha
            overlay = blended.astype(np.uint8)

        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = max(0.5, min(image.shape[1], image.shape[0]) / 1800.0)
        thickness = max(1, int(round(scale * 2)))

        for item in blur_findings:
            x0, y0, x1, y1 = item['x0'], item['y0'], item['x1'], item['y1']
            cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 0, 255), 2)

        max_cov = self.params['max_embedded_overlay_coverage']
        if embedded_issues and work_rect is not None and render_zoom:
            for issue in embedded_issues:
                if issue['coverage_ratio'] > max_cov:
                    continue
                x0, y0, x1, y1 = self._rect_to_pixels(
                    issue['intersect'], work_rect, render_zoom, image.shape[:2],
                )
                if x1 <= x0 or y1 <= y0:
                    continue
                cv2.rectangle(overlay, (x0, y0), (x1, y1), (255, 128, 0), 3)
                label = 'LOW PPI %.1f' % issue['effective_dpi']
                self._draw_label(overlay, label, x0, y0, font, scale, thickness, (255, 128, 0))

        return overlay

    def _draw_label(self, image, label, x0, y0, font, scale, thickness, bgr_color):
        (text_w, text_h), _ = cv2.getTextSize(label, font, scale, thickness)
        label_top = max(0, y0 - text_h - 8)
        label_left = max(0, min(x0, image.shape[1] - text_w - 10))
        cv2.rectangle(
            image,
            (label_left, label_top),
            (min(image.shape[1] - 1, label_left + text_w + 10), min(image.shape[0] - 1, label_top + text_h + 8)),
            bgr_color,
            -1,
        )
        cv2.putText(
            image,
            label,
            (label_left + 4, min(image.shape[0] - 4, label_top + text_h + 2)),
            font,
            scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    def _rect_to_pixels(self, rect, work_rect, render_zoom, image_shape):
        height, width = image_shape
        x0 = int(max(0, (rect.x0 - work_rect.x0) * render_zoom))
        y0 = int(max(0, (rect.y0 - work_rect.y0) * render_zoom))
        x1 = int(min(width, round((rect.x1 - work_rect.x0) * render_zoom)))
        y1 = int(min(height, round((rect.y1 - work_rect.y0) * render_zoom)))
        return x0, y0, x1, y1

    def _decode_raster_to_bgr(self, file_content):
        buffer = np.frombuffer(file_content, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if image is not None:
            return image
        with Image.open(io.BytesIO(file_content)) as pil_image:
            rgb = pil_image.convert('RGB')
            array = np.array(rgb)
            return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)

    def _build_preview_image(self, overlay):
        height, width = overlay.shape[:2]
        max_edge = self.params['preview_max_edge_px']
        if max(height, width) > max_edge:
            scale = max_edge / max(height, width)
            new_w = max(1, int(width * scale))
            new_h = max(1, int(height * scale))
            overlay = cv2.resize(overlay, (new_w, new_h), interpolation=cv2.INTER_AREA)

        return overlay, {
            'width': overlay.shape[1],
            'height': overlay.shape[0],
            'overlay_image_base64': self._encode_image_base64(overlay, max_edge=max_edge),
        }

    def _encode_image_base64(self, image, max_edge=1200):
        if image is None or image.size == 0:
            return None
        h, w = image.shape[:2]
        if max(h, w) > max_edge:
            scale = max_edge / max(h, w)
            image = cv2.resize(
                image,
                (max(1, int(w * scale)), max(1, int(h * scale))),
                interpolation=cv2.INTER_AREA,
            )
        success, encoded = cv2.imencode('.png', image)
        if not success:
            return None
        encoded_bytes = encoded.tobytes()
        base64_data = base64.b64encode(encoded_bytes).decode('ascii')
        return 'data:image/png;base64,%s' % base64_data
