# IMS technical documentation

## Architecture

The application is one Python file with separate responsibilities: CLI functions collect input; `AuthService`, `InventoryService` and `ReportService` handle operations; `UserRepository` and `ItemRepository` provide reads. Service writes use parameterised SQL directly. This is logical separation within a single file, not separate deployable modules.

`db()` opens SQLite with foreign keys enabled and a 10-second busy timeout, then closes the connection. `transaction()` explicitly begins, commits on success and rolls back on exceptions. Plain `db()` does not commit writes automatically.

## Schema

| Table | Purpose | Key constraints |
|---|---|---|
| users | Username, password hash, role, active status, creation time | Case-insensitive unique username; admin/manager/staff role |
| items | Name, category, unit, quantity, cost/selling price, supplier, reorder threshold, timestamps | Case-insensitive unique name; permitted units; nonnegative numeric fields |
| stock_movements | Item/user, action, signed change, before/after quantities, unit, unit price, value, note, timestamp | Foreign keys; initial_stock/stock_in/stock_out/adjustment actions |
| audit_log | Actor, action, target and old/new text, timestamp | Optional user foreign key |

Old/new audit values are generally JSON text, but the password-change entry stores a plain string. Do not assume every field can be JSON-decoded.

## Permissions

| Operation | Admin | Manager | Staff |
|---|---|---|---|
| Add/update item | Yes | Yes | No |
| Stock in/out | Yes | Yes | Yes |
| Create/list users via CLI | Yes | No | No |
| Seed demo via menu | Yes | No | No |
| View/search/report through CLI | Yes | Yes | Yes |
| Physical deletion via service | Yes | No | No |

`delete_item()` has no menu entry and refuses deletion when stock movement history exists. Audit querying exists as a service method, with no CLI menu option. Read repositories/report services do not implement independent role checks.

## Typical workflow

Follow the [operator guide](OPERATOR_GUIDE.md) to create an admin, seed demo items, record movements, inspect low stock and export reports. Menu 6 keeps blank fields unchanged. Menu 10 changes your password. Stock-out values use the item's cost price, not sales revenue. The application is not a complete POS/accounting system.

Reports go into the active data directory's `reports/` folder with a timestamped name. An empty report contains `No records`. Same-prefix exports within one second can overwrite each other.

## Security controls and limits

Passwords require at least eight characters. Usernames are stripped, limited to 50 characters and cannot contain whitespace. Hashes contain algorithm, rounds, random 16-byte salt and digest. `hmac.compare_digest` compares hashes. There is no login rate limiting or password recovery workflow. Audit rows are mutable by someone with database access and are not tamper-proof.

## Security and correctness fixes on main

The current main branch persists successful-login audit rows, rejects non-finite quantities/prices/reorder thresholds, checks active status for role-restricted operations, rejects blank item names and fractional stock/reorder values when converting to whole-item units, and disables unauthenticated command-line demo seeding. Use authenticated admin menu 13 for fictional products. These fixes have focused regression coverage.

## Confirmed defects and remaining limitations

1. Failed logins are not audited; login rate limiting and recovery are not implemented.
2. Monetary fields use binary floating point and require an explicit precision design.
3. Backup/restore is not implemented. A created directory is not a backup; CSV exports cannot restore the database.
4. Concurrent-user races, migrations, session lifecycle and concurrent first-admin creation require further work.
5. The first-admin precheck occurs outside its write transaction.
6. Audit records can be modified by someone with database access and are not tamper-proof.
7. Report filenames can collide within one second; audit values do not have one consistent serialization format.

Stop the app before an ordinary database-file copy. A future backup workflow should use SQLite's backup API and validate restoration.

## Verification on current main

On 10 November 2026, the isolated database/schema smoke check and eight regression tests passed against the current source. Coverage includes login audit persistence, inactive accounts, invalid numeric inputs, discrete quantities, rejected deductions, unit conversions and item names. Tests use temporary data, not shop records. This is focused automated verification; it does not establish concurrency, recovery or full production readiness.

## Repository hygiene

Publish source and synthetic examples only. Do not commit `data/`, SQLite files, reports, backups, environment files or credentials. Never run `git add .` before inspecting staged filenames. Source import creates the data directories, so tests should use a temporary copy.
