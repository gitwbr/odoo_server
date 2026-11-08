# -*- coding: utf-8 -*-
"""PDF 相容 AI / PDF → 印刷 TIFF（對位條 + 檔名標記）。

不依賴 Illustrator：僅讀 PDF 相容內容。不相容檔案請先重新另存。
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass

CM = 72 / 2.54  # pt per cm

# 對位規格（由原軟體輸出量測）
BAND_CM = 0.705
DOT_D_CM = 0.5
DOT_NEAR_CM = 1.35
DOT_FAR_CM = 3.35
LABEL_GAP_CM = 1.0
FONT_SIZE = 14.2
FRAME_W_CM = 0.034
MAX_PIXELS = 300_000_000  # 與原軟體「3 億像素上限」對齊

K100 = (0, 0, 0, 1)
DOT_COLOR = (0.6, 0, 0, 1)  # C60 K100
RED = (0, 1, 1, 0.3)  # M100 Y100 K30 ≈ 紅字
FRAME_COLOR = (1, 0, 0, 0.3)  # C100 K30

_NO_PDF_HINT = "未附帶 PDF 內容"
_LABEL_RE = re.compile(r"^(\d+)\-([0-9]+[a-zA-Z]?)", re.I)
# PDF DeviceCMYK：`c m y k k/K`
_CMYK_OP_RE = re.compile(
    rb"([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s+[kK]\b"
)


@dataclass
class AiInspectResult:
    ok: bool
    pdf_compatible: bool
    page_count: int = 0
    width_cm: float = 0.0
    height_cm: float = 0.0
    message: str = ""


# 對位點所在邊：tb=上下, lr=左右
REGMARK_SIDE_AUTO = "auto"
REGMARK_SIDE_LONG = "long"
REGMARK_SIDE_SHORT = "short"
REGMARK_SIDE_TB = "tb"
REGMARK_SIDE_LR = "lr"
CUTTER_LENGTH_CM = 240.0  # 原軟體自動判斷門檻


@dataclass
class PrepressOptions:
    dpi: int = 100  # 輸入框解析度；手動必用，自動時作過大時後備
    dpi_mode: str = "auto"  # auto / manual（對應原軟體「自動判斷」/「手動, 拼檔」）
    bleed_cm: float = 0.0
    expand_ltrb: tuple = (0.0, 0.0, 0.0, 0.0)  # left, top, right, bottom cm
    add_regmarks: bool = True  # 對位圓點（裁切標記）
    add_filename_label: bool = True  # ↑單號檔名標記
    add_frame: bool = True
    mirror_h: bool = False
    # auto / long / short / tb / lr
    regmark_side: str = REGMARK_SIDE_AUTO
    label_name: str = ""
    label_seq: str = ""
    # art=ARTOPTIMIZED / type=TYPEOPTIMIZED / none=不處理（對齊原軟體消除鋸齒）
    aa_mode: str = "art"
    max_pixels: int = MAX_PIXELS


def resolve_aa_level(aa_mode: str) -> int:
    """對應原軟體消除鋸齒 → MuPDF set_aa_level（0–8）。

    Illustrator 的 ART/TYPE 優化無法在 MuPDF 完全分開，以強度近似：
    art=8（柔和線條）、type=4（較銳利）、none=0。
    """
    mode = (aa_mode or "art").strip().lower()
    if mode in ("none", "off", "0", "no"):
        return 0
    if mode in ("type", "typeoptimized", "text"):
        return 4
    return 8


def _cmyk_float_to_bytes_floor(cmyk: tuple) -> tuple:
    return tuple(int(max(0.0, min(1.0, float(x))) * 255) for x in cmyk)


def _cmyk_float_to_bytes_round(cmyk: tuple) -> tuple:
    """與 Illustrator 一致：四捨五入到 0–255。"""
    return tuple(int(max(0.0, min(1.0, float(x))) * 255 + 0.5) for x in cmyk)


def _iter_pdf_stream_xrefs(doc, xref: int, seen: set | None = None):
    """遞迴收集 page / Form XObject 的 stream xref。"""
    seen = seen if seen is not None else set()
    if not xref or xref in seen:
        return
    seen.add(xref)
    yield xref
    try:
        obj = doc.xref_object(xref) or ""
    except Exception:
        return
    # /XObject << /Fm0 12 0 R ... >>
    for m in re.finditer(r"/([A-Za-z0-9._\-]+)\s+(\d+)\s+0\s+R", obj):
        kid = int(m.group(2))
        try:
            subtype = (doc.xref_get_key(kid, "Subtype") or ("", ""))[1]
        except Exception:
            subtype = ""
        if "Form" in subtype or "XObject" in (doc.xref_get_key(kid, "Type") or ("", ""))[1]:
            yield from _iter_pdf_stream_xrefs(doc, kid, seen)


def extract_device_cmyk_colors(doc) -> set:
    """從 PDF 內容流抽出 DeviceCMYK（含 Form XObject）。"""
    colors = set()
    xrefs = set()
    for page in doc:
        # 合併後的內容 + 各 XObject
        try:
            raw = page.read_contents() or b""
        except Exception:
            raw = b""
        for m in _CMYK_OP_RE.finditer(raw):
            colors.add(tuple(float(m.group(i)) for i in range(1, 5)))
        try:
            for xref, _name, *_rest in page.get_xobjects():
                xrefs.add(int(xref))
        except Exception:
            pass
        try:
            # page 物件上的 Contents
            page_xref = page.xref
            for xref in _iter_pdf_stream_xrefs(doc, page_xref):
                xrefs.add(xref)
        except Exception:
            pass

    for xref in list(xrefs):
        for kid in _iter_pdf_stream_xrefs(doc, xref):
            try:
                stream = doc.xref_stream(kid) or b""
            except Exception:
                continue
            for m in _CMYK_OP_RE.finditer(stream):
                colors.add(tuple(float(m.group(i)) for i in range(1, 5)))
    return colors


def build_cmyk_round_fix_map(colors) -> dict:
    """MuPDF 對 c*255 採截斷；Illustrator 採四捨五入。建立 floor→round 對照。"""
    mapping = {}
    for cmyk in colors or ():
        if not cmyk or len(cmyk) != 4:
            continue
        flo = _cmyk_float_to_bytes_floor(cmyk)
        rnd = _cmyk_float_to_bytes_round(cmyk)
        if flo != rnd:
            mapping[flo] = rnd
    return mapping


def apply_cmyk_round_fix(im, mapping: dict):
    """把實色塊的截斷值改成四捨五入值（抗鋸齒邊緣非整色，不會被誤改）。"""
    if not mapping:
        return im, 0
    try:
        import numpy as np
    except ImportError:
        # 無 numpy 時逐像素（大圖較慢，僅後備）
        px = im.load()
        w, h = im.size
        changed = 0
        for y in range(h):
            for x in range(w):
                t = px[x, y]
                nxt = mapping.get(t)
                if nxt is not None:
                    px[x, y] = nxt
                    changed += 1
        return im, changed

    arr = np.array(im)
    if arr.ndim != 3 or arr.shape[2] < 4:
        return im, 0
    changed = 0
    for flo, rnd in mapping.items():
        mask = (
            (arr[:, :, 0] == flo[0])
            & (arr[:, :, 1] == flo[1])
            & (arr[:, :, 2] == flo[2])
            & (arr[:, :, 3] == flo[3])
        )
        n = int(mask.sum())
        if not n:
            continue
        arr[mask] = rnd
        changed += n
    ImageMod = _require_pil()
    out = ImageMod.fromarray(arr, mode="CMYK")
    return out, changed


def resolve_regmark_axis(width_cm: float, height_cm: float, side_mode: str) -> str:
    """依畫面尺寸與選項，回傳 'tb'（上下）或 'lr'（左右）。"""
    mode = (side_mode or REGMARK_SIDE_AUTO).strip().lower()
    if mode in (REGMARK_SIDE_TB, "top_bottom", "上下"):
        return "tb"
    if mode in (REGMARK_SIDE_LR, "left_right", "左右"):
        return "lr"

    # 畫面：寬>=高 → 長邊=上下、短邊=左右；否則相反
    long_axis = "tb" if width_cm >= height_cm else "lr"
    short_axis = "lr" if long_axis == "tb" else "tb"

    if mode in (REGMARK_SIDE_LONG, "長邊"):
        return long_axis
    if mode in (REGMARK_SIDE_SHORT, "短邊"):
        return short_axis

    # 自動：Length+(點徑x2) ≤ 240cm → 短邊，否則長邊
    # Length 取畫面較長邊（進刀方向常見參考）
    length = max(width_cm, height_cm)
    if length + (DOT_D_CM * 2) <= CUTTER_LENGTH_CM:
        return short_axis
    return long_axis


def _require_fitz():
    try:
        import fitz  # noqa: F401
        return fitz
    except ImportError as err:
        raise RuntimeError("伺服器未安裝 PyMuPDF（fitz），無法處理 AI/PDF。") from err


def _require_pil():
    try:
        from PIL import Image  # noqa: F401
        return Image
    except ImportError as err:
        raise RuntimeError("伺服器未安裝 Pillow，無法輸出 TIFF。") from err


def inspect_ai_bytes(raw: bytes) -> AiInspectResult:
    """檢查是否為可讀的 PDF 相容 AI / PDF，並回傳工作區域尺寸。"""
    fitz = _require_fitz()
    if not raw:
        return AiInspectResult(False, False, message="檔案內容為空。")
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as err:
        return AiInspectResult(
            False, False,
            message="無法開啟檔案（可能不是 PDF 相容 AI，或檔案損壞）：%s" % err,
        )
    try:
        if doc.page_count < 1:
            return AiInspectResult(False, False, message="檔案沒有頁面。")
        page = doc[0]
        text = (page.get_text() or "").strip()
        drawings = page.get_drawings()
        images = page.get_images()
        # Illustrator 未勾「建立 PDF 相容檔案」時，內容只有提示文字
        if _NO_PDF_HINT in text and not drawings and not images:
            return AiInspectResult(
                False, False,
                page_count=doc.page_count,
                width_cm=page.rect.width / CM,
                height_cm=page.rect.height / CM,
                message=(
                    "此 AI 檔未建立 PDF 相容內容。請在 Illustrator 另存時勾選"
                    "「建立 PDF 相容檔案」，或改存為 PDF 後再上傳。"
                ),
            )
        if not drawings and not images and not text:
            return AiInspectResult(
                False, False,
                page_count=doc.page_count,
                message="檔案頁面沒有可輸出的圖稿內容。",
            )
        return AiInspectResult(
            True, True,
            page_count=doc.page_count,
            width_cm=round(page.rect.width / CM, 4),
            height_cm=round(page.rect.height / CM, 4),
            message="PDF 相容，可進行印前處理。",
        )
    finally:
        doc.close()


def parse_label_from_filename(filename: str):
    """從檔名解析標記，例如 101-01-16x22-....ai → ('101', '01')。"""
    if not filename:
        return "", ""
    base = filename.rsplit("/", 1)[-1]
    base = base.rsplit(".", 1)[0]
    m = _LABEL_RE.match(base)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def parse_expand_ltrb(text: str):
    """解析「左,上,右,下」(cm)。空值或 0,0,0,0 表示不延伸；單一數字表示四邊同值。"""
    text = (text or "").strip()
    if not text:
        return (0.0, 0.0, 0.0, 0.0)
    parts = [p.strip() for p in text.replace("，", ",").split(",") if p.strip() != ""]
    if len(parts) == 1:
        v = float(parts[0])
        return (v, v, v, v)
    if len(parts) != 4:
        raise ValueError("延伸尺寸請輸入「左,上,右,下」四個值（cm），或單一數字。")
    return tuple(float(p) for p in parts)


def choose_dpi(
    width_cm: float,
    height_cm: float,
    preferred: int = 100,
    max_pixels: int = MAX_PIXELS,
    mode: str = "auto",
) -> int:
    """對齊原軟體「輸入轉檔 解析度」：

    - 手動, 拼檔：全部依輸入 dpi
    - 自動判斷：依頁面尺寸估適合 dpi；尺寸/像素過大則改用輸入 dpi
    """
    w_in = max(width_cm, 0.01) / 2.54
    h_in = max(height_cm, 0.01) / 2.54
    area = w_in * h_in
    input_dpi = int(preferred) if preferred and preferred > 0 else 100

    if (mode or "auto").strip().lower() == "manual":
        dpi = input_dpi
    else:
        # 小圖約 300，大圖依像素上限自動降
        max_dpi = int(math.sqrt(max_pixels / area)) if area else 300
        dpi = min(300, max(72, max_dpi))
        # 尺寸或像素仍過大 → 改用輸入框解析度（原軟體說明）
        if (w_in * dpi) * (h_in * dpi) > max_pixels:
            dpi = input_dpi

    while dpi > 72 and (w_in * dpi) * (h_in * dpi) > max_pixels:
        dpi -= 1
    return max(1, dpi)


def _draw_label(page, fitz, x, baseline, name, seq):
    arrow_w, arrow_h = 0.195 * CM, 0.39 * CM
    cx = x + arrow_w / 2
    top = baseline - arrow_h
    page.draw_line((cx, baseline), (cx, top + arrow_h * 0.3), color=K100, width=0.09 * CM)
    page.draw_polyline(
        [(x, top + arrow_h * 0.35), (cx, top), (x + arrow_w, top + arrow_h * 0.35)],
        color=K100, fill=K100, closePath=True, width=0,
    )
    tx = x + arrow_w + 0.02 * CM
    page.insert_text((tx, baseline), "%s-" % name, fontname="helv", fontsize=FONT_SIZE, color=K100)
    tx += fitz.get_text_length("%s-" % name, fontname="helv", fontsize=FONT_SIZE)
    page.insert_text((tx, baseline), seq, fontname="helv", fontsize=FONT_SIZE, color=RED)


def _label_width(fitz, name, seq):
    return 0.215 * CM + fitz.get_text_length("%s-%s" % (name, seq), fontname="helv", fontsize=FONT_SIZE)


def _mid_regmark_xs(width_pt: float):
    """寬幅加中間點：每排最多再加偏離中心約 1cm 的點（>80cm 時）。"""
    width_cm = width_pt / CM
    if width_cm < 80:
        return []
    # 與樣本 120cm 對齊：中點偏離中心約 1cm
    mid = width_pt / 2
    return [mid + 1.0 * CM]


def build_print_pdf(raw: bytes, options: PrepressOptions):
    """組裝帶對位條的 PDF（記憶體中），回傳 (fitz.Document, content_w_cm, content_h_cm)。"""
    fitz = _require_fitz()
    inspect = inspect_ai_bytes(raw)
    if not inspect.pdf_compatible:
        raise ValueError(inspect.message or "AI 檔不相容 PDF。")

    src = fitz.open(stream=raw, filetype="pdf")
    try:
        sp = src[0]
        left, top, right, bottom = options.expand_ltrb
        # 延伸工作區域：在外圍補白，再把原頁放到偏移位置
        content_w = sp.rect.width + (left + right) * CM
        content_h = sp.rect.height + (top + bottom) * CM
        if options.bleed_cm > 0:
            # 出血：擴大裁切範圍（對稱）
            b = options.bleed_cm * CM
            content_w += 2 * b
            content_h += 2 * b
            left += options.bleed_cm
            top += options.bleed_cm

        need_band = bool(options.add_regmarks or options.add_filename_label)
        band = BAND_CM * CM if need_band else 0.0
        axis = resolve_regmark_axis(
            content_w / CM, content_h / CM, options.regmark_side
        ) if need_band else "tb"

        if axis == "lr":
            page_w, page_h = content_w + 2 * band, content_h
            art_x, art_y = band, 0.0
        else:
            page_w, page_h = content_w, content_h + 2 * band
            art_x, art_y = 0.0, band

        out = fitz.open()
        page = out.new_page(width=page_w, height=page_h)

        # 白底
        page.draw_rect(page.rect, color=None, fill=(0, 0, 0, 0), width=0)

        dest = fitz.Rect(
            art_x + left * CM,
            art_y + top * CM,
            art_x + left * CM + sp.rect.width,
            art_y + top * CM + sp.rect.height,
        )
        page.show_pdf_page(dest, src, 0)

        if options.mirror_h:
            Image = _require_pil()
            clip = fitz.Rect(art_x, art_y, art_x + content_w, art_y + content_h)
            pix = page.get_pixmap(clip=clip, dpi=72, colorspace=fitz.csCMYK, alpha=False)
            im = Image.frombytes("CMYK", (pix.width, pix.height), pix.samples)
            im = im.transpose(Image.FLIP_LEFT_RIGHT)
            buf = io.BytesIO()
            im.save(buf, format="TIFF", compression="tiff_lzw")
            page.draw_rect(clip, color=None, fill=(0, 0, 0, 0), width=0)
            page.insert_image(clip, stream=buf.getvalue())

        if need_band:
            _draw_regmark_bands(
                page, fitz, options, axis=axis,
                content_w=content_w, content_h=content_h, band=band,
                page_w=page_w, page_h=page_h,
            )

        if options.add_frame:
            fw = FRAME_W_CM * CM
            page.draw_rect(
                fitz.Rect(fw / 2, fw / 2, page_w - fw / 2, page_h - fw / 2),
                color=FRAME_COLOR, width=fw,
            )

        return out, page_w / CM, page_h / CM
    finally:
        src.close()


def _draw_regmark_bands(page, fitz, options, axis, content_w, content_h, band, page_w, page_h):
    """在上下或左右白邊繪製對位點與檔名標記。"""
    r = DOT_D_CM * CM / 2
    name = options.label_name or "00"
    seq = options.label_seq or "01"
    baseline_off = 0.544 * CM - band / 2

    if axis == "tb":
        top_y, bot_y = band / 2, page_h - band / 2
        # 上下錯位：上排左遠右近、下排左近右遠（防轉向）
        top_a = DOT_FAR_CM * CM
        top_b = content_w - DOT_NEAR_CM * CM
        bot_a = DOT_NEAR_CM * CM
        bot_b = content_w - DOT_FAR_CM * CM
        if options.add_regmarks:
            top_xs = [top_a, top_b] + _mid_regmark_xs(content_w)
            bot_xs = [bot_a, bot_b] + [x - 2.0 * CM for x in _mid_regmark_xs(content_w)]
            for y, xs in ((top_y, top_xs), (bot_y, bot_xs)):
                for x in xs:
                    page.draw_circle((x, y), r, color=None, fill=DOT_COLOR, width=0)
        if options.add_filename_label:
            _draw_label(page, fitz, top_a + r + LABEL_GAP_CM * CM, top_y + baseline_off, name, seq)
            lw = _label_width(fitz, name, seq)
            _draw_label(page, fitz, bot_b - r - LABEL_GAP_CM * CM - lw, bot_y + baseline_off, name, seq)
        return

    # 左右：錯位規則同上下（一側近、一側遠）
    left_x, right_x = band / 2, page_w - band / 2
    left_a = DOT_FAR_CM * CM
    left_b = content_h - DOT_NEAR_CM * CM
    right_a = DOT_NEAR_CM * CM
    right_b = content_h - DOT_FAR_CM * CM
    if options.add_regmarks:
        left_ys = [left_a, left_b] + _mid_regmark_xs(content_h)
        right_ys = [right_a, right_b] + [y - 2.0 * CM for y in _mid_regmark_xs(content_h)]
        for x, ys in ((left_x, left_ys), (right_x, right_ys)):
            for y in ys:
                page.draw_circle((x, y), r, color=None, fill=DOT_COLOR, width=0)
    if options.add_filename_label:
        # 左右邊用直書文字框
        label = "↑%s-%s" % (name, seq)
        left_box = fitz.Rect(2, left_a + r + LABEL_GAP_CM * CM, band - 2, left_b)
        right_box = fitz.Rect(page_w - band + 2, right_a + r + LABEL_GAP_CM * CM, page_w - 2, right_b)
        if left_box.height > 8:
            page.insert_textbox(left_box, label, fontsize=FONT_SIZE, fontname="helv",
                                color=K100, rotate=90, align=1)
        if right_box.height > 8:
            page.insert_textbox(right_box, label, fontsize=FONT_SIZE, fontname="helv",
                                color=K100, rotate=90, align=1)


def convert_ai_to_tiff_bytes(raw: bytes, options: PrepressOptions | None = None) -> tuple[bytes, dict]:
    """AI/PDF → CMYK LZW TIFF bytes。

    :return: (tiff_bytes, meta) meta 含 dpi/width_cm/height_cm/width_px/height_px
    """
    fitz = _require_fitz()
    Image = _require_pil()
    options = options or PrepressOptions()

    doc, w_cm, h_cm = build_print_pdf(raw, options)
    try:
        dpi = choose_dpi(
            w_cm,
            h_cm,
            preferred=options.dpi,
            max_pixels=options.max_pixels,
            mode=options.dpi_mode,
        )
        aa_level = resolve_aa_level(options.aa_mode)
        prev_aa = None
        try:
            try:
                prev_aa = fitz.TOOLS.show_aa_level()
            except Exception:
                prev_aa = None
            fitz.TOOLS.set_aa_level(aa_level)
            pix = doc[0].get_pixmap(
                dpi=dpi,
                colorspace=fitz.csCMYK,
                alpha=False,
                annots=False,
            )
        finally:
            if prev_aa is not None:
                try:
                    if isinstance(prev_aa, dict):
                        fitz.TOOLS.set_aa_level(int(prev_aa.get("graphics", 8)))
                    elif isinstance(prev_aa, (list, tuple)):
                        fitz.TOOLS.set_aa_level(int(prev_aa[0]))
                    else:
                        fitz.TOOLS.set_aa_level(int(prev_aa))
                except Exception:
                    fitz.TOOLS.set_aa_level(8)
        im = Image.frombytes("CMYK", (pix.width, pix.height), pix.samples)
        # 對齊 Illustrator：DeviceCMYK 實色由截斷改為四捨五入（例 M70% 178→179）
        try:
            fix_map = build_cmyk_round_fix_map(extract_device_cmyk_colors(doc))
        except Exception:
            fix_map = {}
        im, cmyk_fixed = apply_cmyk_round_fix(im, fix_map)
        buf = io.BytesIO()
        im.save(buf, format="TIFF", compression="tiff_lzw", dpi=(dpi, dpi))
        meta = {
            "dpi": dpi,
            "width_cm": round(w_cm, 4),
            "height_cm": round(h_cm, 4),
            "width_px": pix.width,
            "height_px": pix.height,
            "aa_mode": options.aa_mode,
            "aa_level": aa_level,
            "cmyk_round_fixed_px": cmyk_fixed,
            "cmyk_round_rules": len(fix_map),
        }
        return buf.getvalue(), meta
    finally:
        doc.close()
