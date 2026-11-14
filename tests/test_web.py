import math
import sqlite3
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import app, workspace
import ims


class WebTests(unittest.TestCase):
    def call(self, action='load', snapshot=None, data=None):
        with app.test_client() as client:
            return client.post('/api/inventory', json={'action': action, 'snapshot': snapshot, 'data': data or {}})

    def test_entrypoint_and_health(self):
        with app.test_client() as client:
            self.assertEqual(client.get('/').status_code, 200)
            self.assertEqual(client.get('/api/health').json['status'], 'ok')

    def test_weighted_stock_roundtrip_and_rollback(self):
        first = self.call().json
        item = next(i for i in first['items'] if i['name'] == 'Fresh Fish')
        changed = self.call('stock', first['snapshot'], {'item_id': item['id'], 'direction': 'remove', 'amount': 0.75}).json
        fish = next(i for i in changed['items'] if i['id'] == item['id'])
        self.assertAlmostEqual(fish['quantity'], 42.95)
        loaded = self.call('load', changed['snapshot']).json
        self.assertEqual(loaded['snapshot'], changed['snapshot'])
        rejected = self.call('stock', loaded['snapshot'], {'item_id': item['id'], 'direction': 'remove', 'amount': 999})
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(self.call('load', loaded['snapshot']).json['snapshot'], loaded['snapshot'])

    def test_visitors_are_isolated_under_concurrency(self):
        snapshot = self.call().json['snapshot']
        def update(amount):
            return self.call('stock', snapshot, {'item_id': 1, 'direction': 'add', 'amount': amount}).json
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(update, [1, 5]))
        self.assertAlmostEqual(a['snapshot']['items'][0]['quantity'], 44.7)
        self.assertAlmostEqual(b['snapshot']['items'][0]['quantity'], 48.7)
        self.assertAlmostEqual(self.call().json['snapshot']['items'][0]['quantity'], 43.7)

    def test_add_edit_and_backup_restore(self):
        empty = self.call('reset').json['snapshot']
        added = self.call('add', empty, {'name': 'Tomatoes', 'unit_type': 'kg', 'quantity': 2.5, 'cost_price': 10, 'selling_price': 15}).json
        updated = self.call('update', added['snapshot'], {'item_id': 1, 'name': 'Fresh tomatoes', 'selling_price': 18}).json
        self.assertEqual(updated['items'][0]['selling_price'], 18)
        self.assertEqual(self.call('load', updated['snapshot']).json['items'], updated['items'])
        self.assertEqual(self.call('seed', updated['snapshot']).status_code, 200)

    def test_bad_input_and_tampered_backups(self):
        snapshot = self.call().json['snapshot']
        for amount in [float('inf'), float('nan'), -1, 'not-a-number']:
            self.assertEqual(self.call('stock', snapshot, {'item_id': 1, 'direction': 'add', 'amount': amount}).status_code, 400)
        self.assertEqual(self.call('add', snapshot, {'name':'Eggs','unit_type':'piece','quantity':0.5}).status_code,400)
        self.assertEqual(self.call('update', snapshot, {'item_id':1,'name':'  '}).status_code,400)
        snapshot['items'][0]['unexpected_column'] = 'bad'
        self.assertEqual(self.call('load', snapshot).status_code,400)
        with app.test_client() as client:
            self.assertEqual(client.post('/api/inventory', json=[]).status_code,400)
            self.assertEqual(client.post('/api/inventory', data='x').status_code,415)
            self.assertEqual(client.post('/api/inventory',data='x'*1000001,content_type='application/json').status_code,413)

    def test_service_permissions_and_audit(self):
        with workspace(None) as conn:
            auth = ims.AuthService()
            uid = auth.create_user(1, 'staff', 'test-password', 'staff')
            auth.authenticate('staff', 'test-password')
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='login'").fetchone()[0],1)
            conn.execute('UPDATE users SET active=0 WHERE id=?',(uid,));conn.commit()
            with self.assertRaises(ims.AuthorizationError):
                auth.require_role(uid, {'staff'})
            with self.assertRaises(ims.AuthorizationError):
                ims.InventoryService().add_item(uid,name='X',category='',unit_type='kg',quantity=1,cost_price=1,selling_price=2,supplier='',reorder_level=1)


if __name__ == '__main__':
    unittest.main()
