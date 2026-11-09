# IMS verification

Requires Python 3.10+ and its standard library. Run from the repository root:

```bash
python3 -m py_compile ims.py
python3 scripts/smoke_check.py
python3 -m unittest discover -s tests -v
```

The smoke check copies `ims.py` into a temporary directory, runs `--init-db` with a temporary database path, checks SQLite integrity and confirms the four expected tables. Temporary runtime files are removed afterward. It does not modify the shop database.

## Automated regression coverage

The standard-library unittest suite uses a temporary SQLite database and tests persisted successful-login auditing, disabled-account authorization, invalid non-finite numbers, discrete-unit constraints, rejected stock deductions, unit changes and item name validation. GitHub Actions runs these checks on pushes and pull requests. They do not establish production readiness or replace a real browser/terminal demonstration.

## Manual functional checks

Use fictional data and a fresh database. Create an admin, sign in, seed using admin menu 13, create staff, remove a fractional kilogram quantity, reject insufficient stock, reject staff item creation and export a report. Inspect the generated database and CSV locally.

## Limits

Passing schema/integrity checks does not demonstrate authentication, authorisation, business-rule correctness, concurrency or backup recovery. The [technical guide](TECHNICAL.md) distinguishes fixed issues from remaining defects. The suite is focused and does not test concurrent administration, data migration, backups or all edge cases.
