## 1. 数据与配置

- [x] 1.1 `dtsc.checkoutline` 增加刀模字段：`cut_source_image`、`cut_svg_file`、`cut_svg_json`、`cut_svg_state`、`cut_svg_error`、`cut_svg_generated_at`
- [ ] 1.2 新增 `dtsc.cut.svg.prompt`（或 ir.config 级别）按后加工名称存 prompt 片段与模板默认参数（tab 等）
- [x] 1.3 安全权限：沿用 checkoutline 既有权限（字段挂在原模型）
- [x] 1.4 checkout「刀模生成」页：档名/宽/高/后加工、参考图、状态、下载 SVG、按钮「生成」

## 2. GPT 调用层

- [x] 2.1 从环境变量读取 `GPT_API_KEY`（可选 `GPT_BASE_URL` / `GPT_MODEL`；亦可 `dtsc.cut_svg.gpt_api_key`）
- [x] 2.2 组装上下文：宽、高、后加工、属性、备注、商品名 + 图片
- [ ] 2.3 按后加工匹配 prompt；无匹配用默认（第一版仅通用 prompt）
- [x] 2.4 调用 Vision，解析 JSON；失败回退订单尺寸

## 3. Geometry Engine

- [x] 3.1 实现 `rectangular_pedestal` + `rectangle_cut` JSON → 分层 SVG
- [x] 3.2 不确定参数用模板默认值补齐
- [x] 3.3 本地可导入 geometry 模块验证 SVG

## 4. 管线串联

- [x] 4.1 `checkoutline.action_generate_cut_svg`：后台线程 → GPT → merge defaults → Engine → 写回
- [x] 4.2 失败写 `cut_svg_state=error`；缺图 UserError；无 key 则 fallback
- [x] 4.3 成功可下载 SVG + HTML 预览

## 5. 验收

- [x] 5.1 固定订单尺寸可生成 rectangle_cut SVG
- [ ] 5.2 在测试库一项次上传图 + 点按钮跑通（需升级模块）
