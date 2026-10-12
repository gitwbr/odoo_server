# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DtscComfyuiJob(models.Model):
    _name = "dtsc.comfyui.job"
    _description = "AI 出圖歷史"
    _order = "id desc"

    name = fields.Char(string="摘要", compute="_compute_name", store=True)
    studio_id = fields.Many2one("dtsc.comfyui.studio", string="工作台", ondelete="cascade")
    user_id = fields.Many2one("res.users", string="操作人", default=lambda self: self.env.user)
    mode = fields.Selection(
        [("txt2img", "文生圖"), ("img2img", "圖生圖")],
        string="類型",
        required=True,
    )
    prompt = fields.Text(string="提示詞")
    image = fields.Binary(string="出圖結果", attachment=True)
    ref_image1 = fields.Binary(string="參考圖一", attachment=True)
    ref_image2 = fields.Binary(string="參考圖二", attachment=True)
    ref_image3 = fields.Binary(string="參考圖三", attachment=True)
    prompt_id = fields.Char(string="ComfyUI 任務ID")
    state = fields.Selection(
        [
            ("done", "完成"),
            ("cancelled", "已停止"),
            ("error", "失敗"),
        ],
        default="done",
        string="狀態",
    )

    @api.depends("prompt", "mode")
    def _compute_name(self):
        for rec in self:
            text = (rec.prompt or "").strip().replace("\n", " ")
            if len(text) > 24:
                text = text[:24] + "…"
            rec.name = text or (dict(rec._fields["mode"].selection).get(rec.mode) or "出圖")
