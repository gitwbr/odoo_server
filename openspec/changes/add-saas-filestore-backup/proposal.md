# Change: Add SaaS Filestore Backup

## Why
Current SaaS tenant backups contain only PostgreSQL data. Odoo attachments stored in
`filestore/default` cannot be recovered consistently from those backups.

## What Changes
- Back up each active tenant's `filestore/default` with the database dump.
- Give the database dump and filestore archive the same timestamp.
- Treat the database dump and filestore archive as one backup set.
- Retain the latest three complete backup sets only after a new set succeeds.
- Extend tenant restore support to restore a matching filestore archive.
- Log partial failures and never report an incomplete set as successful.

## Impact
- Affected specs: `saas-tenant-backup`
- Affected code:
  - `www/html/api/utils/backup_db.py`
  - `www/html/api/utils/scheduler.py`
  - `www/html/api/utils/restore_db.py`
- Storage usage will increase according to tenant attachment volume.

