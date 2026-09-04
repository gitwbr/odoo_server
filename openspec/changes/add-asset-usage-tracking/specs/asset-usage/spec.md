## ADDED Requirements

### Requirement: Asset Master Data
The system SHALL allow administrators to maintain asset categories and assets in the Odoo backend.

#### Scenario: Create category and asset
- **WHEN** an administrator creates a category and an asset linked to that category
- **THEN** both records are stored as active and appear in LINE selection lists

#### Scenario: Inactive assets hidden from LINE
- **WHEN** an asset or category is set inactive
- **THEN** it MUST NOT appear in LINE Flex selection lists

### Requirement: LINE Asset Usage Session
The system SHALL let bound employees start and end asset usage via the employee LINE Bot using Flex messages and postbacks.

#### Scenario: Open category list from rich menu
- **WHEN** a bound employee sends the message `資產使用`
- **THEN** the bot replies with a Flex list of active categories

#### Scenario: Select asset and show action buttons
- **WHEN** the employee selects a category then an asset via postback
- **THEN** the bot shows Start Use and End Use actions for that asset

#### Scenario: Flex shows asset status and current user
- **WHEN** the bot lists assets in a category Flex
- **THEN** each asset shows idle or in-use status, and if in-use it shows who is using it

#### Scenario: Start usage
- **WHEN** the employee taps Start Use on an idle asset
- **THEN** the system creates a usage record with start time and state `using`

#### Scenario: End usage
- **WHEN** the employee who started the session taps End Use
- **THEN** the system sets end time, computes duration, and sets state `done`

#### Scenario: Exclusive in-use asset
- **WHEN** an asset already has an open `using` session
- **THEN** another employee MUST NOT start a new session on the same asset and MUST receive a clear error message

#### Scenario: Unbound LINE user
- **WHEN** an unbound LINE user triggers asset usage
- **THEN** the bot MUST prompt them to bind an employee account first

### Requirement: Asset Usage Statistics Page
The system SHALL provide a backend statistics page with a left filter panel and a right usage detail panel.

#### Scenario: View all usage
- **WHEN** an administrator opens the statistics page and selects All
- **THEN** the page lists all usage records with start time, end time, user, asset, and duration

#### Scenario: Filter by category or asset
- **WHEN** the administrator selects a category or a single asset in the left panel
- **THEN** the right panel shows only matching usage records and the summed duration for the current filter

#### Scenario: Date range filter
- **WHEN** the administrator applies a date range
- **THEN** only usage records overlapping that range are included in the list and totals
