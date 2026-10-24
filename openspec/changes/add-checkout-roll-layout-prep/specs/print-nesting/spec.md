## ADDED Requirements

### Requirement: Checkout Automatic Layout Tab for Roll Lines
The system SHALL, when `dtsc_print_nesting` is installed, show a notebook page「自動排版」on `dtsc.checkout` that lists only checkout lines whose resolved raw material is a roll (serial-tracked `make_ori_product_id` on product or attribute).

#### Scenario: Only roll-material lines appear
- **WHEN** a checkout has both roll-material and non-roll lines
- **THEN** the「自動排版」page SHALL list only the roll-material lines

### Requirement: Bleed Size Independent of Product Size
Each roll checkout line SHALL store `layout_bleed_width` and `layout_bleed_height` as fields independent of `product_width` / `product_height`, prefilled from product size when empty, and editable on the layout page.

#### Scenario: Prefill and edit bleed size
- **WHEN** a new checkout line is created with product width/height
- **THEN** bleed width/height SHALL default to those values
- **AND** changing bleed size SHALL NOT change product width/height

### Requirement: TIFF Upload Only
Roll checkout lines SHALL accept a layout image file that MUST use extension `.tif` or `.tiff`.

#### Scenario: Reject non-TIFF filename
- **WHEN** a user uploads a file whose name does not end with `.tif` or `.tiff`
- **THEN** the system SHALL raise a validation error

### Requirement: Gate Work-Order Conversion on Layout Completeness
When `dtsc_print_nesting` is installed, confirming a checkout via `in_out_check` SHALL require every roll-material line to have a TIFF uploaded and non-empty bleed width and height.

#### Scenario: Block confirm without TIFF
- **WHEN** a user clicks 訂單確認 and a roll line has no `layout_tiff`
- **THEN** the system SHALL raise UserError listing missing item sequences and SHALL NOT create work orders

#### Scenario: Module not installed
- **WHEN** `dtsc_print_nesting` is not installed
- **THEN** checkout confirmation SHALL behave as before with no layout checks
