订单业务事实（由项目 AGENTS.md 提供，不替代运行时模型与字段发现）：

A 是普通大图订单；F 是打样单，打样不是 A；E 是重制单（用户说「重置单」同义），表示重新制作，由原单指定产品行复制，保留原始单号线索；字段 `checkout_order_type=e`。
M 是合并标记，合并后非主目标单的产品行移入目标单，产品行保留来源母单关联；D 是 CRM/报价路径生成的单据（正式确认前多为「待确认」）。
**默认「大图订单」口径（与大图主菜单一致）**：`is_invisible=false`，且 `checkout_order_state != waiting_confirmation`。CRM「待确认」**不属于**大图订单查询范围，进单数、金额、逾期、未出货等一律排除；只有用户明确说查 CRM/待确认/报价单时才可纳入。
B 是内部工单，C 是委外工单，G 是代工单，T 是施工工单，从产品行的生产/施工需求生成并关联母单。

重制/重置单比例（只看大图订单，不看工单）：
| 用户说法 | 模型 | 条件 | metric |
|---|---|---|---|
| A 单数量 | dtsc.checkout | type=a + 大图主菜单口径 | `a_period_count` |
| 重制单 / 重置单 / 重新制作 | dtsc.checkout | type=e + 同上 | `e_period_count` |
| 重制/重置比例 | dtsc.checkout | E / 有效进单总数 | `rework_share` |

硬规则：
- 「重置单比例 / 重制单比例」= 大图 E 单，**禁止**查 `dtsc.makein` / 内部工单。回答须给出期间、A 单数、E（重置）单数，以及 E 占有效进单比例（或 E 相对 A 的对照）；不要只报一个工单笔数。
- 用户说重置即重制（E），不是工单重做。

CRM 转化率（D 转 A，不是 crm.lead）：
- CRM/报价路径单据 = 大图 **D 单**（`checkout_order_type=d`）。成单后 D **保留**，并通过 `related_checkout_id`（關聯大圖訂單）与对应 **A 单**互相关联。
- 「CRM转化率」优先 metric `crm_d_conversion_rate`：分母=期间建立的 D 单，分子=`related_checkout_id` 已填写（已转到 A）的 D 单。
- **禁止**用标准 `crm.lead` 笔数当转化率；**禁止**因默认排除「待确认」而把 D 单查成 0（D 成单后状态仍常为 waiting_confirmation）。
- 回答写明期间、D 单总数、已转化数、转化率 %；可附带说明关联字段为 related_checkout_id。
代工需求（make_om）同时产生 B 与 G 需求；工单需求允许重叠，统计母单数必须去重。
S 是独立出货单，可以关联一张或多张大图订单；母单也记录出货单号。出货单不是大图订单状态，S 已发送也不等于物流已签收。
大图订单逾期与出货单逾期不能直接视为同一指标。
业务关系、状态和来源字段必须通过本轮模型元数据核验，不从这些文字猜技术字段。

内部工单 vs 委外/外包比例（工厂内部订单与外包订单）：
| 用户说法 | 模型 | metric（期间笔数） | 排除 |
|---|---|---|---|
| 内部工单 / B / 工厂内部订单 | dtsc.makein | `b_period_count` | install_state=cancel |
| 委外工单 / C / 外包订单 | dtsc.makeout | `c_period_count` | install_state=cancel |

硬规则：
- 问「内部和委外/外包比例」时：同一期间各查一次上述笔数，回答 B 数、C 数、B:C 以及各自占 (B+C) 的百分比。**禁止**回答找不到来源。
- 这不是完成率（`b_completion_rate` / `c_completion_rate`）；未说明「未完成」时用期间进单数，不是 `b_open`/`c_open`。
- 默认期间：用户说最近 N 个月则用该范围；未说期间可先按最近三个月并写明起讫日。

大图订单金额（dtsc.checkout；与应收账单 account.move 不同）：

| 用户要查的指标 | 模型 | 金额字段 | 界面名 | 日期字段 | 状态范围 |
|---|---|---|---|---|---|
| 含税金额、含税总价、税后总价、订单金额合计 | dtsc.checkout | total_price_added_tax | 稅後總價 | create_date（进单日） | 排除 cancel、waiting_confirmation、隐藏 |
| 税前总额、未税总额（含施工） | dtsc.checkout | record_price_and_construction_charge | 稅前總額 | create_date | 同上 |
| 订单总价（产品行合计，偏税前且不含施工） | dtsc.checkout | record_price | 訂單總價 | create_date | 同上 |
| 单数 / 一共多少单 | dtsc.checkout | （record_count） | — | create_date | 同上；可用 metric checkout_count |

硬规则：
- 用户说「大图订单 + 含税金额/含税总价」即指 `total_price_added_tax`（稅後總價）。优先用 metric `checkout_tax_total`（带 period 时同时可得同口径单数 record_count）；或 describe 后 aggregate `sum(total_price_added_tax)`。
- **销售趋势 / 最近N个月走势 / 每个月多少**：对 `dtsc.checkout` 做 `period_analysis`（`analysis_mode=trend`，`granularity=month`，`date_field=create_date`，并保留大图主菜单口径 filters）。`measures` **必须**至少包含 `sum(total_price_added_tax)`（含税金额）与 `sum(unit_all)`（母单总才数）；单数可附带，但不能只出资料笔数。**禁止**只调用 `checkout_tax_total` 得到整段一个数后结束；**禁止**省略 measures 只看每月单数当销售趋势。
- **不得**用 `account.move.total_price` 回答大图订单金额；那是应收/应付账单口径。
- **不得**因界面字是「稅後總價」而非「含稅金額」就要求用户确认或声称缺少含税字段。
- 默认用 `total_price_added_tax`，不用 `total_price_added_tax_crm`（除非用户明确说 CRM/报价路径）。
- 已注释的旧字段 `total_price` 不存在，禁止再猜该字段名。
- 查「大图订单」时**禁止**返回 `waiting_confirmation`（待确认）单据；系统层也会自动排除。

大图订单逾期（与进单日无关）：
- 「逾期 / 逾期未出货」优先用 metric `checkout_overdue`（due_field=`estimated_date` 发货日期）。
- 列明细时 **必须** 包含 `estimated_date`（发货日期），以及单号、客户；进单日 `create_date` 可附带，但**不能**只列进单日代替发货日期。
- 逾期判断：未生成出货单（`is_delivery=false`）、未隐藏、状态不在作废/结案/待确认，且 `estimated_date` 早于当前时刻。
- 客户为空时表格显示「未填」，不是有客户搜不到。

产品（销售用 vs 采购用）：
本系统用同一套 `product.template`，以勾选区分用途，不是两套互斥主档：
| 用户说法 | 识别条件 | 实际落点 |
|---|---|---|
| 销售用产品 / 可销售 / 大图订单商品 | `sale_ok=true`（订单行 domain 亦含可费用化项） | 大图订单明细 `dtsc.checkoutline.product_id` → `product.template` |
| 采购用产品 / 可采购 / 原料耗材 | `purchase_ok=true` | 采购订单明细 `purchase.order.line.product_id` → `product.product`（模板常带「採購用」字样） |

硬规则：
- 「卖得最好 / 畅销 / 销量最好的产品」指**销售才数**：优先 metric `checkout_product_sales`——对 `dtsc.checkoutline` **按 `product_id` 分组**，期间内加总 `total_units`（总才数）；期间用母单 `checkout_product_id.create_date`。同指标附带 `price` 金额合计，但**排名以才数为准**。
- **禁止**用不分组的 search 列明细行、禁止把行 ID 当销量、禁止用标准 `sale.order` / `sale.order.line`。
- 用户明确说「按金额 / 按价钱」时，再改按 `price` 排序；未说明时一律按才数。
- 「采购最多 / 进货最多」才用 metric `purchase_product_spend`（`purchase.order.line`）。与大图销售不可混答。
- 只列产品主档时：销售清单筛 `sale_ok`，采购清单筛 `purchase_ok`；二者可重叠（少数模板两者皆真）。
- 回答用分组里的商品名称（product_id.display_name）+ 才数合计；不要把内部 id 当结论。

生产机台用量（大图明细行）：
- 每一行大图订单明细 `dtsc.checkoutline` 都有 `machine_id`（界面名**生產機台**），表示生产该产品所用机台（`dtsc.machineprice`）。
- 「机台用量 / 用量前五的机台」优先 metric `checkout_machine_usage`：按 `machine_id` 分组，加总 `total_units`（才数）排名，附带金额；期间用母单进单日。
- **禁止**追问用户选工作中心/工时/另张单据——默认就是明细行生产机台。用户明确说按金额或按笔数时再改排序依据。

开单人员排行（大图订单）：
- 字段 `kaidan`（界面名**開單人員**）→ `dtsc.userlistbefore`。与 `user_id`（銷售人員）不同，问开单人员用 `kaidan`。
- 「开单最多的人 / 按开单人员统计」优先 metric `checkout_kaidan_rank`：按 `kaidan` 分组，同时汇总 `unit_all`（总才数）与 `total_price_added_tax`（税后总价）；`record_count` 为开单笔数。期间用 `create_date`。
- 回答应同时给出才数、税后金额（及可选笔数）两个维度，不要只报一个人名却无金额/才数；**禁止**因口径不清而失败不查。

采购单据怎么抓（有采购单，也能查供应商）：
| 用户要查 | 模型 | 关键字段 | 说明 |
|---|---|---|---|
| 采购最多的材料/产品 | purchase.order.line | product_id、price_total；日期 order_id.date_order | metric `purchase_product_spend`；母单 state∈purchase/done |
| 供应商名称 | 同上明细的 partner_id（= 采购单 partner_id「供應商」） | 存儲 Many2one | metric `purchase_product_supplier_spend`，或 aggregate 再按 partner_id 分组 |
| 采购单张数/待收货 | purchase.order | partner_id、my_state、date_order | metric purchase_confirmed / purchase_pending_receipt |

硬规则：
- 采购数据来自**采购订单**及其明细，不是大图订单行。每笔明细都能通过 `partner_id` / `order_id.partner_id` 读到供应商名称。
- 用户同句问「采购最多的材料 + 供应商是谁」时：先 `purchase_product_spend` 定材料，再同期间、同 state、限定该 `product_id` 按 `partner_id` 汇总（或直接用 `purchase_product_supplier_spend` 报该材料金额最高的供应商）。**禁止**只答材料后说「供应商需另查」却不查；**禁止**声称采购单没有供应商字段。
- 材料总排行与「材料×供应商」组合排行不同：组合第一名未必等于「总采购最多的那一种材料」的第一供应商，须按上面两步口径回答。

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
