## ADDED Requirements

### Requirement: Overview Menu Entry
The system SHALL provide a backend menu item named `概覽畫面` in the `印刷訂單系統` top menu, positioned after the existing `報表` menu.

#### Scenario: User opens overview menu
- **GIVEN** a user has permission to access the `dtsc` backend menus
- **WHEN** the user opens the `印刷訂單系統` top menu
- **THEN** the system SHALL display `概覽畫面` after `報表`
- **AND** selecting it SHALL open the overview page

#### Scenario: Phase 1 page shell
- **GIVEN** Phase 1 is implemented
- **WHEN** the user opens `概覽畫面`
- **THEN** the system SHALL show a dashboard shell with a clearly separated quick menu, filter area, KPI area, category chart area, ranking area, and alert area
- **AND** the system SHALL NOT require full statistical data to be implemented yet

### Requirement: Phased Delivery
The system SHALL deliver the overview dashboard in multiple phases, with Phase 1 limited to menu and page shell creation.

#### Scenario: Phase 1 scope
- **WHEN** Phase 1 is implemented
- **THEN** the system SHALL only add the menu entry, page action, permissions, and visual shell
- **AND** the system SHALL avoid heavy data aggregation

#### Scenario: Later phases
- **WHEN** Phase 2 or later is implemented
- **THEN** the system SHALL add data blocks according to the approved phase plan
- **AND** each data block SHALL declare its source model and metric口徑

### Requirement: Quick Menu And Filter Separation
The system SHALL visually separate quick navigation menus from global filters.

#### Scenario: Quick menu is separate from filters
- **WHEN** the overview page is displayed
- **THEN** the system SHALL show a quick menu for major business areas such as total overview, big orders, work order status, receivables/payables, purchase, star products, material consumption, people/administration, and alerts
- **AND** the system SHALL show filters in a separate area for date range, customer, salesperson, product, category, and status

#### Scenario: Menu category chart groups
- **WHEN** a user selects or navigates to a quick menu category
- **THEN** the system SHALL present multiple chart blocks for that business category
- **AND** the chart blocks SHALL be visually more technology-oriented than plain Odoo native lists while still fitting the backend layout

### Requirement: Big Order Metrics
The system SHALL support overview metrics for `dtsc.checkout` big orders.

#### Scenario: Big order KPI
- **WHEN** the overview loads big order metrics
- **THEN** the system SHALL be able to show order count, order state distribution, order type distribution, untaxed amount, tax amount, total amount, total quantity, total units, mother-order delivery progress, and overdue-not-delivered count
- **AND** the metrics SHALL be based on `dtsc.checkout` fields such as `checkout_order_state`, `checkout_order_type`, `record_price_and_construction_charge`, `tax_of_price`, `total_price_added_tax`, `quantity`, `unit_all`, `estimated_date`, and `is_delivery`

### Requirement: Delivery Metrics
The system SHALL support delivery detail analysis as an extension of big-order delivery metrics.

#### Scenario: Delivery KPI
- **WHEN** the overview loads delivery metrics
- **THEN** the system SHALL be able to show delivery detail source distribution, delivery quantity, delivery units, and delivery method distribution when the delivery detail extension is implemented
- **AND** the metrics SHALL be based on `dtsc.deliveryorder`, `dtsc.deliveryorderline.make_orderid`, and linked `dtsc.checkout` records
- **AND** S delivery detail analysis SHALL NOT replace the mother-order delivery metrics because B/C/G/T records are downstream extension orders, not replacements for the original checkout

### Requirement: Work Order Status Metrics
The system SHALL support overview metrics for B/C/G/T downstream work orders generated from big orders.

#### Scenario: Work order KPI
- **WHEN** the overview loads work order status metrics
- **THEN** the system SHALL be able to show B internal work order, C outsourcing work order, G subcontract order, and T installation order demand, generated count, pending conversion count, pending completion count, completed count, and status distribution
- **AND** the metrics SHALL use `dtsc.checkoutline` demand flags and downstream models linked by `checkout_id`

### Requirement: Receivable Metrics
The system SHALL support overview metrics for receivable invoice amounts.

#### Scenario: Receivable KPI
- **WHEN** the overview loads receivable metrics
- **THEN** the system SHALL be able to show receivable invoice count, receivable total, receivable trend, and receivable customer ranking
- **AND** the metrics SHALL be based on `account.move` records where `move_type = out_invoice`, scoped by `invoice_date`, using `total_price`/`amount_total_signed` and `partner_id`
- **AND** the system SHALL NOT present unpaid/paid progress for receivables unless a real collection workflow is introduced

### Requirement: Purchase Metrics
The system SHALL support overview metrics for purchase orders.

#### Scenario: Purchase KPI
- **WHEN** the overview loads purchase metrics
- **THEN** the system SHALL be able to show purchase order count, purchase amount, purchase status distribution, and supplier ranking
- **AND** the metrics SHALL be based on Odoo `purchase.order` and `purchase.order.line`

### Requirement: Payable Metrics
The system SHALL support overview metrics for vendor bill amounts and receivable/payable comparison.

#### Scenario: Payable KPI
- **WHEN** the overview loads payable metrics
- **THEN** the system SHALL be able to show vendor bill count, payable total, payable trend, receivable/payable amount comparison, and payable supplier ranking
- **AND** the metrics SHALL be based on `account.move` records where `move_type = in_invoice`, scoped by `invoice_date`, using `total_price`/`amount_total_signed` and `partner_id`
- **AND** the system SHALL NOT present unpaid/paid progress for payables unless a real payment workflow is introduced

### Requirement: People Administration Summary Metrics
The system SHALL support management-level summary metrics for personnel administration reports without replacing detailed reports.

#### Scenario: People administration summary
- **WHEN** the overview loads people administration metrics
- **THEN** the system SHALL be able to show employee performance hours, attendance summary, leave summary, and salary summary at an overview level
- **AND** the system SHALL NOT expose detailed personnel data beyond the user's allowed backend permissions

### Requirement: Star Product Metrics
The system SHALL support ranking metrics for star products.

#### Scenario: Star products
- **WHEN** the overview loads product rankings
- **THEN** the system SHALL be able to rank products by sales amount, total units, and quantity
- **AND** the metrics SHALL be based on `dtsc.checkoutline.product_id`, `dtsc.checkoutline.price`, `dtsc.checkoutline.total_units`, and `dtsc.checkoutline.quantity`

### Requirement: Fast Material Consumption Metrics
The system SHALL support a first-version metric for fastest material consumption using order-line usage data.

#### Scenario: Material usage ranking
- **WHEN** the overview loads material consumption ranking
- **THEN** the system SHALL rank materials/products by order-line usage amount, total units, and quantity
- **AND** the system SHALL label the first-version metric as based on order-line usage rather than actual inventory deduction

#### Scenario: Future stock consumption
- **WHEN** the business requires actual stock consumption ranking
- **THEN** the system SHALL require a separate口徑 definition based on stock movement data before implementation

### Requirement: Technology-Oriented Visual Design
The system SHALL present overview data with a modern technology-oriented dashboard design rather than plain Odoo native icon blocks.

#### Scenario: Dashboard visual style
- **WHEN** the overview page is displayed
- **THEN** the system SHALL use visually distinct KPI cards, status colors, trend charts, rankings, and exception lists
- **AND** the layout SHALL prioritize quick comprehension of statistical results

### Requirement: Drilldown And Traceability
The system SHALL make statistical results traceable to their source records.

#### Scenario: KPI drilldown
- **WHEN** a user clicks a supported KPI or chart segment
- **THEN** the system SHALL open the related Odoo list view with matching filters where practical

#### Scenario: Source口徑 visibility
- **WHEN** a metric uses an estimated or fallback口徑
- **THEN** the system SHALL display enough label or tooltip information to avoid confusing it with another business meaning

### Requirement: Permissions
The system SHALL protect overview access with existing `dtsc` backend permissions.

#### Scenario: Authorized user
- **GIVEN** a user belongs to an allowed `dtsc` backend group
- **WHEN** the user opens `概覽畫面`
- **THEN** the system SHALL allow access according to the user's role

#### Scenario: Unauthorized user
- **GIVEN** a user does not belong to an allowed `dtsc` backend group
- **WHEN** the user attempts to access `概覽畫面`
- **THEN** the system SHALL deny access or hide the menu
