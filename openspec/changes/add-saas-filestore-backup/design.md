## Context
Odoo stores attachment metadata in PostgreSQL and attachment content under the
tenant data directory at `filestore/<database>`. Restoring only one side can leave
attachments missing or mismatched.

## Goals / Non-Goals
- Goals: produce and restore consistent, timestamp-matched database and filestore
  backup sets for active SaaS tenants.
- Non-Goals: remote replication, encryption, incremental backups, or changing the
  tenant activation policy.

## Decisions
- Create a compressed tar archive from the web container's configured
  `filestore/default` directory.
- Use one generated timestamp for both artifacts.
- Mark a set successful only when both artifacts pass basic format validation.
- Run retention after successful creation and delete artifacts by backup-set
  timestamp, keeping the latest three complete sets.
- Restore filestore while the tenant web container is stopped and replace only the
  target database's filestore directory.

## Risks / Trade-offs
- Filestore archives can be large and increase backup duration and disk usage.
- Database and filestore writes are not transactionally frozen together. Stopping
  the web container during scheduled backup would improve consistency but cause
  daily downtime; this proposal keeps the current online backup behavior.
- A restore is destructive to the target tenant, so isolated restore verification
  is required before production use.

## Migration Plan
Existing database-only backups remain available. New complete backup sets use
matching timestamps and are managed independently until old database-only files
age out under the revised retention policy.

