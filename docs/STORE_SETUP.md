# Single-PC store edition

This edition runs on the store PC, without an internet connection after installation.
The existing `app.py` remains the separate, browser-only Vercel portfolio demo.
Run `store_app.py` for real store records. Do not deploy it to Vercel's temporary disk.

## Install on EndeavourOS / Linux

Download and extract IMS_Store_Edition.zip first. Requires Python 3.10+. In a terminal:

```bash
unzip IMS_Store_Edition.zip
cd IMS_Store_Edition
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-store.txt
python store_setup.py
python store_app.py
```

Setup asks privately for an owner username and password. There is no default account.
Open http://127.0.0.1:8080 in Firefox on the same PC. Keep the server terminal running.
For subsequent starts, enter this folder, activate `.venv`, then run `python store_app.py`.
Use the desktop's terminal copy shortcut (normally Ctrl+Shift+C) when copying text.

On Windows with Python and Git installed, use the same commands except activate with
`.venv\Scripts\activate` in Command Prompt. Confirm the actual store PC's OS before installation.

## Accounts and permissions

Sign in as the owner. Open **Account & staff** to create separate named accounts.

| Role | Permissions |
| --- | --- |
| Staff | View inventory, export displayed CSV, record stock in/out |
| Manager | Staff permissions plus add/edit products |
| Admin | Manager permissions plus create accounts and download full database backups |

Passwords use the existing salted PBKDF2 hashing. Sessions expire after 30 minutes
and are checked against the database on each request. Logout revokes the session;
changing a password revokes all sessions for that user. Login is limited to 10
attempts in five minutes. No public registration or demo seed/reset/restore endpoints
are exposed. The server listens only on loopback and rejects other hostnames.
This configuration is for one trusted PC, not LAN/public access.

## Data and backups

Default location: `~/.local/share/chitalu-ims/inventory.db` plus `session.key` and
`backups/`. Set `IMS_DATA_DIR` before setup and startup to choose another local folder.
Keep the same folder on every start. Browser storage is not used by this edition.
Inventory starts empty; enter real opening stock after a physical count.
The Vercel demo's browser snapshots are not imported into store records.

SQLite transactions commit stock movements and audit records together. Automatic
consistent backups run on startup and before every add/edit/stock request; the newest
30 are retained. Admins can also download a full SQLite backup from the dashboard.
Copy a backup to a USB drive **daily**: copies on the same disk do not survive disk failure.
Backups contain account password hashes and store records: keep them private.

To recover: stop the store server completely, then run:

```bash
python store_restore.py /path/to/ims-store-backup.sqlite3
```

The tool checks integrity and references, asks for `RESTORE`, saves the previous
database, restores records, and clears sessions. Restart the server and sign in with
the credentials from the restored backup. Do not run recovery while IMS is running.
There is no password-reset-by-email; keep the owner credentials safely.

## Verify on the actual store PC before using live stock

1. Create the owner account and one staff account; check each role.
2. Add a temporary product, record a fractional kilogram movement, then restart IMS.
3. Confirm records survived. Download a backup and test recovery in a separate data folder.
4. Only then enter real stock. Keep existing store records alongside the first trial.

This tracks inventory quantities and cost-based stock movements. It does not yet
provide a sales till, payment reconciliation, sales profit accounting, or encrypted
database files. Protect the PC with its OS login and disk encryption where available.

## Developer checks

```bash
python -m unittest discover -s tests -v
```

Regression coverage includes store restart persistence, backup integrity, permissions,
CSRF, session revocation, login limits, weighted stock and rejected overdrafts, plus
the existing Vercel demo tests. Actual store installation and browser acceptance
testing are still required.
