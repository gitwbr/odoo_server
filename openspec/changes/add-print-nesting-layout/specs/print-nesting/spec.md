## ADDED Requirements

### Requirement: Print Nesting Module Isolation
The system SHALL provide an installable Odoo module `dtsc_print_nesting` that depends on `dtsc` and does not alter core checkout/makein state machine behavior when the module is not installed.

#### Scenario: Module installable on target tenant
- **WHEN** an administrator installs `dtsc_print_nesting` on client109
- **THEN** print-order menus and models become available without requiring changes to other tenants

#### Scenario: Uninstalled tenant unaffected
- **WHEN** the module is not installed on a database
- **THEN** internal work order creation and material deduction continue to work as before

### Requirement: Print Order As Primary Document
The system SHALL treat `dtsc.print.order` (印刷單) as the primary document that collects unproduced roll-print demands and produces an optimized layout for factory printing.

#### Scenario: Create print order from pending pool
- **WHEN** a user selects pending unproduced nesting-candidate makeinline records that share the same roll material
- **THEN** the system creates one print order containing those demands as order lines

#### Scenario: Auto nest pending content
- **WHEN** a user runs auto-nest on a draft print order
- **THEN** the system optimally places outstanding quantities onto one or more print rolls and records each rectangle

### Requirement: Identify Nesting Candidates
The system SHALL mark internal work order lines (`dtsc.makeinline`) as print candidates when their resolved raw material uses serial tracking, and SHALL expose a pending pool of lines that are not fully placed on a confirmed print order and whose makein is not finished or cancelled.

#### Scenario: Serial material line is a candidate
- **WHEN** a makeinline resolves to a raw material with `tracking == 'serial'`
- **THEN** the line is marked as needing print nesting by default

#### Scenario: Fully placed line leaves pending pool
- **WHEN** a makeinline quantity is fully placed on confirmed print orders
- **THEN** the line no longer appears as selectable pending demand for new print orders

#### Scenario: Manual override
- **WHEN** a user clears or sets the nesting-needed flag on a line
- **THEN** the system respects the override for subsequent print order creation

### Requirement: One Trackable Layout Record Per Roll
The system SHALL persist each physical/logical roll layout as one `dtsc.print.roll` record that owns its placed rectangles, remains openable for later traceability, and can be visualized in the UI without requiring an external image file as the source of truth.

#### Scenario: Each roll is a first-class record
- **WHEN** auto-nest creates placements that span multiple rolls
- **THEN** the system creates one `dtsc.print.roll` per roll with its own piece set and used length

#### Scenario: Layout stored as structured pieces
- **WHEN** pieces are placed on a roll
- **THEN** each piece stores coordinates, size, rotation, makeinline link, and a label of work-order-number plus line sequence

#### Scenario: UI shows rectangles with labels
- **WHEN** a user opens a print roll or its parent print order
- **THEN** the UI renders each placed rectangle and displays the work-order-plus-line label inside or on the rectangle

#### Scenario: Historical traceability
- **WHEN** a user later opens a confirmed print roll
- **THEN** the same arrangement and piece-to-makeinline links remain available for review

### Requirement: Roll Width Master Data
The system SHALL store roll width on the product template for roll materials and SHALL snapshot that width onto each print order and print roll when created.

#### Scenario: Missing roll width blocks auto-nest
- **WHEN** a user starts auto-nesting for a material without roll width
- **THEN** the system refuses to compute and prompts to set the roll width

#### Scenario: Order keeps width snapshot
- **WHEN** a print order is created from a material that has roll width
- **THEN** the order and its rolls store the width snapshot used for placement even if the product master changes later

### Requirement: Print Order Lifecycle
The system SHALL support draft collection, computed nesting, manual edit of unlocked pieces, user reservation lock, and printed finalization for actual shop-floor processing.

#### Scenario: Manual adjustment of open pieces
- **WHEN** a user edits coordinates, rotation, or target roll of a piece in `open` lock state
- **THEN** the roll recalculates used length and utilization and the piece remains editable

#### Scenario: Reserved pieces are read-only until unlocked
- **WHEN** a piece is in `reserved` lock state
- **THEN** its position cannot be edited until the user unlocks it back to `open`

#### Scenario: Printed pieces are permanently immutable
- **WHEN** a piece is marked `printed`
- **THEN** its position and lock state cannot be changed and it cannot be unlocked

### Requirement: Piece Lock States
The system SHALL maintain per-piece lock states `open`, `reserved`, and `printed`, where `open` may move during re-nest, `reserved` is user-protected before actual printing, and `printed` means actual printing is done.

#### Scenario: User reserves placed but unprinted pieces
- **WHEN** a user selects placed pieces that are not yet printed and chooses lock/reserve
- **THEN** those pieces become `reserved` and keep their coordinates on subsequent re-nests

#### Scenario: User unlocks reserved pieces
- **WHEN** a user unlocks `reserved` pieces that are not printed
- **THEN** those pieces return to `open` and may move on the next re-nest

#### Scenario: Mark roll or pieces as printed
- **WHEN** a user marks selected pieces or an entire roll as printed
- **THEN** those pieces become `printed` and represent actual processed layout

### Requirement: Change-Triggered Re-Nest
The system SHALL mark affected print orders as needing re-nest when new eligible work-order lines appear for inclusion or when included lines change size or quantity, and SHALL re-optimize only unlocked pieces while treating reserved and printed pieces as fixed obstacles.

#### Scenario: New work order dirties related material plan
- **WHEN** a new makeinline becomes a pending print candidate for a material that already has an open print order policy for re-nest
- **THEN** the related print order is marked `need_renest` for user action

#### Scenario: Size or quantity change dirties print order
- **WHEN** width, height, or quantity of a makeinline included in a print order changes
- **THEN** the print order is marked `need_renest`

#### Scenario: Re-nest preserves locked positions
- **WHEN** a user runs re-nest on a dirty print order
- **THEN** pieces in `reserved` or `printed` keep their coordinates and `open` pieces plus new demand are re-packed around them

#### Scenario: Printed demand change does not move printed pieces
- **WHEN** a makeinline linked only to `printed` pieces has a conflicting size change
- **THEN** the system does not move those printed pieces and raises a warning for manual residual handling

#### Scenario: No silent automatic re-nest in V1
- **WHEN** a dirty trigger occurs
- **THEN** the system does not silently rewrite piece coordinates without an explicit user re-nest action

### Requirement: Material-Saving Placement Rules
The nesting engine SHALL place rectangular pieces on a fixed-width roll to minimize estimated used length, respect configured gap/margin, and optionally allow 90-degree rotation when enabled.

#### Scenario: Pieces fit within roll width
- **WHEN** auto-nest places a piece
- **THEN** the piece's width across the roll MUST NOT exceed roll width minus margins

#### Scenario: Oversized piece rejected
- **WHEN** a piece's both orientations exceed the usable roll width
- **THEN** the engine leaves it unplaced and reports it on the print order

#### Scenario: Same-size strip preference
- **WHEN** multiple identical pieces are nested
- **THEN** the engine SHOULD prefer packing them in equal-height shelves along the roll

### Requirement: Factory Nesting Output
The system SHALL provide a printable report per print roll showing width, estimated used length, and labeled piece list for shop-floor guidance.

#### Scenario: Print confirmed roll
- **WHEN** a user prints a confirmed print order or roll
- **THEN** the report includes one section per roll with piece labels (work-order line identity), sizes, and positions

### Requirement: Non-Blocking Production Integration
Until explicitly configured otherwise, print orders SHALL NOT block makein production state transitions.

#### Scenario: Making without nesting still allowed
- **WHEN** a makein has unplaced print-candidate lines and nesting is not configured as mandatory
- **THEN** the user can still move the makein through existing production states
