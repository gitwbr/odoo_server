## ADDED Requirements

### Requirement: 项次刀模上下文采集
系统 SHALL 从大图订单项次 `dtsc.checkoutline` 采集生成刀模所需上下文，至少包含宽、高、后加工描述、商品与属性、客户备注，以及项次上的刀模参考图。

#### Scenario: 项次具备参考图与尺寸时可采集
- **WHEN** 项次已填写 `product_width`、`product_height` 且已上传刀模参考图
- **THEN** 系统可组装完整生成上下文
- **AND** 后加工名称来自 `multi_chose_ids` 或 `aftermakepricelist_lines`

#### Scenario: 缺少参考图时拒绝生成
- **WHEN** 用户触发生成刀模 SVG 但项次无参考图
- **THEN** 系统拒绝执行并提示需要上传参考图

### Requirement: 全自动生成管线无人工确认
系统 SHALL 提供项次动作「生成刀模 SVG」，在一次调用内完成 Vision 解析、默认参数补齐与 SVG 生成，不插入人工确认步骤。

#### Scenario: 一键生成成功
- **GIVEN** 已配置可用的 `GPT_API_KEY`
- **AND** 项次已有参考图与宽高
- **WHEN** 用户点击「生成刀模 SVG」
- **THEN** 系统调用 GPT Vision 得到结构化 JSON
- **AND** 用后加工/产品模板默认值补齐不确定参数
- **AND** Geometry Engine 产出分层 SVG 并写回项次
- **AND** 不展示确认对话框

#### Scenario: 生成失败可追踪
- **WHEN** GPT 调用或几何生成失败
- **THEN** 项次记录失败状态与错误信息
- **AND** 用户可修正后重新触发

### Requirement: 后加工 Prompt 可配置
系统 SHALL 允许按后加工名称维护可微调的 prompt 片段与模板默认参数，未匹配时使用通用默认配置。

#### Scenario: 命中后加工专用 prompt
- **GIVEN** 配置表中存在与项次后加工名称匹配的记录
- **WHEN** 生成刀模 SVG
- **THEN** 系统使用该记录的 prompt 与默认参数

#### Scenario: 未命中时回退默认
- **GIVEN** 无匹配的后加工 prompt 配置
- **WHEN** 生成刀模 SVG
- **THEN** 系统使用通用默认 prompt 与通用模板默认参数

### Requirement: Geometry Engine 产出分层 SVG
系统 SHALL 根据结构化 JSON（而非 AI 描边）生成向量 SVG，并至少包含 CUT、CREASE、KISS 图层语义。

#### Scenario: 五面底座模板可生成
- **GIVEN** JSON 的 `product_type` 为支持的矩形五面底座类型，且含正面宽高与深度
- **WHEN** Geometry Engine 执行
- **THEN** 输出 SVG 含外切/板框与折线几何
- **AND** 搭接耳尺寸来自模板默认值而非模型臆造的不可复现数值

### Requirement: 社区版密钥读取
系统 SHALL 从运行环境变量 `GPT_API_KEY` 读取 OpenAI 兼容接口密钥，不依赖企业版 AI Gateway 模块。

#### Scenario: 未配置密钥
- **WHEN** 环境未设置 `GPT_API_KEY` 且用户触发生成
- **THEN** 系统提示缺少密钥并拒绝调用外部 API
