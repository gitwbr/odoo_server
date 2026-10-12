# -*- coding: utf-8 -*-
import json
import random
import uuid
import urllib.error
import urllib.parse
import urllib.request

NEGATIVE_TXT2IMG = (
    "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, "
    "fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, "
    "signature, watermark, username, blurry, deformed, ugly, disfigured, poorly drawn face, "
    "mutation, mutated, extra limb, floating limbs, disconnected limbs, malformed hands, "
    "out of focus, long neck, long body, disgusting, bad proportions, gross proportions, "
    "missing arms, missing legs, extra arms, extra legs, fused fingers, too many fingers, "
    "badly drawn hands, hands crossed,"
)

TRANSLATE_COMMON = {
    "direction": "Auto",
    "style": "Image Prompt",
    "preserve_terms": "ComfyUI, LoRA, GGUF, Flux, Krea 2, Z-Image, Qwen, Wan, SDXL",
    "extra_instruction": "",
    "model": "qwen2.5:14b",
    "endpoint": "http://127.0.0.1:11434",
    "keep_alive": "0",
    "num_ctx": 8192,
    "temperature": 0,
    "top_p": 0.7,
    "timeout_seconds": 120,
    "allow_remote_endpoint": False,
    "force_rerun": False,
    "debug_logging": False,
}


class ComfyUIError(Exception):
    pass


def _request(url, data=None, headers=None, timeout=30, method=None):
    headers = dict(headers or {})
    headers.setdefault("Connection", "close")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:800]
        raise ComfyUIError("ComfyUI HTTP %s：%s" % (exc.code, body)) from exc
    except urllib.error.URLError as exc:
        raise ComfyUIError("連不上 ComfyUI（%s）。請先在 Windows 啟動 ComfyUI，並確認 8188 已轉發。" % url) from exc
    except Exception as exc:
        raise ComfyUIError(str(exc) or "ComfyUI 連線中斷") from exc


def ping(base_url):
    _request(base_url.rstrip("/") + "/system_stats", timeout=8)


def _encode_multipart(fields, files):
    boundary = "----odoo" + uuid.uuid4().hex
    chunks = []
    for key, value in fields.items():
        chunks.append(("--%s" % boundary).encode())
        chunks.append(('Content-Disposition: form-data; name="%s"' % key).encode())
        chunks.append(b"")
        chunks.append(str(value).encode())
    for key, (filename, content, content_type) in files.items():
        chunks.append(("--%s" % boundary).encode())
        chunks.append(
            ('Content-Disposition: form-data; name="%s"; filename="%s"' % (key, filename)).encode()
        )
        chunks.append(("Content-Type: %s" % content_type).encode())
        chunks.append(b"")
        chunks.append(content)
    chunks.append(("--%s--" % boundary).encode())
    chunks.append(b"")
    return b"\r\n".join(chunks), boundary


def upload_image(base_url, raw_bytes, filename):
    body, boundary = _encode_multipart(
        {"overwrite": "true", "type": "input"},
        {"image": (filename, raw_bytes, "application/octet-stream")},
    )
    data = _request(
        base_url.rstrip("/") + "/upload/image",
        data=body,
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary},
        timeout=60,
    )
    info = json.loads(data.decode("utf-8"))
    name = info.get("name")
    if not name:
        raise ComfyUIError("上傳圖片失敗：%s" % info)
    return name


def queue_prompt(base_url, prompt):
    payload = json.dumps({"prompt": prompt, "client_id": "dtsc-odoo"}).encode("utf-8")
    data = _request(
        base_url.rstrip("/") + "/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    info = json.loads(data.decode("utf-8"))
    prompt_id = info.get("prompt_id")
    if not prompt_id:
        node_errors = info.get("node_errors") or info
        raise ComfyUIError("提交工作流失敗：%s" % node_errors)
    return prompt_id


def _history_cancelled(entry):
    status = entry.get("status") or {}
    flag = (status.get("status_str") or "").lower()
    if flag in ("cancel", "cancelled", "interrupted"):
        return True
    for item in status.get("messages") or []:
        if item and item[0] == "execution_interrupted":
            return True
    return False


def _history_error(entry):
    status = entry.get("status") or {}
    messages = status.get("messages") or []
    for item in messages:
        if item and item[0] == "execution_error":
            detail = item[1] if len(item) > 1 else {}
            node = detail.get("node_type") or detail.get("node_id") or ""
            msg = detail.get("exception_message") or str(detail)
            if node:
                return "%s：%s" % (node, msg)
            return msg
    if status.get("status_str") == "error":
        return "ComfyUI 執行失敗"
    return None


def poll_history(base_url, prompt_id):
    raw = _request(base_url.rstrip("/") + "/history/" + urllib.parse.quote(prompt_id), timeout=20)
    data = json.loads(raw.decode("utf-8") or "{}")
    entry = data.get(prompt_id)
    if not entry:
        return {"state": "running"}
    if _history_cancelled(entry):
        return {"state": "cancelled"}
    err = _history_error(entry)
    if err:
        return {"state": "error", "error": err}
    outputs = entry.get("outputs") or {}
    image_meta = None
    for out in outputs.values():
        images = out.get("images") or []
        if images:
            image_meta = images[0]
            break
    status = entry.get("status") or {}
    completed = bool(status.get("completed")) or bool(outputs)
    if not image_meta:
        if completed:
            return {"state": "error", "error": "工作流已結束但沒有輸出圖片"}
        return {"state": "running"}
    query = urllib.parse.urlencode({
        "filename": image_meta.get("filename") or "",
        "subfolder": image_meta.get("subfolder") or "",
        "type": image_meta.get("type") or "output",
    })
    image_bytes = _request(base_url.rstrip("/") + "/view?" + query, timeout=60)
    if not image_bytes:
        return {"state": "error", "error": "取回圖片為空"}
    return {"state": "done", "image": image_bytes}


def queue_status(base_url, prompt_id):
    raw = _request(base_url.rstrip("/") + "/queue", timeout=8)
    info = json.loads(raw.decode("utf-8") or "{}")
    running = info.get("queue_running") or []
    pending = info.get("queue_pending") or []

    def _match(item):
        return bool(item) and len(item) > 1 and item[1] == prompt_id

    for item in running:
        if _match(item):
            return {"phase": "running", "ahead": 0}
    for idx, item in enumerate(pending):
        if _match(item):
            return {"phase": "queued", "ahead": idx}
    return {"phase": "unknown", "ahead": 0}


def cancel_prompt(base_url, prompt_id):
    payload = json.dumps({"prompt_id": prompt_id} if prompt_id else {}).encode("utf-8")
    try:
        _request(
            base_url.rstrip("/") + "/interrupt",
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
    except ComfyUIError:
        try:
            _request(
                base_url.rstrip("/") + "/interrupt",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
        except ComfyUIError:
            pass
    if prompt_id:
        try:
            _request(
                base_url.rstrip("/") + "/queue",
                data=json.dumps({"delete": [prompt_id]}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
        except ComfyUIError:
            pass


def build_txt2img_prompt(user_text):
    seed = random.randint(1, 2 ** 53)
    return {
        "2": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "z_image_turbo_bf16.safetensors",
                "weight_dtype": "default",
            },
        },
        "7": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen_3_4b.safetensors",
                "type": "stable_diffusion",
                "device": "default",
            },
        },
        "10": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "z_image_turbo_ae.safetensors"},
        },
        "11": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": ["2", 0], "shift": 3, "sampling": "flow"},
        },
        "6": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": 768, "height": 1280, "batch_size": 1},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["7", 0], "text": user_text},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["7", 0], "text": NEGATIVE_TXT2IMG},
        },
        "1": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["11", 0],
                "positive": ["5", 0],
                "negative": ["4", 0],
                "latent_image": ["6", 0],
                "seed": seed,
                "steps": 36,
                "cfg": 1,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1,
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["1", 0], "vae": ["10", 0]},
        },
        "12": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": "dtsc_txt2img"},
        },
    }


def build_img2img_prompt(user_text, image_names):
    seed = random.randint(1, 2 ** 53)
    prompt = {
        "40": {
            "class_type": "DiffusionModelLoaderKJ",
            "inputs": {
                "model_name": "qwen_image_edit_2511_bf16.safetensors",
                "weight_dtype": "default",
                "compute_dtype": "default",
                "patch_cublaslinear": False,
                "sage_attention": "disabled",
                "enable_fp16_accumulation": False,
            },
        },
        "38": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["40", 0],
                "lora_name": "Qwen-Image-Lightning-4steps-V1.0.safetensors",
                "strength_model": 1,
            },
        },
        "37": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "type": "qwen_image",
                "device": "default",
            },
        },
        "39": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "qwen_image_vae.safetensors"},
        },
        "24": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": ["38", 0], "shift": 3, "sampling": "flow"},
        },
        "17": {
            "class_type": "CFGNorm",
            "inputs": {"model": ["24", 0], "strength": 1, "pre_cfg": False},
        },
        "18": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": 1280, "height": 768, "batch_size": 1},
        },
    }
    load_ids = ["6", "13", "14"]
    pos_inputs = {
        "clip": ["37", 0],
        "vae": ["39", 0],
        "prompt": user_text,
    }
    neg_inputs = {
        "clip": ["37", 0],
        "vae": ["39", 0],
        "prompt": "模糊",
    }
    for idx, filename in enumerate(image_names):
        node_id = load_ids[idx]
        prompt[node_id] = {
            "class_type": "LoadImage",
            "inputs": {"image": filename},
        }
        key = "image%d" % (idx + 1)
        pos_inputs[key] = [node_id, 0]
        neg_inputs[key] = [node_id, 0]
    prompt["9"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": pos_inputs}
    prompt["10"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": neg_inputs}
    prompt["1"] = {
        "class_type": "KSampler",
        "inputs": {
            "model": ["17", 0],
            "positive": ["9", 0],
            "negative": ["10", 0],
            "latent_image": ["18", 0],
            "seed": seed,
            "steps": 4,
            "cfg": 1,
            "sampler_name": "euler",
            "scheduler": "simple",
            "denoise": 1,
        },
    }
    prompt["19"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["1", 0], "vae": ["39", 0]},
    }
    prompt["21"] = {
        "class_type": "SaveImage",
        "inputs": {"images": ["19", 0], "filename_prefix": "dtsc_img2img"},
    }
    return prompt
