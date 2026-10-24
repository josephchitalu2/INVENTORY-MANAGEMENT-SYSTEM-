"""Offline recovery. Stop the store server before running this command."""
import argparse
import os
from pathlib import Path
import sqlite3
import time


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    args = parser.parse_args()
    source_path = args.backup.resolve()
    root = Path(os.environ.get('IMS_DATA_DIR', Path.home() / '.local/share/chitalu-ims')).resolve()
    destination = root / 'inventory.db'
    if source_path == destination:
        raise SystemExit('Choose a backup file, not the live database.')
    with sqlite3.connect(source_path.as_uri()+'?mode=ro', uri=True) as source:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit('Backup failed its integrity check.')
        for table in ['users','items','stock_movements','audit_log','web_sessions','login_attempts']:
            source.execute(f'SELECT * FROM {table} LIMIT 0')
        if source.execute('PRAGMA foreign_key_check').fetchone():
            raise SystemExit('Backup contains broken references.')
        if input('Stop IMS first. Replace store records with this backup? Type RESTORE: ') != 'RESTORE':
            raise SystemExit('Cancelled.')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if destination.exists():
            with sqlite3.connect(destination) as current, sqlite3.connect(root / f'before-restore-{time.time_ns()}.sqlite3') as old:
                current.backup(old)
        with sqlite3.connect(destination) as target:
            source.backup(target)
            target.execute('DELETE FROM web_sessions')
            target.execute('DELETE FROM login_attempts')
        os.chmod(destination, 0o600)
    print('Restored. Restart IMS and sign in using the account from the backup.')
