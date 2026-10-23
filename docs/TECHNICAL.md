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

## Web deployment and isolation

`app.py` exports a Flask application for Vercel. JSON snapshots contain only
items, stock movements and audit rows. A `ContextVar` binds a separate in-memory
SQLite connection to each request; no request changes the CLI database path.
Users/password hashes are not exported. A synthetic actor is created per request.
Server-side validation rejects malformed backups, non-finite inputs, fractional
discrete stock, overdrawn stock and over-limit snapshots. Templates escape user
text before HTML insertion. CSV exports neutralise formula-like text cells.

Browser localStorage is the persistence layer for this portfolio demo. The
server is stateless; there is no account, shared inventory, or cloud database.
JSON backup/restore preserves the synthetic workspace across devices manually.
All imported records are untrusted, editable demonstration data. Limits are
100 items, 500 movements, 1,000 audits and 1 MB per API request.

## Confirmed fixes and remaining limitations

Fixed in the web deployment update: login audit writes now commit; numeric
validation rejects NaN/infinity; inactive actors fail role checks; blank product
names are rejected; unit changes are blocked until a conversion workflow exists.
Import no longer creates directories (important for read-only deployments).

The CLI still has these limitations: `--seed-demo` selects an existing user
without authentication; first-admin setup can race between processes; automatic
database backup/restore is not implemented. Prices use binary floats. Read
repositories do not enforce roles. CSV report filenames can collide within one
second. Existing v4 data is not migrated. The web demo does not expose CLI user
management or offer cloud persistence. Neither interface is a complete POS or
accounting system; movement values are at cost, not revenue or profit.

## Verification on the supplied source

Executed against a temporary copy and temporary database, with no shop data: first-admin creation; staff creation; case-insensitive login; fractional kilogram removal; rejection of insufficient stock with original quantity retained; staff add-item rejection. Those two defects were subsequently fixed and are covered by regression checks. These were logic checks, not a production security audit or manual terminal usability assessment.

## Repository hygiene

Publish source and synthetic examples only. Do not commit `data/`, SQLite files, reports, backups, environment files or credentials. Never run `git add .` before inspecting staged filenames. Source import no longer creates data directories; CLI database/report paths are created when needed.
