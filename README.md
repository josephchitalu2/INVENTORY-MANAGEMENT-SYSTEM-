# Inventory Management System

A Python CLI inventory application for a small retail shop, with SQLite persistence, weighted stock, movement history and role-based write operations.

**Version:** 5.0 · **Runtime:** Python 3.10+ · **Dependencies:** standard library only · **Status:** local educational prototype

[Technical documentation](docs/TECHNICAL.md) · [Roadmap](docs/ROADMAP.md) · [Testing](docs/TESTING.md) · [Contributing](CONTRIBUTING.md) · [Security reporting](SECURITY.md)

## Quick start

```bash
git clone https://github.com/josephchitalu2/INVENTORY-MANAGEMENT-SYSTEM-.git
cd INVENTORY-MANAGEMENT-SYSTEM-
python3 ims.py
```

First run creates a local database and asks you to create an administrator. No default password is shipped. Type `q` at the login username prompt to exit. The CLI still displays its original shop-specific application title; `ims.py` is the canonical entry point.

Use a separate database for practice:

```bash
python3 ims.py --init-db --db ./sandbox/inventory.db
python3 ims.py --db ./sandbox/inventory.db
```

After signing in as admin, menu **13** adds eight fictional demo products. Duplicate product names are skipped. Use this authenticated menu rather than the legacy command-line seeding option documented under known issues.

## Capabilities

| Area | Working behaviour |
| --- | --- |
| Stock units | Fractional kilograms; whole packs, bottles and pieces |
| Inventory | Item search, stock in/out, low-stock lookup and cost valuation |
| Records | Stock movements and inventory/movement CSV reports |
| Roles | Admin, manager and staff; service-level write restrictions |
| Passwords | Salted PBKDF2-HMAC-SHA256 hashes, 210,000 rounds |
| Writes | Inventory changes and their movement/audit inserts in SQLite transactions |

Read the [confirmed defects](docs/TECHNICAL.md#confirmed-defects-and-remaining-limitations) before entering real shop data. This repository contains the CLI implementation; a separate Flask POS deployment is not included here.

## Code and data

| Path | Purpose |
| --- | --- |
| `ims.py` | CLI, services, repositories and SQLite schema |
| `docs/TECHNICAL.md` | Architecture, permissions, data model and known issues |
| `docs/ROADMAP.md` | Prioritised future work |
| `docs/TESTING.md` | Reproducible checks and their limits |
| `.github/` | Automated smoke check and contribution templates |

By default the application creates `data/inventory.db`, `data/reports/` and `data/backups/` beside the script. `--db` changes the active data location; importing the script also creates its default data directories. Run verification on a temporary copy.

A backups directory exists, but backup/restore is not implemented. CSV reports cannot restore a database. v4 databases are not migrated automatically: preserve the original separately and use a fresh v5 database.

## Development

```bash
python3 -m py_compile ims.py
python3 scripts/smoke_check.py
```

The smoke check runs an isolated copy, initialises SQLite and verifies its expected tables. It does not exercise all business rules or fix the known defects. No complete automated regression suite is currently shipped.

Do not commit live databases, password hashes, reports or shop/customer data. `.gitignore` excludes runtime outputs, but already tracked files must still be reviewed.

## Licensing and provenance

Built through iterative development with AI assistance. No software licence has been selected; public source visibility is not an open-source licence grant. Earlier versions remain in Git history. Future work is listed in the roadmap rather than presented as completed functionality.
