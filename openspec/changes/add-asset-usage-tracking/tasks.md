## 1. 数据模型
- [x] 1.1 新增 `dtsc.asset.category`（名称、排序、启用）
- [x] 1.2 新增 `dtsc.asset`（名称、类别、编号、启用、当前状态）
- [x] 1.3 新增 `dtsc.asset.usage`（资产、员工、LINE ID、开始/结束时间、时长、状态）
- [x] 1.4 约束：同一资产最多一条 `using`；结束时计算时长
- [x] 1.5 `__init__.py` / `__manifest__.py` 注册模型、视图、权限、静态资源（主档+记录+统计）

## 2. 后台维护
- [x] 2.1 类别 tree/form 菜单
- [x] 2.2 资产 tree/form 菜单（按类别筛选）
- [x] 2.3 使用记录 tree/form（只读为主，管理员可改）
- [x] 2.4 访问权限（管理组全权维护主档；base 组可读）

## 3. LINE 交互
- [x] 3.1 webhook：收到「資產使用」→ 推送类别 Flex
- [x] 3.2 postback `asset_cat` → 推送该类别资产 Flex
- [x] 3.3 postback `asset_pick` → 推送开始/结束操作卡（显示当前占用状态）
- [x] 3.4 postback `asset_start` → 开使用记录并回复结果
- [x] 3.5 postback `asset_end` → 关自己的使用中记录并回复时长
- [x] 3.6 未绑定员工、资产占用中、无进行中记录等错误提示

## 4. 统计页面
- [x] 4.1 菜单入口「資產使用統計」（報表目录，仅管理员）
- [x] 4.2 左栏：全部 / 类别 / 资产树，可点选筛选
- [x] 4.3 右栏：使用明细列表 + 合计时长（支持日期范围）
- [x] 4.4 RPC `get_usage_stats` 返回列表与汇总

## 5. 验收
- [ ] 5.1 后台可录入类别与资产
- [ ] 5.2 LINE 完整走通：选类→选资→开始→结束，库中有记录
- [ ] 5.3 统计页可按全部/类别/单资产查看，时长正确
- [x] 5.4 `openspec validate add-asset-usage-tracking --strict` 通过（提案阶段）
