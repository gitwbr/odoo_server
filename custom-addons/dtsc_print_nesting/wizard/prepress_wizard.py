# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.dtsc_print_nesting.utils import ai_to_tiff

_logger = logging.getLogger(__name__)

JOB_TYPE_SELECTION = [
    ("general", "一般裁切 (General)"),
    ("splice", "材料接片 (Splicing)"),
    ("board_one", "單面切板 (One Side)"),
    ("board_two", "雙面貼板 (Two Side)"),
    ("board_splice", "板材接片 (Board Splicing)"),
    ("board_wrap", "板材包邊 (Board Wrap)"),
    ("lampcloth", "燈布車邊 (LampCloth Tailor)"),
    ("custom_splice", "自訂接片 (Splicing)[完成,編號]"),
]

# 目前僅實作一般裁切；其餘先列出來讓流程對齊原軟體
SUPPORTED_JOB_TYPES = {"general"}

# 第二層：彩白彩 / 圖層類型（原軟體「彩白彩 限用AI完稿」）
CWC_TYPE_SELECTION = [
    ("normal", "一般案件"),
    ("white", "白墨 (1層)"),
    ("white_color", "白彩 (1,2層)"),
    ("color_white", "彩白 (1,2層)"),
    ("cwc_same", "彩白彩[相同彩](1,2層)"),
    ("cwc_diff", "彩白彩[不同彩](1,2,3層)"),
    ("multi", "多層次[1層 1檔](限依檔 II)"),
]
SUPPORTED_CWC_TYPES = {"normal"}

# 第三層：裁切方式（原軟體 Cutter Way）
CUT_MARK_SELECTION = [
    ("cutter", "裁切標記 (Cutter Mark)"),
    ("filename", "檔名標記 (FileName Mark)"),
    ("filename_cutter", "檔名+裁切 (FileName N' Cutter)"),
    ("none", "不標記 (No Mark)"),
]

# 第四層：出血尺寸（原軟體 Bleed Size，單邊 cm）
BLEED_SELECTION = [
    ("0.0", "0.0"),
    ("0.1", "0.1"),
    ("0.3", "0.3"),
    ("0.5", "0.5"),
]

# 第五層：對位點位置（原軟體 Regmark Side）
REGMARK_SIDE_SELECTION = [
    ("auto", "自動判斷 (Automatic)"),
    ("long", "長邊 (Long Side)"),
    ("short", "短邊 (Short Side)"),
    ("tb", "上下 (Top & Bottom)"),
    ("lr", "左右 (Left & Right)"),
]

# 第六層：存檔格式（原軟體 Save Format）
SAVE_FORMAT_SELECTION = [
    ("tiff", "TIFF"),
    ("pdf", "PDF"),
    ("jpg", "JPG"),
    ("eps", "EPS"),
    ("png", "PNG"),
]
SUPPORTED_SAVE_FORMATS = {"tiff"}

# 第八層：消除鋸齒（原軟體 Optimized / ARTOPTIMIZED）
AA_MODE_SELECTION = [
    ("art", "1. 最佳化線條圖 (ARTOPTIMIZED)"),
    ("type", "2. 最佳化文字 (TYPEOPTIMIZED)"),
    ("none", "3. 不處理鋸齒 (None)"),
]

# 第九層：拍攝縮圖（原軟體 Take Layout）
THUMB_SELECTION = [
    ("skip", "不拍縮圖"),
    ("screen", "螢幕局部"),
]

# 其他功能清單（對齊原軟體；可複選，略過則全部不套用）
OTHER_FN_ITEMS = [
    ("make_cut_layer", "繪製裁切圖層[拼檔用] (make cut layer)"),
    ("expand_stroke", "展開填色筆畫 (Expand fill stroke)"),
    ("mirror_h", "全面左右鏡射 (Horizontal mirror)"),
    ("white_mark", "白色墨對位點 (White cut point)"),
    ("hand_cut_frame", "手切頁面黑框 (Hand cut line)"),
]


class PrepressWizard(models.TransientModel):
    _name = "dtsc.prepress.wizard"
    _description = "印前處理（AI → TIFF）"

    line_id = fields.Many2one("dtsc.checkoutline", string="訂單項次", required=True, ondelete="cascade")
    checkout_id = fields.Many2one(related="line_id.checkout_product_id", string="大圖訂單", readonly=True)
    sequence = fields.Integer(related="line_id.sequence", string="項次", readonly=True)
    project_product_name = fields.Text(related="line_id.project_product_name", string="檔名", readonly=True)

    layout_ai_filename = fields.Char(related="line_id.layout_ai_filename", string="AI 檔名", readonly=True)
    layout_ai_pdf_compatible = fields.Boolean(
        related="line_id.layout_ai_pdf_compatible", string="PDF 相容", readonly=True
    )
    layout_ai_width_cm = fields.Char(related="line_id.layout_ai_width_cm", string="AI 寬(cm)", readonly=True)
    layout_ai_height_cm = fields.Char(related="line_id.layout_ai_height_cm", string="AI 高(cm)", readonly=True)
    layout_ai_message = fields.Char(related="line_id.layout_ai_message", string="檢查訊息", readonly=True)

    step = fields.Selection(
        [
            ("job", "1. 案件類別"),
            ("cwc", "2. 彩白彩 / 圖層"),
            ("marks", "3. 裁切方式"),
            ("bleed", "4. 出血尺寸"),
            ("regside", "5. 對位點位置"),
            ("fmt", "6. 存檔格式"),
            ("output", "7. 轉檔解析度"),
            ("aa", "8. 消除鋸齒"),
            ("thumb", "9. 拍攝縮圖"),
            ("size", "10. 延伸AI頁面尺寸"),
            ("other", "11. 其他功能"),
            ("confirm", "12. 確認執行"),
        ],
        string="步驟",
        default="job",
        required=True,
    )
    step_title = fields.Char(compute="_compute_step_title")

    # 1. 案件類別
    job_type = fields.Selection(JOB_TYPE_SELECTION, string="案件類別", default="general", required=True)
    job_type_supported = fields.Boolean(compute="_compute_job_type_supported")

    # 2. 彩白彩 / 圖層類型
    cwc_type = fields.Selection(
        CWC_TYPE_SELECTION,
        string="彩白彩類型",
        default="normal",
        required=True,
        help="選擇「一般案件」或「彩白彩」類型（圖層數）。多層次：圖層名稱起始為[特]時視為特別色。",
    )
    cwc_type_supported = fields.Boolean(compute="_compute_cwc_type_supported")

    # 3. 裁切方式（Cutter Way）
    cut_mark_mode = fields.Selection(
        CUT_MARK_SELECTION,
        string="裁切方式",
        default="filename_cutter",
        required=True,
        help="裁切標記=對位點；檔名標記=↑單號；檔名+裁切=兩者都加（常用）。",
    )

    # 4. 出血尺寸（單邊 cm）
    bleed_choice = fields.Selection(
        BLEED_SELECTION,
        string="出血尺寸(單邊cm)",
        default="0.0",
        required=True,
        help="AI 檔案的出血為單邊 cm？",
    )
    bleed_cm = fields.Float(
        string="出血(cm)",
        compute="_compute_bleed_cm",
        store=True,
        digits=(16, 2),
    )

    # 5. 對位點位置
    regmark_side = fields.Selection(
        REGMARK_SIDE_SELECTION,
        string="對位點位置",
        default="auto",
        required=True,
        help="自動：長度+(點徑x2)≤240cm 用短邊，否則長邊。材料接片請先指定上下或左右。",
    )

    # 6. 存檔格式
    save_format = fields.Selection(
        SAVE_FORMAT_SELECTION,
        string="存檔格式",
        default="tiff",
        required=True,
        help="PDF=圖文分離；JPG=經 TIFF 轉存；EPS=LDP 特別色；PNG=僅 RGB。自動排版印刷檔目前僅寫回 TIFF。",
    )
    save_format_supported = fields.Boolean(compute="_compute_save_format_supported")

    # 7. 轉檔解析度（原軟體「輸入轉檔 解析度 (dpi)」）
    dpi_mode = fields.Selection(
        [
            ("auto", "自動判斷"),
            ("manual", "手動, 拼檔"),
        ],
        string="解析度模式",
        default="auto",
        required=True,
        help="手動, 拼檔＝全部依輸入 dpi（拼檔必用）；自動判斷＝依頁面尺寸估 dpi，過大則用輸入值。",
    )
    dpi = fields.Integer(
        string="輸入 DPI",
        default=100,
        required=True,
        help="原軟體預設 100。拼檔請用手動；自動模式此值作過大時後備。",
    )

    # 8. 消除鋸齒（原軟體 Optimized）
    aa_mode = fields.Selection(
        AA_MODE_SELECTION,
        string="消除鋸齒",
        default="art",
        required=True,
        help="最佳化線條圖＝柔和向量；最佳化文字＝字較清晰；不處理＝保持原圖、轉檔較快。",
    )

    # 9. 拍攝縮圖（原軟體 Take Layout）
    thumb_mode = fields.Selection(
        THUMB_SELECTION,
        string="拍攝縮圖",
        default="screen",
        required=True,
        help="螢幕局部＝從產出 TIFF 自動產生列表預覽（預設）；不拍縮圖＝仍寫 TIFF，但不產預覽圖。",
    )

    # 10. 延伸AI頁面尺寸（原軟體 Expand Artboard）
    expand_ltrb = fields.Char(
        string="左,上,右,下 (cm)",
        default="0,0,0,0",
        help="不修改 Artboard：0,0,0,0 或空值；四邊延伸 0.3：0.3,0.3,0.3,0.3 或單一值 0.3。",
    )
    # 標記 / 輸出檔名（原軟體後續對話或預設推導，確認步可改）
    label_name = fields.Char(string="標記前綴")
    label_seq = fields.Char(string="標記序號")
    output_filename = fields.Char(string="輸出 TIFF 檔名")

    # 11. 其他功能（原軟體 other function；command+點選複選 → 網頁用勾選）
    other_skip = fields.Boolean(
        string="---> 略過 其他功能 (skip fn) <---",
        default=True,
        help="勾選略過則不套用下列功能；取消略過後可複選多項。",
    )
    make_cut_layer = fields.Boolean(
        string="繪製裁切圖層[拼檔用] (make cut layer)",
        default=False,
        help="預留：記錄選項，TIFF 輸出尚未實作裁切圖層。",
    )
    expand_stroke = fields.Boolean(
        string="展開填色筆畫 (Expand fill stroke)",
        default=False,
        help="需 Illustrator，伺服器端暫不支援；勾選後執行會提示。",
    )
    mirror_h = fields.Boolean(string="全面左右鏡射 (Horizontal mirror)", default=False)
    white_mark = fields.Boolean(
        string="白色墨對位點 (White cut point)",
        default=False,
        help="預留：記錄選項，TIFF 輸出尚未實作白墨對位。",
    )
    hand_cut_frame = fields.Boolean(string="手切頁面黑框 (Hand cut line)", default=False)

    summary_html = fields.Html(compute="_compute_summary_html", sanitize=False)

    STEP_ORDER = [
        "job", "cwc", "marks", "bleed", "regside", "fmt", "output", "aa",
        "thumb", "size", "other", "confirm",
    ]

    @api.depends("step")
    def _compute_step_title(self):
        titles = dict(self._fields["step"].selection)
        for rec in self:
            rec.step_title = titles.get(rec.step) or ""

    @api.depends("job_type")
    def _compute_job_type_supported(self):
        for rec in self:
            rec.job_type_supported = rec.job_type in SUPPORTED_JOB_TYPES

    @api.depends("cwc_type")
    def _compute_cwc_type_supported(self):
        for rec in self:
            rec.cwc_type_supported = rec.cwc_type in SUPPORTED_CWC_TYPES

    @api.depends("bleed_choice")
    def _compute_bleed_cm(self):
        for rec in self:
            try:
                rec.bleed_cm = float(rec.bleed_choice or 0.0)
            except (TypeError, ValueError):
                rec.bleed_cm = 0.0

    @api.depends("save_format")
    def _compute_save_format_supported(self):
        for rec in self:
            rec.save_format_supported = rec.save_format in SUPPORTED_SAVE_FORMATS

    def _selected_other_labels(self):
        self.ensure_one()
        if self.other_skip:
            return ["略過 其他功能 (skip fn)"]
        labels = []
        for fname, label in OTHER_FN_ITEMS:
            if getattr(self, fname, False):
                labels.append(label)
        return labels or ["略過 其他功能 (skip fn)"]

    @api.depends(
        "job_type", "cwc_type", "cut_mark_mode", "thumb_mode", "bleed_choice", "bleed_cm",
        "regmark_side", "save_format", "expand_ltrb", "dpi_mode", "dpi", "aa_mode",
        "label_name", "label_seq", "output_filename", "other_skip", "mirror_h", "make_cut_layer",
        "expand_stroke", "white_mark", "hand_cut_frame",
        "layout_ai_filename", "layout_ai_width_cm", "layout_ai_height_cm",
    )
    def _compute_summary_html(self):
        job_map = dict(JOB_TYPE_SELECTION)
        cwc_map = dict(CWC_TYPE_SELECTION)
        mark_map = dict(CUT_MARK_SELECTION)
        thumb_map = dict(THUMB_SELECTION)
        side_map = dict(REGMARK_SIDE_SELECTION)
        fmt_map = dict(SAVE_FORMAT_SELECTION)
        aa_map = dict(AA_MODE_SELECTION)
        for rec in self:
            rows = [
                ("案件類別", job_map.get(rec.job_type, "")),
                ("彩白彩類型", cwc_map.get(rec.cwc_type, "")),
                ("AI 檔", rec.layout_ai_filename or "—"),
                ("AI 尺寸", "%s × %s cm" % (rec.layout_ai_width_cm or "?", rec.layout_ai_height_cm or "?")),
                ("裁切方式", mark_map.get(rec.cut_mark_mode, "")),
                ("出血(單邊)", "%s cm" % (rec.bleed_choice or "0.0")),
                ("對位點位置", side_map.get(rec.regmark_side, "")),
                ("存檔格式", fmt_map.get(rec.save_format, "")),
                (
                    "轉檔解析度",
                    "自動判斷（後備 %s DPI）" % rec.dpi
                    if rec.dpi_mode == "auto"
                    else "手動, 拼檔（%s DPI）" % rec.dpi,
                ),
                ("消除鋸齒", aa_map.get(rec.aa_mode, "")),
                ("拍攝縮圖", thumb_map.get(rec.thumb_mode, "")),
                ("延伸頁面", rec.expand_ltrb or "0,0,0,0"),
                ("標記", "↑%s-%s" % (rec.label_name or "?", rec.label_seq or "?")),
                ("輸出檔名", rec.output_filename or "—"),
                ("其他功能", "；".join(rec._selected_other_labels())),
            ]
            lis = "".join("<tr><th>%s</th><td>%s</td></tr>" % (k, v) for k, v in rows)
            rec.summary_html = (
                '<table class="table table-sm table-bordered mb-0">%s</table>' % lis
            )

    @api.onchange("other_skip")
    def _onchange_other_skip(self):
        if self.other_skip:
            self.make_cut_layer = False
            self.expand_stroke = False
            self.mirror_h = False
            self.white_mark = False
            self.hand_cut_frame = False

    @api.onchange(
        "make_cut_layer", "expand_stroke", "mirror_h", "white_mark", "hand_cut_frame",
    )
    def _onchange_other_items(self):
        if any([
            self.make_cut_layer, self.expand_stroke, self.mirror_h,
            self.white_mark, self.hand_cut_frame,
        ]):
            self.other_skip = False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line = self.env["dtsc.checkoutline"].browse(
            self.env.context.get("default_line_id") or self.env.context.get("active_id")
        )
        if not line:
            return res
        res["line_id"] = line.id
        res["step"] = "job"
        fname = line.layout_ai_filename or ""
        name, seq = ai_to_tiff.parse_label_from_filename(fname)
        if not name:
            cname = (line.checkout_product_id.name or "").lstrip("AFEMD")
            digits = "".join(ch for ch in cname if ch.isdigit())
            name = digits[-3:] if len(digits) >= 3 else (digits or "000")
        if not seq:
            seq = "%02d" % (line.sequence or 1)
        res["label_name"] = name
        res["label_seq"] = seq
        base = fname.rsplit(".", 1)[0] if fname else (line.project_product_name or "layout")
        if isinstance(base, str):
            base = base.strip().split("\n")[0][:80] or "layout"
        res["output_filename"] = "%s.tif" % base
        return res

    def action_next(self):
        self.ensure_one()
        order = self.STEP_ORDER
        if self.step == "job" and self.job_type not in SUPPORTED_JOB_TYPES:
            raise UserError(
                _("「%s」尚未開放，目前僅支援「一般裁切」。")
                % dict(JOB_TYPE_SELECTION).get(self.job_type, self.job_type)
            )
        if self.step == "cwc" and self.cwc_type not in SUPPORTED_CWC_TYPES:
            raise UserError(
                _("「%s」尚未開放，目前僅支援「一般案件」。白墨 / 彩白彩等多層輸出後續再加。")
                % dict(CWC_TYPE_SELECTION).get(self.cwc_type, self.cwc_type)
            )
        if self.step == "fmt" and self.save_format not in SUPPORTED_SAVE_FORMATS:
            raise UserError(
                _("「%s」尚未寫回自動排版印刷檔。目前僅支援 TIFF（下游拼檔/印刷需要）；"
                  "PDF/JPG/EPS/PNG 後續再開放。")
                % dict(SAVE_FORMAT_SELECTION).get(self.save_format, self.save_format)
            )
        if self.step == "output" and (not self.dpi or self.dpi < 1):
            raise UserError(_("請輸入有效的轉檔解析度（dpi）。"))
        if self.step == "size":
            try:
                ai_to_tiff.parse_expand_ltrb(self.expand_ltrb)
            except ValueError as err:
                raise UserError(str(err)) from err
        idx = order.index(self.step)
        if idx >= len(order) - 1:
            return True
        self.step = order[idx + 1]
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        order = self.STEP_ORDER
        idx = order.index(self.step)
        if idx <= 0:
            return self._reopen()
        self.step = order[idx - 1]
        return self._reopen()

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(self.env.context),
        }

    def action_run_prepress(self):
        self.ensure_one()
        line = self.line_id
        if not line._has_layout_ai_file():
            raise UserError(_("請先上傳 AI / PDF 檔案。"))
        if line.layout_ai_pdf_compatible is False:
            raise UserError(
                line.layout_ai_message
                or _("此 AI 檔未建立 PDF 相容內容，無法處理。請重新另存後再上傳。")
            )
        if self.job_type not in SUPPORTED_JOB_TYPES:
            raise UserError(_("目前僅支援「一般裁切」。"))
        if self.cwc_type not in SUPPORTED_CWC_TYPES:
            raise UserError(_("目前僅支援「一般案件」（無白墨 / 彩白彩分層）。"))
        if self.save_format not in SUPPORTED_SAVE_FORMATS:
            raise UserError(_("目前僅支援輸出 TIFF 並寫回自動排版項次。"))
        if not self.dpi or self.dpi < 1:
            raise UserError(_("請輸入有效的轉檔解析度（dpi）。"))

        # 其他功能：略過時全部不套用
        do_cut_layer = (not self.other_skip) and bool(self.make_cut_layer)
        do_expand_stroke = (not self.other_skip) and bool(self.expand_stroke)
        do_mirror = (not self.other_skip) and bool(self.mirror_h)
        do_white_mark = (not self.other_skip) and bool(self.white_mark)
        do_hand_cut = (not self.other_skip) and bool(self.hand_cut_frame)

        if do_expand_stroke:
            raise UserError(_("「展開填色筆畫」需 Illustrator，伺服器端暫不支援，請取消後再執行。"))

        try:
            expand = ai_to_tiff.parse_expand_ltrb(self.expand_ltrb)
        except ValueError as err:
            raise UserError(str(err)) from err

        # 裁切方式 → 對位點 / 檔名標記
        mode = self.cut_mark_mode or "filename_cutter"
        add_regmarks = mode in ("cutter", "filename_cutter")
        add_filename_label = mode in ("filename", "filename_cutter")
        add_frame = do_hand_cut or mode != "none"

        raw = line._read_layout_ai_raw()
        options = ai_to_tiff.PrepressOptions(
            dpi=int(self.dpi or 100),
            dpi_mode=self.dpi_mode or "auto",
            bleed_cm=self.bleed_cm or 0.0,
            expand_ltrb=expand,
            add_regmarks=add_regmarks,
            add_filename_label=add_filename_label,
            add_frame=add_frame,
            mirror_h=do_mirror,
            regmark_side=self.regmark_side or "auto",
            label_name=(self.label_name or "").strip() or "00",
            label_seq=(self.label_seq or "").strip() or "01",
            aa_mode=self.aa_mode or "art",
        )
        try:
            tiff_bytes, meta = ai_to_tiff.convert_ai_to_tiff_bytes(raw, options)
        except Exception as err:
            _logger.exception("prepress convert failed line=%s", line.id)
            line.write({
                "layout_prepress_state": "error",
                "layout_prepress_message": str(err),
            })
            raise UserError(_("印前處理失敗：%s") % err) from err

        filename = (self.output_filename or "").strip() or "layout.tif"
        if not filename.lower().endswith((".tif", ".tiff")):
            filename = "%s.tif" % filename

        # 列表預覽與 TIFF 一併產生（預設）；僅「不拍縮圖」時跳過
        need_preview = (self.thumb_mode or "screen") != "skip"
        line._store_layout_tiff_raw(tiff_bytes, filename, need_preview=need_preview)

        extra = []
        if do_cut_layer:
            extra.append(_("裁切圖層：暫存標記，輸出尚未實作"))
        if do_white_mark:
            extra.append(_("白墨對位：暫存標記，輸出尚未實作"))
        if do_mirror:
            extra.append(_("左右鏡射"))
        if do_hand_cut:
            extra.append(_("手切黑框"))
        if need_preview:
            extra.append(_("已產預覽圖"))
        else:
            extra.append(_("不拍縮圖"))
        if meta.get("cmyk_round_fixed_px"):
            extra.append(_("CMYK 實色已對齊 Illustrator 四捨五入"))
        msg = _("已生成 TIFF：%(fn)s（%(w)s×%(h)scm @ %(dpi)s DPI）【%(job)s / %(cwc)s】") % {
            "fn": filename,
            "w": meta.get("width_cm"),
            "h": meta.get("height_cm"),
            "dpi": meta.get("dpi"),
            "job": dict(JOB_TYPE_SELECTION).get(self.job_type, self.job_type),
            "cwc": dict(CWC_TYPE_SELECTION).get(self.cwc_type, self.cwc_type),
        }
        if extra:
            msg = "%s；%s" % (msg, "；".join(extra))

        line.write({
            "layout_prepress_state": "done",
            "layout_prepress_message": msg,
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("印前處理完成"),
                "message": _("已寫入 TIFF「%s」。") % filename,
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
