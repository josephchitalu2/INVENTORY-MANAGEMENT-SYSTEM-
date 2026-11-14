"""Initialise and inspect a disposable IMS database without touching shop data."""
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

source = Path(__file__).resolve().parents[1] / "ims.py"
with tempfile.TemporaryDirectory(prefix="ims-smoke-") as folder:
    work = Path(folder)
    shutil.copy2(source, work / "ims.py")
    database = work / "sandbox" / "inventory.db"
    subprocess.run([sys.executable, str(work / "ims.py"), "--init-db", "--db", str(database)], check=True, cwd=work)
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "items", "stock_movements", "audit_log"} <= tables, tables
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("PASS: isolated database initialisation, expected schema and SQLite integrity")
