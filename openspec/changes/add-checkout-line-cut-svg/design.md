## Context

社区版大图订单项次模型为 `dtsc.checkoutline`，已有：

- `product_width` / `product_height`：宽高（Char，单位业务上多为 cm）
- `multi_chose_ids` / `aftermakepricelist_lines`：后加工
- `product_atts`、`comment`、`project_product_name`
- `small_image` / `small_image_new`：小图

目标是项次上传参考图后，结合上述上下文全自动生成刀模 SVG。用户明确：**全程 AI，无人工确认**；后加工对应的 prompt 后续可微调。

参考对话中的架构（AI 读懂 → 程序画线）仍然成立，但确认环节去掉，不确定参数走产品/后加工模板默认值。

## Goals / Non-Goals

### Goals

- 项次上一键（或上传后触发）跑通：`图片 + 订单字段 → GPT JSON → SVG`
- Prompt 按后加工可配置，便于后续微调
- SVG 分层（至少 CUT / CREASE / KISS），可下载
- 失败可看见错误状态，不阻塞整张大图单

### Non-Goals（第一版不做）

- 人工确认 UI
- 企业版 AI Gateway / LangChain 服务
- 多产品模板全覆盖（先通用 JSON schema + 一种五面底座几何）
- 直接对接 Zünd / RIP
- PDF 向量 Path 解析（优先 JPG/PNG Vision；PDF 可后续）

## Decisions

### Decision 1：挂在 `dtsc.checkoutline`，逻辑放 `dtsc` 内 utils

- 业务入口就是项次，避免新模块安装摩擦。
- 几何与 GPT 调用放 `custom-addons/dtsc/utils/cut_svg/`，视图只加按钮与字段。

### Decision 2：两段式管线，AI 不直接画 SVG

```
checkoutline 上下文 + image
        ↓
GPT Vision（按后加工选 prompt）→ structured JSON
        ↓
模板默认值补齐 uncertain 字段
        ↓
Geometry Engine → layered SVG
        ↓
写回 checkoutline.cut_svg_* 字段
```

AI 只负责结构理解与尺寸解读；刀线由公式生成。

### Decision 3：无确认窗；不确定字段用默认模板

例如搭接耳 `tab_depth_mm=30`、`tab_bevel_mm=10` 存在模板/后加工配置里。GPT 可建议，但最终以「配置默认 ∪ GPT 高置信输出」合并策略为准：第一版采用 **配置默认覆盖 GPT 的 uncertain 建议**，保证可复现。

### Decision 4：密钥来自 `GPT_API_KEY` 环境变量

社区版 Docker/主机 `.env` 已有该变量。Odoo 进程需能读到；若未配置则按钮报错提示。

### Decision 5：触发方式第一版为显式按钮

`action_generate_cut_svg`。上传图自动触发可作为后续选项，避免每次改小图都扣 API。

## Data shape（GPT → Engine）

```json
{
  "product_type": "rectangular_pedestal",
  "dimensions_mm": {
    "front_width": 1860,
    "front_height": 605,
    "depth": 205,
    "board_width": 2270,
    "board_height": 1015
  },
  "structure": {
    "top_panel": true,
    "bottom_panel": true,
    "left_panel": true,
    "right_panel": true,
    "corner_tabs": true
  },
  "material": {"name": "PVC", "thickness_mm": 5},
  "confidence": "high",
  "notes": []
}
```

订单项次的宽高、后加工名称会作为 **权威文本上下文** 一并塞进 prompt，优先于纯 OCR，减少 AI 瞎猜尺寸。

## Risks / Trade-offs

- 无人工确认 → 错误刀模可能直接产出 → 用状态字段 + 可重跑 + 保留 JSON 便于排查
- Vision 费用与延迟 → 仅按钮触发；后续可加队列
- 后加工种类多 → prompt 表先通用，按名称逐个补

## Open Questions

- 参考图用新建 `cut_source_image` 还是复用 `small_image_new`？（提案默认：新建字段，避免和现有小图预览耦合）
- 宽高单位：业务 Char 多为 cm，引擎内部统一 mm；转换规则写死 `*10`，特殊后加工可在 prompt/配置覆盖
