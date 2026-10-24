"""Interactive local owner-account setup. Never accepts passwords on command line."""
from getpass import getpass
import os
from pathlib import Path
import sqlite3
import ims
from store_app import create_app

if __name__ == '__main__':
    root = Path(os.environ.get('IMS_DATA_DIR', Path.home() / '.local/share/chitalu-ims')).resolve()
    create_app(root)
    conn = sqlite3.connect(root / 'inventory.db')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    token = ims.REQUEST_DATABASE.set(conn)
    try:
        if ims.UserRepository().count():
            raise SystemExit('An account already exists. Sign in to manage accounts.')
        username = input('Owner username: ').strip()
        password = getpass('Owner password (at least 8 characters): ')
        if password != getpass('Confirm password: '):
            raise SystemExit('Passwords do not match. No account created.')
        ims.AuthService().create_first_admin(username, password)
        print('Owner account created. Start with: python store_app.py')
    except ims.IMSException as exc:
        raise SystemExit(str(exc))
    finally:
        ims.REQUEST_DATABASE.reset(token)
        conn.close()
