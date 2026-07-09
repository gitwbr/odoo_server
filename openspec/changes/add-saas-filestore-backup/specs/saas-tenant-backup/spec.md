## ADDED Requirements

### Requirement: Complete Tenant Backup Set
The system SHALL back up both the PostgreSQL database and the corresponding Odoo
filestore for every active SaaS tenant.

#### Scenario: Complete backup succeeds
- **WHEN** the scheduled tenant backup runs successfully
- **THEN** it creates a database dump and filestore archive with the same timestamp
- **AND** both artifacts are stored in the tenant backup directory

#### Scenario: One artifact fails
- **WHEN** either the database dump or filestore archive cannot be created or validated
- **THEN** the system SHALL report the backup set as failed
- **AND** it SHALL remove partial artifacts from that attempt

### Requirement: Backup Set Retention
The system SHALL retain the latest three complete backup sets for each active
tenant.

#### Scenario: New complete set exceeds retention
- **WHEN** a fourth complete backup set is created successfully
- **THEN** the oldest complete database dump and matching filestore archive are removed

#### Scenario: New backup fails
- **WHEN** creation of a new backup set fails
- **THEN** existing complete backup sets SHALL remain unchanged

### Requirement: Complete Tenant Restore
The system SHALL support restoring a database dump together with its matching
filestore archive.

#### Scenario: Matching set is restored
- **WHEN** an operator selects matching database and filestore backup artifacts
- **THEN** the tenant web container is stopped during restoration
- **AND** the database and `filestore/default` are restored from the selected set
- **AND** the tenant web container is restarted after restoration

#### Scenario: Backup artifacts do not match
- **WHEN** the database dump and filestore archive timestamps do not match
- **THEN** the restore SHALL stop before modifying the tenant

