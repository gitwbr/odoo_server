# Change: 大图订单项次图片自动生成刀模 SVG

## Why

印前需要根据客户施工图（或参考图）自动产出可进 Illustrator / 后续 Zünd 的向量刀模。大图订单项次已有宽高、后加工与小图，缺少「图片 + 订单上下文 → SVG」的全自动流水线。先把流程搭通，后续再按后加工类型微调 prompt。

## What Changes

- 在社区版 `dtsc` 的 `dtsc.checkoutline` 增加刀模相关字段：参考图（可复用/扩展现有小图）、生成的 SVG、结构化解析结果 JSON、生成状态与错误信息。
- 新增「生成刀模 SVG」动作：收集项次宽/高、后加工描述、属性、备注 + 图片，调用 GPT Vision，**无人工确认**直接产出 SVG。
- 新增后加工 prompt 配置（按后加工名称存可微调的 system/user prompt 片段），默认回退到通用 prompt。
- 新增 Geometry Engine：GPT 输出的结构化 JSON → 分层 SVG（CUT / CREASE / KISS / REMARK）；不确定参数（如搭接耳）由模板默认值补齐，不猜、不弹确认窗。
- 从环境变量 `GPT_API_KEY` 读取密钥（社区版），不依赖企业版 AI Gateway。

## Impact

- Affected specs: `checkout-cut-svg`（新增）
- Affected code: `custom-addons/dtsc`（模型、视图、工具模块）；可选独立 `utils/cut_svg/` 几何引擎
- 不改数据库业务资料的既有字段语义；仅新增字段与配置表
- 第一版只保证流水线跑通；几何精度与多产品模板后续迭代
