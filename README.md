# IMS by Chitalu Software Solutions

A Python CLI inventory application for a small retail shop, with SQLite persistence, weighted stock and role-based write operations. The supplied file identifies itself as **v5.0**; its upload filename was `ims_v5_1(1).py`. This package uses `ims.py` as the canonical entry point. Built through iterative development with AI assistance.

## Browser demo (Vercel)

The repository now includes `app.py`, a Flask web entry point, and `vercel.json`.
Vercel deploys the web demo; the original `python3 ims.py` CLI remains available.

```bash
python3 -m pip install -r requirements.txt
python3 app.py
# Open http://127.0.0.1:5000
```

The demo supports product creation/editing, weighted stock in/out, low-stock
filtering, movement history, CSV exports, and JSON backup/restore. The browser
sends its synthetic snapshot to a request-isolated in-memory SQLite database;
operations use the existing Python services. The resulting snapshot is saved
in browser localStorage. No shared server database or demo login is involved.
Each visitor has their own workspace. Private browsing or another device has
a separate workspace. Clearing browser data loses records unless backed up.

**Portfolio demo only:** use fictional data. This is not a shared shop service,
an authenticated account system, or durable cloud storage. An external database,
authenticated sessions, and an operational backup/recovery plan are required
before adapting it for real business use. Audit records in browser backups are
editable and are not proof of activity. Limits: 100 products, 500 movements,
1,000 audit rows, 1 MB requests. Unit conversion is blocked to preserve meaning.

Deploy the repository root with the Flask preset (declared in `vercel.json`).
No environment secrets are required. Do not configure a custom output directory
or a CLI command as the build/start command. Vercel discovers the `app` instance
in `app.py`. Existing Vercel deployment access protection remains a separate
project setting; a successful build does not make a protected preview public.

```bash
python3 -m unittest discover -s tests -v
```

## Run CLI

Requires Python 3.10+ and its standard library. No pip packages are required.

```bash
python3 ims.py
```

First run creates a local database and asks you to create an administrator. No default password is provided. Type `q` at the login username prompt to exit.

```bash
python3 ims.py --init-db
python3 ims.py --db ./sandbox/inventory.db
```

After creating an admin, use menu 13 to add the eight fictional demo products. It is an admin-only menu operation. Existing duplicate product names are skipped.

## Capabilities

- Units: kilograms, packs, bottles and pieces. Kilograms accept fractional quantities.
- Item search, stock-in/out, low-stock lookup and inventory cost valuation.
- Inventory and movement CSV reports.
- Admin, manager and staff roles with service-level write restrictions.
- Password hashing using salted PBKDF2-HMAC-SHA256, 210,000 rounds.
- Atomic inventory changes with movement and audit inserts in a SQLite transaction.

[Technical documentation](docs/TECHNICAL.md) explains the schema, operation, limitations and validation results. **Read its known issues before entering real shop data.**

## Data handling

The program creates `data/inventory.db`, `data/reports/` and `data/backups/` beside the script. A custom `--db` changes these destinations. A backups folder exists, but automatic backup/restore is not implemented. CSV reports do not restore a database.

Do not commit databases, password hashes, real customer/supplier details or exported logs. The included `.gitignore` excludes common runtime outputs. Check tracked files separately: ignore rules do not untrack existing content.

## Project status

Educational/local prototype. This upload is preserved, with known defects documented rather than labelled production-ready. This update replaces the old v4 code stored in README.md with real documentation and a separate Python entry point. Earlier versions remain in Git history. No licence has been chosen in this package; choose one before claiming open-source licensing.

## Planned improvements

These are intentions, not existing capabilities: verified database backup/restore, stricter finite-number and unit validation, persistent login auditing, session/activity checks, safe demo seeding, database migrations, and a broader automated regression suite. See [the roadmap](docs/ROADMAP.md) for the proposed order.

## Existing v4 data

v5 does not migrate a v4 database. Start with a fresh database path and preserve the old database separately. Do not point this application at a v4 database expecting an automatic upgrade.
