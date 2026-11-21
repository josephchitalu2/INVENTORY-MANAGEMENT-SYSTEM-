# IMS technical documentation

## Architecture

The CLI and inventory engine live in `ims.py`. CLI functions collect input, services handle operations, and repositories provide reads. Service writes use parameterised SQL. The Flask demo in `app.py` calls the same inventory engine.

`db()` opens SQLite with foreign keys enabled and a 10-second busy timeout, then closes the connection. `transaction()` explicitly begins, commits on success and rolls back on exceptions. Plain `db()` does not commit writes automatically.

## Browser workspace

The browser sends a JSON snapshot of its items, movements and audit rows with
each request. Flask binds a separate in-memory SQLite connection to that
request through a `ContextVar`. The services read and write that connection
until the request finishes. The browser saves the returned snapshot in
`localStorage`. CLI commands open the configured disk database.

The request snapshot contains editable demo data. The server creates a fictional
actor for each request. User records and password hashes stay outside the
snapshot. The demo accepts up to 100 items, 500 movements, 1,000 audit rows, and
1 MB per request. JSON backup exports contain the browser workspace.

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

Reports go into the active data directory's `reports/` folder with a timestamped name. If a filename is taken, the exporter adds a numbered suffix. An empty report contains `No records`.

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
7. Audit values use multiple serialization formats.

Stop the app before an ordinary database-file copy. A future backup workflow should use SQLite's backup API and validate restoration.

## Verification on current main

The CLI smoke check verifies the schema in a temporary database. The regression
suites cover login auditing, permissions, input validation, stock operations,
browser backup restore and concurrent requests with separate demo workspaces.
Run the commands in the [verification guide](TESTING.md).

## Repository hygiene

Publish source and synthetic examples only. Keep `data/`, SQLite files, reports,
backups, environment files and credentials outside source control. The CLI
creates its directories when run. Importing the Flask app performs no disk writes.
