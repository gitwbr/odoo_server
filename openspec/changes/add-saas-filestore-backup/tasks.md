## 1. Implementation
- [ ] 1.1 Add timestamp-matched filestore archive creation to tenant backup.
- [ ] 1.2 Make backup-set success and cleanup operate on database/filestore pairs.
- [ ] 1.3 Add matching filestore restoration with safe temporary extraction.
- [ ] 1.4 Add clear logging and cleanup for partial backup and restore failures.

## 2. Verification
- [ ] 2.1 Test backup creation against one non-production tenant.
- [ ] 2.2 Verify the database dump with `pg_restore --list`.
- [ ] 2.3 Verify the filestore archive and compare representative attachment files.
- [ ] 2.4 Test restoring both artifacts into an isolated tenant.

