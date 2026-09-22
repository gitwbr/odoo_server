订单业务事实（由项目 AGENTS.md 提供，不替代运行时模型与字段发现）：

A 是普通大图订单；F 是打样单，打样不是 A；E 是重制单，由原单指定产品行复制，保留原始单号线索。
M 是合并标记，合并后非主目标单的产品行移入目标单，产品行保留来源母单关联；D 是 CRM/报价相关生成的大图订单。这些均属于大图订单主单。
B 是内部工单，C 是委外工单，G 是代工单，T 是施工工单，从产品行的生产/施工需求生成并关联母单。
代工需求（make_om）同时产生 B 与 G 需求；工单需求允许重叠，统计母单数必须去重。
S 是独立出货单，可以关联一张或多张大图订单；母单也记录出货单号。出货单不是大图订单状态，S 已发送也不等于物流已签收。
大图订单逾期与出货单逾期不能直接视为同一指标。
业务关系、状态和来源字段必须通过本轮模型元数据核验，不从这些文字猜技术字段。

客户与供应商身份（DTSC res_partner.py 的实际定义）：
res.partner 的 customer_rank > 0 表示客户，supplier_rank > 0 表示供应商，两者可以重叠。
is_customer / is_supplier 是上述排名条件的计算显示值，没有搜索方法，不能用作筛选；active 或 is_company 也不能替代客户/供应商身份。
列候选时仍须 discover、describe，并保留对应 rank > 0 的身份条件，不可因显示字段不可搜索而改列全部联系人。

财务业务定义（DTSC 账单界面及概览的实际口径；维护理由见统一文档 B03）：

默认字段对照：
| 用户要查的指标 | 模型 | 金额字段 | 日期字段 | 单据类型 | 状态范围 |
|---|---|---|---|---|---|
| 应收总额、应收总共多少钱 | account.move | total_price | invoice_date | out_invoice | **禁止**加 state；全部状态，含草稿 |
| 应付总额、应付总共多少钱 | account.move | total_price | invoice_date | in_invoice | **禁止**加 state；全部状态，含草稿 |
| 应收/应付未税总额 | account.move | sale_price | invoice_date | 按应收或应付选择上述类型 | **禁止**加 state；全部状态，含草稿 |
| 标准发票原始金额（只有用户明确这样要求） | account.move | amount_total | invoice_date | 按用户要求 | 按用户要求 |

DTSC 二次开发硬规则（本项目没有标准 Odoo「过账」业务流作为应收门槛）：
- `move_type=out_invoice` 即客户应收单据；`move_type=in_invoice` 即供应商应付单据。出现在 account.move 且类型正确的就是应收/应付，不要再猜 state。
- 问「某月应收一共多少 / 应收总额」时：只要 `out_invoice` + `invoice_date` 期间 + `sum(total_price)`。**不得**自行添加 `state=posted`、`payment_state` 或「已过账」类过滤。
- 只有用户明确说「已过账 / posted」时，才可加 state。OpenAI 或本地模型都一样，默认口径不含过账条件。
- 「未收余额 / 还欠多少」才是另一口径（receivable_open：posted + amount_residual>0），与「期间应收总额」不要混用。
- **总额/一共多少/合计** 属于数字汇总：discover → describe 后必须用 **aggregate**（或 metric）直接出总数。**禁止**对本问题做 search 列发票号，也**禁止** action=select 让用户挑单。select 只用于用户要先选客户名/供应商名/某一张具体单再查下游资料的场景。

应收总额和应付总额使用 total_price。amount_total 不符合本项目默认业务口径，即使历史回答使用了 amount_total，也必须重新按 total_price 查询。这两个字段的税额算法不同，不能互换。
这张表是业务定义，不是查询结果；禁止使用历史答案数值。仍须本轮 discover、describe 核对实际模型与字段，再执行查询。
同一口径也适用于应收/应付趋势、最近几个月、逐月金额以及期间比较。每次应收查询均须带 move_type=out_invoice，应付查询均须带 move_type=in_invoice；period_analysis 也通过 filters 或 conditions 传入，不能省略后汇总整张账单表。历史失败查询或修正日期/模式时遗漏的条件，不能作为新口径沿用。

金额规则：total_price = sale_price + tax_price。sale_price 来自公司币种的 amount_untaxed_signed 经取整，tax_price 按项目发票形式及取整规则计算；这三个业务字段使用公司币种。读取 company_currency_id 确认单位，按 company_id 分组（company_currency_id 本身不可分组），不得混币种加总。
概览按每笔金额绝对值求和；可分别聚合字段 >= 0 和 < 0 两组，用非负合计减负值合计。不能先求和后取绝对值，不得从分页明细估总额。
“未收/未付余额”“历史期末余额”和上述期间账单总额是不同指标，须另核对相应口径。用户明确指定的状态或日期优先；仅指定“已过账”只改变状态范围，不自动改换金额字段。
当前未收/未付余额沿用 receivable_open / payable_open 的已过账、剩余金额大于 0 的单据范围；查询金额时按客户/供应商汇总 amount_residual，并按公司、currency_id 区分币种。这是当前原始账单剩余未结清金额，不含草稿，不是历史时点余额或抵扣贷记单后的往来净额。
回答仅简短注明账单含税金额、含草稿等业务范围。字段和条件放 AI Gateway Log，不显示技术口径区块。
