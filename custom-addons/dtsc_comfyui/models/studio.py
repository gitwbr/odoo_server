# -*- coding: utf-8 -*-
import base64
import uuid

from odoo import api, fields, models
from odoo.exceptions import UserError

from . import comfyui_client as comfy

DEFAULT_URL = "http://host.docker.internal:8188"


class DtscComfyuiStudio(models.Model):
    _name = "dtsc.comfyui.studio"
    _description = "AI 出圖工作台"
    _rec_name = "display_name"

    display_name = fields.Char(default="AI 出圖工作台")
    state = fields.Selection(
        [
            ("draft", "待出圖"),
            ("running", "出圖中"),
            ("done", "完成"),
            ("cancelled", "已停止"),
            ("error", "失敗"),
        ],
        default="draft",
        string="狀態",
    )
    error_message = fields.Text(string="錯誤訊息", readonly=True)
    prompt_id = fields.Char(readonly=True)
    comfyui_url = fields.Char(string="ComfyUI 地址")
    started_at = fields.Datetime(readonly=True)
    progress_text = fields.Char(string="進度", readonly=True)

    txt_prompt = fields.Text(string="提示詞")
    img_prompt = fields.Text(string="編輯描述")
    image1 = fields.Binary(string="圖片一", attachment=True)
    image2 = fields.Binary(string="圖片二", attachment=True)
    image3 = fields.Binary(string="圖片三", attachment=True)
    result_image = fields.Binary(string="生成結果", attachment=True, readonly=True)
    result_at = fields.Datetime(string="本次出圖時間", readonly=True)
    # 為 img2img 時暫時隱藏「文生圖」頁籤，讓 notebook 自動落到「圖生圖」（用完由前端清掉）
    ui_open_tab = fields.Selection(
        [("img2img", "圖生圖")],
        string="UI 目標頁籤",
        copy=False,
    )
    last_mode = fields.Selection(
        [("txt2img", "文生圖"), ("img2img", "圖生圖")],
        string="上次類型",
    )
    job_ids = fields.One2many("dtsc.comfyui.job", "studio_id", string="歷史記錄")

    def _base_url(self):
        url = (self.comfyui_url or "").strip()
        if not url:
            url = self.env["ir.config_parameter"].sudo().get_param(
                "dtsc_comfyui.base_url", DEFAULT_URL
            )
        return (url or DEFAULT_URL).rstrip("/")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        res["comfyui_url"] = self.env["ir.config_parameter"].sudo().get_param(
            "dtsc_comfyui.base_url", DEFAULT_URL
        )
        return res

    def write(self, vals):
        res = super().write(vals)
        if "comfyui_url" in vals and vals.get("comfyui_url"):
            self.env["ir.config_parameter"].sudo().set_param(
                "dtsc_comfyui.base_url", vals["comfyui_url"].strip()
            )
        return res

    @api.model
    def action_open_studio(self):
        rec = self.search([("create_uid", "=", self.env.uid)], limit=1)
        if not rec:
            rec = self.create({})
        elif not rec.comfyui_url:
            rec.comfyui_url = self.env["ir.config_parameter"].sudo().get_param(
                "dtsc_comfyui.base_url", DEFAULT_URL
            )
        if rec.result_image and not rec.job_ids:
            rec.last_mode = rec.last_mode or "txt2img"
            rec._archive_current()
        return {
            "type": "ir.actions.act_window",
            "name": "出圖工作台",
            "res_model": "dtsc.comfyui.studio",
            "view_mode": "form",
            "res_id": rec.id,
            "target": "current",
            "context": {"form_view_initial_mode": "edit"},
        }

    def _history_prompt(self, mode=None):
        self.ensure_one()
        mode = mode or self.last_mode or "txt2img"
        if mode == "img2img":
            return (self.img_prompt or "").strip()
        return (self.txt_prompt or "").strip()

    def _archive_current(self):
        self.ensure_one()
        if not self.result_image:
            return
        if self.prompt_id and self.env["dtsc.comfyui.job"].search_count([
            ("studio_id", "=", self.id),
            ("prompt_id", "=", self.prompt_id),
        ]):
            return
        mode = self.last_mode or "txt2img"
        self.env["dtsc.comfyui.job"].create({
            "studio_id": self.id,
            "user_id": self.env.uid,
            "mode": mode,
            "prompt": self._history_prompt(mode),
            "image": self.result_image,
            "ref_image1": self.image1 if mode == "img2img" else False,
            "ref_image2": self.image2 if mode == "img2img" else False,
            "ref_image3": self.image3 if mode == "img2img" else False,
            "prompt_id": self.prompt_id,
            "state": "done" if self.state in ("done", "running", "draft") else (self.state or "done"),
        })

    def _record_finished(self, image_b64, job_state="done"):
        self.ensure_one()
        mode = self.last_mode or "txt2img"
        vals = {
            "studio_id": self.id,
            "user_id": self.env.uid,
            "mode": mode,
            "prompt": self._history_prompt(mode),
            "image": image_b64 or False,
            "ref_image1": self.image1 if mode == "img2img" else False,
            "ref_image2": self.image2 if mode == "img2img" else False,
            "ref_image3": self.image3 if mode == "img2img" else False,
            "prompt_id": self.prompt_id,
            "state": job_state,
        }
        if self.prompt_id:
            existing = self.env["dtsc.comfyui.job"].search([
                ("studio_id", "=", self.id),
                ("prompt_id", "=", self.prompt_id),
            ], limit=1)
            if existing:
                existing.write({k: v for k, v in vals.items() if k != "studio_id"})
                return existing
        return self.env["dtsc.comfyui.job"].create(vals)

    def _submit(self, mode):
        self.ensure_one()
        base = self._base_url()
        try:
            comfy.ping(base)
        except comfy.ComfyUIError as exc:
            raise UserError(str(exc)) from exc

        if mode == "txt2img":
            text = (self.txt_prompt or "").strip()
            if not text:
                raise UserError("請先填寫文生圖提示詞。")
            prompt = comfy.build_txt2img_prompt(text)
        else:
            text = (self.img_prompt or "").strip()
            if not text:
                raise UserError("請先填寫圖生圖描述。")
            names = []
            for idx, field_name in enumerate(("image1", "image2", "image3"), start=1):
                raw_b64 = self[field_name]
                if not raw_b64:
                    continue
                raw = base64.b64decode(raw_b64)
                filename = "odoo_%s_%s.png" % (self.id, uuid.uuid4().hex[:8])
                try:
                    names.append(comfy.upload_image(base, raw, filename))
                except comfy.ComfyUIError as exc:
                    raise UserError(str(exc)) from exc
            if not names:
                raise UserError("圖生圖至少上傳一張圖片。")
            prompt = comfy.build_img2img_prompt(text, names)

        self._archive_current()
        self.result_image = False
        self.result_at = False

        try:
            prompt_id = comfy.queue_prompt(base, prompt)
        except comfy.ComfyUIError as exc:
            raise UserError(str(exc)) from exc

        self.write({
            "state": "running",
            "error_message": False,
            "prompt_id": prompt_id,
            "comfyui_url": base,
            "last_mode": mode,
            "started_at": fields.Datetime.now(),
            "progress_text": "已提交，正在出圖中，請勿離開…",
            "result_image": False,
            "result_at": False,
        })

    def action_generate_txt2img(self):
        self._submit("txt2img")
        return True

    def action_generate_img2img(self):
        self._submit("img2img")
        return True

    def action_continue_edit(self):
        """把本次結果放到圖生圖圖片一，清空圖片二/三與圖生圖提示詞，方便繼續改圖。"""
        self.ensure_one()
        if self.state == "running":
            raise UserError("出圖進行中，請稍候再繼續處理。")
        if not self.result_image:
            raise UserError("目前沒有可繼續處理的生成結果。")
        self.write({
            "image1": self.result_image,
            "image2": False,
            "image3": False,
            "img_prompt": False,
            "result_image": False,
            "result_at": False,
            "error_message": False,
            "ui_open_tab": "img2img",
            # 繼續處理視為新流程，回到待出圖
            "state": "draft",
            "prompt_id": False,
            "started_at": False,
            "progress_text": False,
            "last_mode": False,
        })
        # 重開表單，讓 notebook 依 page invisible 重新計算當前頁籤
        return {
            "type": "ir.actions.act_window",
            "name": "出圖工作台",
            "res_model": "dtsc.comfyui.studio",
            "view_mode": "form",
            "res_id": self.id,
            "target": "current",
            "context": {"form_view_initial_mode": "edit"},
        }

    def _elapsed_label(self):
        self.ensure_one()
        if not self.started_at:
            return "0 秒"
        secs = max(0, int((fields.Datetime.now() - self.started_at).total_seconds()))
        if secs < 60:
            return "%d 秒" % secs
        return "%d 分 %02d 秒" % (secs // 60, secs % 60)

    def _progress_payload(self, extra_text):
        self.ensure_one()
        text = extra_text
        self.write({"progress_text": text})
        return {
            "state": "running",
            "error_message": "",
            "progress_text": text,
        }

    def action_poll(self):
        self.ensure_one()
        if self.state != "running" or not self.prompt_id:
            return {
                "state": self.state,
                "error_message": self.error_message or "",
                "progress_text": self.progress_text or "",
            }
        base = self._base_url()
        elapsed = self._elapsed_label()
        try:
            comfy.ping(base)
            qstat = comfy.queue_status(base, self.prompt_id)
            result = comfy.poll_history(base, self.prompt_id)
        except comfy.ComfyUIError:
            secs = 0
            if self.started_at:
                secs = int((fields.Datetime.now() - self.started_at).total_seconds())
            if secs > 20 * 60:
                msg = "出圖超過 20 分鐘仍未完成，已停止等待。"
                self.write({"state": "error", "error_message": msg, "progress_text": False})
                return {"state": "error", "error_message": msg, "progress_text": ""}
            return self._progress_payload(
                "仍在出圖中，請勿離開。已等待 %s（連線閃斷，正在重試）" % elapsed
            )
        if result["state"] == "running":
            secs = 0
            if self.started_at:
                secs = int((fields.Datetime.now() - self.started_at).total_seconds())
            if qstat.get("phase") == "unknown" and secs > 480:
                msg = "出圖超過 8 分鐘仍對不到任務，可能已結束或失敗。請查看歷史記錄，或點停止後重試。"
                self.write({"state": "error", "error_message": msg, "progress_text": False})
                return {"state": "error", "error_message": msg, "progress_text": ""}
            if secs > 20 * 60:
                msg = "出圖超過 20 分鐘仍未完成，已停止等待。"
                self.write({"state": "error", "error_message": msg, "progress_text": False})
                return {"state": "error", "error_message": msg, "progress_text": ""}
            if qstat.get("phase") == "queued":
                ahead = int(qstat.get("ahead") or 0)
                if ahead:
                    msg = "排隊中，前面還有 %d 個任務。已等待 %s，請勿離開。" % (ahead, elapsed)
                else:
                    msg = "即將開始出圖。已等待 %s，請勿離開。" % elapsed
            elif qstat.get("phase") == "running":
                msg = "正在出圖中，請勿離開。已等待 %s（ComfyUI 連線正常）" % elapsed
            else:
                msg = "正在出圖中，請勿離開。已等待 %s" % elapsed
            return self._progress_payload(msg)
        if result["state"] == "cancelled":
            self._record_finished(False, "cancelled")
            self.write({
                "state": "cancelled",
                "error_message": False,
                "progress_text": "已停止本次出圖",
                "result_image": False,
                "result_at": False,
            })
            return {"state": "cancelled", "error_message": "", "progress_text": "已停止本次出圖"}
        if result["state"] == "error":
            msg = result.get("error") or "出圖失敗"
            self._record_finished(False, "error")
            self.write({"state": "error", "error_message": msg, "progress_text": False})
            return {"state": "error", "error_message": msg, "progress_text": ""}
        self._record_finished(base64.b64encode(result["image"]), "done")
        self.write({
            "state": "done",
            "error_message": False,
            "progress_text": "出圖完成",
            "result_image": base64.b64encode(result["image"]),
            "result_at": fields.Datetime.now(),
        })
        return {"state": "done", "error_message": "", "progress_text": "出圖完成"}

    def action_stop(self):
        self.ensure_one()
        if self.state != "running":
            return True
        try:
            comfy.cancel_prompt(self._base_url(), self.prompt_id)
        except comfy.ComfyUIError as exc:
            raise UserError("停止失敗：%s" % exc) from exc
        self._record_finished(False, "cancelled")
        self.write({
            "state": "cancelled",
            "error_message": False,
            "progress_text": "已停止本次出圖",
            "result_image": False,
            "result_at": False,
        })
        return True
