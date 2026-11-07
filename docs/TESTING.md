# IMS verification

Requires Python 3.10+ and its standard library. Run from the repository root:

```bash
python3 -m py_compile ims.py
python3 scripts/smoke_check.py
```

The smoke check copies `ims.py` into a temporary directory, runs `--init-db` with a temporary database path, checks SQLite integrity and confirms the four expected tables. Temporary runtime files are removed afterward. It does not modify the shop database.

## Manual functional checks

Use fictional data and a fresh database. Create an admin, sign in, seed using admin menu 13, create staff, remove a fractional kilogram quantity, reject insufficient stock, reject staff item creation and export a report. Inspect the generated database and CSV locally.

## Limits

Passing schema/integrity checks does not demonstrate authentication, authorisation, business-rule correctness, concurrency or backup recovery. The [technical guide](TECHNICAL.md) records previously confirmed defects, including missing login-audit commits, non-finite numeric values and the legacy seeding shortcut. A broader regression suite is roadmap work.
