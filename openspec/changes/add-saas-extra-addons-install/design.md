## Context
SaaS tenants each have `instances/clientN/config/odoo.conf` and a docker-compose with `-u dtsc,dtsc_custom`. Restart today is only `docker restart` and does not install new modules. `is_open_*` flags are business toggles, not installers.

## Goals / Non-Goals
- Goals: conf-driven auto-install of optional addons on SaaS restart/start
- Non-Goals: auto-uninstall; changing `is_open_*` semantics; modifying shared `dtsc` for feature packs

## Decisions
- Decision: New key `extra_addons` (not `is_open_*`)
- Decision: Install via `docker compose run --rm --no-deps webN -i ... --stop-after-init` after stopping web, to avoid worker DB locks
- Decision: Query `ir_module_module.state` via db container `psql`; missing row = not installed
- Alternatives considered: only change compose `-u` list — does not install new modules; rejected

## Risks / Trade-offs
- Install can take minutes → API timeout UX; timeout set to 900s for the install subprocess
- Failed install may leave web stopped → restart/start handlers attempt `docker start` web on error
- Module not present in addons_path → install fails with clear error

## Open Questions
- Whether later to also `-u` already-installed extra_addons on every restart for code refresh
