## ADDED Requirements

### Requirement: Print pool shows all active lots for the material
The print pool SHALL list every non-archived `stock.lot` of the selected roll material. Lots with nested content (history pieces or pending pieces) SHALL appear above empty lots. Empty lots SHALL remain visible for inspection and archive actions but MUST NOT be used as a packing target when capacity is zero.

#### Scenario: Operator opens a material with multiple rolls
- **WHEN** the operator selects a material that has three lots (two with print history, one virgin empty)
- **THEN** the pool shows three strips ordered content-first then empty
- **AND** packing prefers leftover capacity before virgin capacity

### Requirement: Archive exhausted roll from print pool
The system SHALL provide a “材料耗盡” action on a lot strip that marks the lot as print-archived. Archived lots MUST NOT appear in the active print pool. The system SHALL provide a list view to search all archived print lots.

#### Scenario: Operator archives a finished roll
- **WHEN** the operator clicks 材料耗盡 on a lot strip and confirms
- **THEN** the lot is marked print-archived with timestamp and user
- **AND** the lot disappears from the active pool layout
- **AND** the lot appears in the archived lots list

### Requirement: Print order consumes stock instead of barcode lotmpr scan
When print-nesting auto-deduct is enabled, confirming (or creating, per approved design) a print order that binds a `stock.lot` SHALL create the stock consumption for the used/cutoff length on that lot, and related make-in lines SHALL be treated as already deducted (`is_stock_off`). The legacy 捲料扣料表 scan entry point SHALL be hidden or disabled for this flow to prevent double deduction.

#### Scenario: Generate print order deducts roll stock
- **WHEN** auto-deduct is enabled and the operator generates and confirms a print order with cutoff length on a bound lot
- **THEN** stock is moved from the lot’s internal location to production for the consumed quantity
- **AND** related makeinline barcodes are marked deducted
- **AND** make-in stock-in no longer requires scanning that line in 捲料扣料表

#### Scenario: Legacy scan menu hidden when auto-deduct on
- **WHEN** the system parameter for print-nesting auto-deduct is enabled
- **THEN** the 捲料扣料表 menu is hidden (or unavailable for print-roll materials)
