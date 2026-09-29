## ADDED Requirements

### Requirement: Extra Addons Config
The system SHALL treat `extra_addons` in each tenant `odoo.conf` as a comma-separated list of optional Odoo module technical names to install. Removing a module from this list MUST NOT uninstall it.

#### Scenario: Parse module list
- **WHEN** `odoo.conf` contains `extra_addons = dtsc_cashflow, other_mod`
- **THEN** the SaaS API parses two modules: `dtsc_cashflow` and `other_mod`

#### Scenario: Empty or missing key
- **WHEN** `extra_addons` is absent or empty
- **THEN** restart/start proceeds without module install steps

### Requirement: Auto Install On Restart Or Start
When a user restarts or starts an instance via the SaaS API, the system SHALL ensure every module listed in `extra_addons` is installed in that tenant database if it is not already installed. Already-installed modules SHALL be skipped. Uninstall MUST NOT be triggered by this flow.

#### Scenario: Install missing module on restart
- **WHEN** a tenant has `extra_addons = dtsc_cashflow` and the module is not installed
- **AND** the user calls SaaS instance restart
- **THEN** the API installs `dtsc_cashflow` with `-i` / `--stop-after-init` before bringing the web container back up

#### Scenario: Skip already installed
- **WHEN** `extra_addons` lists a module that is already `installed`
- **THEN** the API does not reinstall it and continues with normal restart/start

#### Scenario: Remove from list does not uninstall
- **WHEN** a previously installed extra addon is removed from `extra_addons`
- **AND** the user restarts the instance
- **THEN** the module remains installed
