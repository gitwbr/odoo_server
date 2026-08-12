<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->
# 重要遵循规则
 所有改动没经过允许不能直接改数据库资料，首先以及纯代码改动，不行再找ui设置方案，还是没办法再讨论是否直接改数据库。

# 大图订单-单号类型

A：普通大图订单主单，模型是 dtsc.checkout。
F：打樣單。代码里是 is_dayang=True 时把 A 改成 F，所以打样不是 A。
E：重製單。由原大图订单复制指定产品行生成，保留 source_name。
M：合併單标记。合并时非主目标订单会从 A 改成 M，产品行会移到目标订单，并用 origin_checkout_id 记录原订单。
D：CRM/报价相关生成的大图订单类型，代码里存在。
B：內部工單，模型 dtsc.makein，由产品行 is_purchse = make_in 或 make_om 生成。
C：委外工單，模型 dtsc.makeout，由产品行 is_purchse = make_out 生成。
G：代工單，模型 dtsc.makeom，只由产品行 is_purchse = make_om 生成。
T：施工工單，模型 dtsc.installproduct，由产品行 is_install=True 生成。
S：出貨單，模型 dtsc.deliveryorder，可以关联一张或多张大图订单。
关系

A/F/E/M/D 都属于大图订单主模型：dtsc.checkout。
B/C/G/T 是从大图订单的产品行生成出来的生产/施工单，核心关联字段是 checkout_id。
make_om 产品行会同时进入 B 内部工单需求和 G 代工单需求；统计 B/G 需求时允许重叠，统计母单数量时需要按 checkout_id 去重。
S 是出货单，核心关联是 dtsc.deliveryorder.checkout_ids，同时大图订单上也会写 delivery_order = Sxxxxx。
出货单不是大图订单状态，它是独立单据；所以“大图订单逾期”和“出货单逾期”不能直接用同一个数字对比。

# 环境说明
 1：这里存放的是企业版（测试环境）以及 saas社区版
 2：企业版（正式环境） 没有docker，不在当前服务器，启动方式是
    source odoo16/bin/activate
    nohup python3 ./odooE/odoo-bin -w odoo -r odoo -c /home/bryant/odooE/config/odoo.conf > odoo.log 2>&1 &

 