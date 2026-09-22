## Implementation
- [x] 1. Add bounded, authenticated gateway state tracking and actual execution events.
- [x] 2. Bind Odoo progress reads to the authenticated database/user/request and whitelist responses.
- [x] 3. Render friendly pending status and elapsed time with lifecycle cleanup.
- [x] 4. Run simulated regression checks and reload only community services.

## Validation results
- Gateway: 63 simulated tests passed, no network access.
- Odoo: 91 isolated tests passed, no registry/database or provider calls.
- Frontend: 4 progress tests and 8 conversation tests passed; access/rendering checks passed.
- OpenSpec strict validation and git diff whitespace check passed.
- Community gateway/web reloaded; gateway health OK and login page HTTP 200.
