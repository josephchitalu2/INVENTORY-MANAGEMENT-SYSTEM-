import sqlite3
import tempfile
import unittest
from pathlib import Path
import ims
from store_app import create_app


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(self.root)
        self.app.testing = True
        conn = sqlite3.connect(self.root / 'inventory.db')
        conn.row_factory = sqlite3.Row
        token = ims.REQUEST_DATABASE.set(conn)
        try:
            uid = ims.AuthService().create_first_admin('owner', 'owner-password-123')
            ims.AuthService().create_user(uid, 'cashier', 'staff-password-123', 'staff')
        finally:
            ims.REQUEST_DATABASE.reset(token)
            conn.close()
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, client=None, username='owner', password='owner-password-123'):
        client = client or self.client
        client.get('/login')
        with client.session_transaction() as s:
            csrf = s['csrf']
        return client.post('/login', data={'username':username, 'password':password, 'csrf':csrf})

    def post(self, action, data=None, client=None, **extra):
        client = client or self.client
        with client.session_transaction() as s:
            csrf = s['csrf']
        return client.post('/api/inventory', json={'action':action, 'data':data or {}, **extra}, headers={'X-CSRF-Token':csrf})

    def add(self):
        return self.post('add', dict(name='Fish', unit_type='kg', quantity=10, cost_price=20, selling_price=30, reorder_level=2))

    def test_login_csrf_logout_and_backup_protection(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.client.get('/login')
        self.assertEqual(self.post('load').status_code, 401)
        self.assertEqual(self.client.get('/backup').status_code, 302)
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.client.post('/api/inventory', json={'action':'load'}).status_code, 403)
        with self.client.session_transaction() as s:
            old_cookie = dict(s)
            csrf = s['csrf']
        self.assertEqual(self.client.post('/logout', data={'csrf':csrf}).status_code, 302)
        with self.client.session_transaction() as s:
            s.update(old_cookie)
        self.assertEqual(self.post('load').status_code, 401)

    def test_persistence_weighted_stock_and_rollback(self):
        self.login()
        self.assertEqual(self.add().status_code, 200)
        item = self.post('load').json['items'][0]
        self.assertEqual(self.post('stock', {'item_id':item['id'], 'amount':1.25, 'direction':'remove'}).status_code, 200)
        self.assertEqual(self.post('stock', {'item_id':item['id'], 'amount':100, 'direction':'remove'}).status_code, 400)
        restarted = create_app(self.root).test_client()
        self.login(restarted)
        self.assertEqual(self.post('load', client=restarted).json['items'][0]['quantity'], 8.75)
        backup = restarted.get('/backup')
        path = self.root / 'restored.sqlite3'
        path.write_bytes(backup.data)
        backup.close()
        with sqlite3.connect(path) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(c.execute('SELECT quantity FROM items').fetchone()[0], 8.75)

    def test_staff_and_snapshot_restrictions(self):
        self.login()
        self.add()
        staff = self.app.test_client()
        self.login(staff, 'cashier', 'staff-password-123')
        item = self.post('load', client=staff).json['items'][0]
        self.assertEqual(self.post('add', {'name':'Chicken'}, client=staff).status_code, 403)
        self.assertEqual(self.post('stock', {'item_id':item['id'],'amount':.5,'direction':'remove'}, client=staff).status_code, 200)
        self.assertEqual(staff.get('/backup').status_code, 403)
        self.assertEqual(self.post('reset').status_code, 400)
        self.assertEqual(self.post('load', snapshot={'version':1}).status_code, 400)

    def test_password_change_revokes_sessions_and_rate_limit(self):
        self.login()
        second = self.app.test_client()
        self.login(second)
        with self.client.session_transaction() as s:
            csrf = s['csrf']
        r = self.client.post('/account', data={'csrf':csrf, 'current':'owner-password-123', 'password':'new-password-123'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.post('load', client=second).status_code, 401)
        for _ in range(10):
            r = self.login(password='wrong')
        self.assertEqual(r.status_code, 429)


if __name__ == '__main__':
    unittest.main()
