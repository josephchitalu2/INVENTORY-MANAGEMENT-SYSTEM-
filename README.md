# Inventory Management System

A Python CLI inventory application for a small retail shop, with SQLite persistence, weighted stock, movement history and role-based write operations.

**Version 5.0** · Python 3.10+ · Local inventory CLI and Flask portfolio demo

[Operator guide](docs/OPERATOR_GUIDE.md) · [Technical documentation](docs/TECHNICAL.md) · [Roadmap](docs/ROADMAP.md) · [Testing](docs/TESTING.md) · [Contributing](CONTRIBUTING.md) · [Security reporting](SECURITY.md)

## Quick start

```bash
git clone https://github.com/josephchitalu2/INVENTORY-MANAGEMENT-SYSTEM-.git
cd INVENTORY-MANAGEMENT-SYSTEM-
python3 ims.py
```

First run creates a local SQLite database and asks you to create an administrator. Choose a new password with at least eight characters. No default password is shipped. Type `q` at the login username prompt to exit. The CLI uses Chitalu Software Solutions branding; `ims.py` is the canonical entry point.

Use a separate database for practice:

```bash
python3 ims.py --init-db --db ./sandbox/inventory.db
python3 ims.py --db ./sandbox/inventory.db
```

After signing in as admin, menu **13** adds eight fictional demo products. Duplicate product names are skipped. The legacy `--seed-demo` argument is disabled. The [operator guide](docs/OPERATOR_GUIDE.md) shows the first stock movement and report export.

## Browser demo

The Flask demo opens a fictional inventory workspace for each browser. Add and
edit products, record stock movements, filter low stock, and export CSV or a
JSON backup. The browser stores the snapshot locally and can restore a backup.
There is no shared inventory or login. Use fictional data.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open http://127.0.0.1:5000. For Vercel, the repository root contains `app.py`
and `vercel.json`. The Flask app starts with no environment secrets. Hosted
access follows the Vercel project's Deployment Protection settings.
The CLI runs with Python's standard library.

## Capabilities

| Area | Working behaviour |
| --- | --- |
| Stock units | Fractional kilograms; whole packs, bottles and pieces |
| Inventory | Item search, stock in/out, low-stock lookup and cost valuation |
| Records | Stock movements and inventory/movement CSV reports |
| Roles | Admin, manager and staff; service-level write restrictions |
| Passwords | Salted PBKDF2-HMAC-SHA256 hashes, 210,000 rounds |
| Writes | Inventory changes and their movement/audit inserts in SQLite transactions |

Review the [remaining limitations](docs/TECHNICAL.md#confirmed-defects-and-remaining-limitations) before entering real shop data.

## Code and data

| Path | Purpose |
| --- | --- |
| `ims.py` | CLI, services, repositories and SQLite schema |
| `app.py`, `templates/index.html` | Browser demo and request-scoped SQLite workspace |
| `docs/OPERATOR_GUIDE.md` | Practice setup, stock movements and reports |
| `docs/TECHNICAL.md` | Architecture, permissions, data model and known issues |
| `docs/ROADMAP.md` | Prioritised future work |
| `docs/TESTING.md` | Reproducible checks and their limits |
| `.github/` | Automated smoke check and contribution templates |

By default the CLI creates `data/inventory.db`, `data/reports/` and `data/backups/` beside the script. `--db` changes the active data location. Run verification on a temporary copy.

A backups directory exists for the CLI, and SQLite backup/restore is still planned. The browser demo's JSON backups contain only its own workspace. For v4 databases, preserve the original separately and use a fresh v5 database.

## Development

```bash
python3 -m py_compile ims.py
python3 scripts/smoke_check.py
python3 -m unittest discover -s tests -p test_inventory_guards.py -v
```

Run `.venv/bin/python -m unittest discover -s tests -v` after installing Flask
to include the web tests. The smoke check initialises SQLite in an isolated copy
and verifies its tables. See the [verification guide](docs/TESTING.md) for coverage.

Do not commit live databases, password hashes, reports or shop/customer data. `.gitignore` excludes runtime outputs, but already tracked files must still be reviewed.

## Licensing and provenance

Built through iterative development with AI assistance. No software licence has been selected; public source visibility is not an open-source licence grant. Earlier versions remain in Git history. Future work is listed in the roadmap rather than presented as completed functionality.
