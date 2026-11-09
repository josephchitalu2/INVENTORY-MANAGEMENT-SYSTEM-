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

Create admin, log in, create items or seed demo, record movements, inspect low stock and export reports. Menu 6 keeps blank fields unchanged. Menu 10 changes your password. Stock-out values use the item's cost price, not sales revenue. The application is not a complete POS/accounting system.

Reports go into the active data directory's `reports/` folder with a timestamped name. An empty report contains `No records`. Same-prefix exports within one second can overwrite each other.

## Security controls and limits

Passwords require at least eight characters. Usernames are stripped, limited to 50 characters and cannot contain whitespace. Hashes contain algorithm, rounds, random 16-byte salt and digest. `hmac.compare_digest` compares hashes. There is no login rate limiting or password recovery workflow. Audit rows are mutable by someone with database access and are not tamper-proof.

## Security and correctness fixes (fix/cli-guards-and-regression-tests)

The regression branch commits successful-login audit rows, rejects non-finite numbers in quantities/prices/reorder thresholds, checks active status for role-restricted operations, rejects blank item names and fractional stock/reorder values when converting to whole-item units, and disables the unauthenticated command-line demo seeding shortcut. Use the authenticated admin menu 13 to seed fictional items. These controls have regression tests; until the branch is merged they are not on main.

## Confirmed defects and remaining limitations

1. On `main`, successful-login audit inserts did not persist; fixed on the regression branch. Failed logins are still not audited.
2. On `main`, non-finite numeric values were not rejected; fixed on the regression branch. Monetary precision still requires design work.
3. On `main`, `require_role()` did not reject inactive users; fixed on the regression branch for role-guarded operations.
4. On `main`, unit changes permitted fractional stock under discrete units and stripped empty names; fixed on the regression branch.
5. On `main`, CLI `--seed-demo` could seed without authentication; disabled on the regression branch. Use the authenticated admin menu instead.
6. Backup/restore is not implemented; a created directory is not a backup. Stop the app before an ordinary database-file copy, or use SQLite's backup API in a future feature.
7. Amounts and prices use binary floating point. Monetary precision, concurrent-user races, migrations, session lifecycle and recovery require further work.
8. The first-admin precheck is outside its write transaction. Simultaneous first-run processes are not handled robustly.

## Verification on the supplied source

Executed against a temporary copy and temporary database, with no shop data: first-admin creation; staff creation; case-insensitive login; fractional kilogram removal; rejection of insufficient stock with original quantity retained; staff add-item rejection. The baseline checks confirmed the missing login-audit commit and accepted infinite price; regression tests on the fix branch cover these cases. These are logic checks, not a production security audit or manual terminal usability assessment.

## Repository hygiene

Publish source and synthetic examples only. Do not commit `data/`, SQLite files, reports, backups, environment files or credentials. Never run `git add .` before inspecting staged filenames. Source import creates the data directories, so tests should use a temporary copy.
