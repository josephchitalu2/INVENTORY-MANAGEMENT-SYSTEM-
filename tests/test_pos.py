import json
import subprocess
import os
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import ims
import papino
from store_app import create_app

class POSTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.app=create_app(self.root)
        self.c=sqlite3.connect(self.root/'inventory.db');self.c.row_factory=sqlite3.Row;self.c.execute('PRAGMA foreign_keys=ON')
        token=ims.REQUEST_DATABASE.set(self.c)
        try:
            self.uid=ims.AuthService().create_first_admin('owner','owner-password-123')
            self.staff=ims.AuthService().create_user(self.uid,'cashier','cashier-password-123','staff')
        finally:ims.REQUEST_DATABASE.reset(token)
        self.p=papino.POS(self.c,dict(id=self.uid,role='admin'))
        self.p.act('catalog',{})
        self.fish=self.c.execute("SELECT id FROM items WHERE name='Fish'").fetchone()[0]
        self.chicken=self.c.execute("SELECT id FROM items WHERE name='Chicken pieces'").fetchone()[0]
        with self.c:self.c.execute('UPDATE items SET quantity=100')
        self.p.act('open',{'opening':'500'})
    def tearDown(self):self.c.close();self.tmp.cleanup()
    def checkout(self,items=None,payments=None,**more):
        return self.p.act('checkout',{'key':str(uuid.uuid4()),'items':items or [{'id':self.fish,'quantity':'1'}], 'payments':payments if payments is not None else [{'method':'cash','amount':'68'}],'tendered':'100',**more})
    def test_split_weighted_money_and_duplicate(self):
        k=str(uuid.uuid4()); d={'key':k,'items':[{'id':self.fish,'quantity':'.75'}],'payments':[{'method':'cash','amount':'20'},{'method':'airtel','amount':'31','reference':'AIRTEL-1'}],'tendered':'50'}
        first=self.p.act('checkout',d);second=self.p.act('checkout',d)
        self.assertEqual(first['sale_id'],second['sale_id']);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM pos_sales').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT total FROM pos_sales').fetchone()[0],5100)
        self.assertEqual(self.c.execute('SELECT quantity FROM items WHERE id=?',(self.fish,)).fetchone()[0],99.25)
        self.assertEqual(self.p.expected(self.p.shift()),52000)
    def test_atomic_failed_basket(self):
        with self.assertRaises(ims.ValidationError):self.checkout([{'id':self.fish,'quantity':'1'},{'id':self.chicken,'quantity':'200'}])
        self.assertEqual(self.c.execute('SELECT quantity FROM items WHERE id=?',(self.fish,)).fetchone()[0],100)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM pos_sales').fetchone()[0],0)
    def test_credit_repayment_no_second_stock_deduction(self):
        sale=self.checkout(payments=[],customer='Customer',contact='0970000000',recipient='Recipient',due='2026-11-01',authorization='Dad by phone')['sale_id']
        self.p.act('repay',{'key':str(uuid.uuid4()),'sale_id':sale,'tendered':'20','payments':[{'method':'cash','amount':'20'}]})
        self.p.act('repay',{'key':str(uuid.uuid4()),'sale_id':sale,'payments':[{'method':'airtel','amount':'48','reference':'REP-1'}]})
        row=self.c.execute('SELECT * FROM pos_sales WHERE id=?',(sale,)).fetchone();self.assertEqual(self.p.balance(row),0)
        self.assertEqual(self.c.execute('SELECT quantity FROM items WHERE id=?',(self.fish,)).fetchone()[0],99)
        with self.assertRaises(ims.ValidationError):self.p.act('repay',{'key':str(uuid.uuid4()),'sale_id':sale,'payments':[{'method':'cash','amount':'1'}]})
    def test_unauthorized_credit_rejected(self):
        with self.assertRaises(ims.ValidationError):self.checkout(payments=[])
    def test_expense_deposit_and_owner_receipt(self):
        self.p.act('cash',{'key':str(uuid.uuid4()),'kind':'expense','amount':'20','category':'lunch','details':'Lunch','recipient':'Cashier'})
        self.p.act('cash',{'key':str(uuid.uuid4()),'kind':'owner_deposit','amount':'100','details':'Dad requested 100','recipient':'Agent','reference':'DEP-1'})
        before=self.p.expected(self.p.shift());self.assertEqual(before,38000)
        ident=self.c.execute("SELECT id FROM pos_cash WHERE kind='owner_deposit'").fetchone()[0]
        self.p.act('confirm_cash',{'id':ident,'details':'Dad received K100'})
        self.assertEqual(self.p.expected(self.p.shift()),before)
    def test_closing_blind_and_frozen_count(self):
        self.checkout()
        self.p.act('start_close',{})
        with self.assertRaises(ims.ValidationError):self.checkout()
        self.p.act('count',{'denominations':{'10000':5,'5000':1,'1000':1,'500':1,'200':1,'100':1}})
        shift=self.p.shift(('counted',));self.assertEqual(shift['counted'],56800)
        with self.assertRaises(ims.ValidationError):self.p.act('count',{'denominations':{'10000':1}})
        self.p.act('cash',{'key':str(uuid.uuid4()),'kind':'owner_deposit','amount':'68','details':'Closing deposit','recipient':'Agent','reference':'DEP-2'})
        self.p.act('finish_close',{'remaining':'500'})
        self.assertEqual(self.c.execute('SELECT status FROM pos_shifts').fetchone()[0],'closed')
    def test_variance_not_silently_fixed(self):
        self.p.act('start_close',{});self.p.act('count',{'denominations':{'10000':4}})
        with self.assertRaises(ims.ValidationError):self.p.act('finish_close',{'remaining':'500'})
        self.p.act('finish_close',{'remaining':'400','explanation':'K100 shortage retained for owner review'})
        shift=self.c.execute('SELECT * FROM pos_shifts').fetchone();self.assertEqual(shift['counted']-shift['expected'],-10000)
    def test_dawari_conserves_stock_and_can_sell(self):
        self.p.act('withdraw',{'key':str(uuid.uuid4()),'item_id':self.fish,'quantity':'3','mode':'dawari','price':'25','reason':'Quality downgrade, safe for consumption'})
        downgraded=self.c.execute("SELECT * FROM items WHERE category='Ma dawari'").fetchone()
        self.assertEqual(downgraded['quantity'],3);self.assertEqual(self.c.execute('SELECT quantity FROM items WHERE id=?',(self.fish,)).fetchone()[0],97)
        self.checkout(items=[{'id':downgraded['id'],'quantity':'1'}],payments=[{'method':'cash','amount':'25'}])
        self.assertEqual(self.p.expected(self.p.shift()),52500)
    def test_full_reversal_preserves_original_and_refunds_cash(self):
        sid=self.checkout()['sale_id'];self.p.act('refund',{'key':str(uuid.uuid4()),'sale_id':sid,'payments':[{'method':'cash','amount':'68'}],'reason':'Customer return owner approved','restock':True})
        self.assertEqual(self.p.expected(self.p.shift()),50000);self.assertEqual(self.c.execute('SELECT quantity FROM items WHERE id=?',(self.fish,)).fetchone()[0],100)
        self.assertEqual(self.c.execute('SELECT reversed FROM pos_sales').fetchone()[0],1)
    def test_staff_cannot_change_owner_records(self):
        staff=papino.POS(self.c,dict(id=self.staff,role='staff'))
        for action,data in [('catalog',{}),('review_shift',{'id':1}),('withdraw',{'key':str(uuid.uuid4())}),('refund',{'key':str(uuid.uuid4())})]:
            with self.assertRaises(ims.AuthorizationError):staff.act(action,data)
        with self.assertRaises(ims.AuthorizationError):staff.act('start_close',{})
    def test_duplicate_electronic_reference_rejected(self):
        self.checkout(payments=[{'method':'zanaco','amount':'68','reference':'ZAN-1'}])
        with self.assertRaises(ims.ValidationError):self.checkout(payments=[{'method':'zanaco','amount':'68','reference':'ZAN-1'}])
    def test_recount_preserves_first_count_and_explains_variance(self):
        self.p.act('start_close',{})
        self.p.act('count',{'denominations':{'10000':4}})
        self.p.act('recount',{'denominations':{'10000':5},'explanation':'Found misplaced K100 note'})
        first=self.c.execute('SELECT counted FROM pos_shifts').fetchone()[0]
        self.assertEqual(first,40000)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM pos_counts').fetchone()[0],2)
        self.p.act('finish_close',{'remaining':'500','explanation':'First count shortage resolved on documented recount'})

    def test_concurrent_duplicate_checkout_only_commits_once(self):
        request_key=str(uuid.uuid4())
        payload={'key':request_key,'items':[{'id':self.fish,'quantity':'1'}],'payments':[{'method':'cash','amount':'68'}],'tendered':'68'}
        def perform(_):
            c=sqlite3.connect(self.root/'inventory.db',timeout=10);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
            try:return papino.POS(c,{'id':self.uid,'role':'admin'}).act('checkout',payload)['sale_id']
            finally:c.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(perform,range(2)))
        self.assertEqual(results[0],results[1]);self.assertEqual(self.c.execute('SELECT quantity FROM items WHERE id=?',(self.fish,)).fetchone()[0],99)

    def test_owner_review_waits_for_electronic_reconciliation(self):
        self.checkout(payments=[{'method':'airtel','amount':'68','reference':'VERIFY-1'}])
        self.p.act('start_close',{});self.p.act('count',{'denominations':{'50000':1}});self.p.act('finish_close',{'remaining':'500'})
        with self.assertRaises(ims.ValidationError):self.p.act('review_shift',{'id':1,'details':'Reviewed'})
        payment=self.c.execute('SELECT id FROM pos_payments').fetchone()[0]
        self.p.act('confirm_payment',{'id':payment,'details':'Dad verified company account'})
        self.p.act('review_shift',{'id':1,'details':'Payment and physical cash reconciled'})

    def test_staff_blind_state_and_cashier_shift_permissions(self):
        self.p.act('start_close',{});self.p.act('count',{'denominations':{'50000':1}});self.p.act('finish_close',{'remaining':'500'})
        staff=papino.POS(self.c,dict(id=self.staff,role='staff'));staff.act('open',{'opening':'500'})
        token=ims.REQUEST_DATABASE.set(self.c)
        try:
            state=staff.state();active=next(s for s in state['shifts'] if s['status']=='open')
            self.assertIsNone(active['expected']);self.assertEqual(state['cash'],[]);self.assertEqual(state['payments'],[])
            staff.act('start_close',{})
            self.assertEqual(staff.state()['sales'],[])
        finally:ims.REQUEST_DATABASE.reset(token)

    def test_full_database_recovery_retains_sales_and_credit(self):
        sid=self.checkout(payments=[],customer='Debtor',contact='0970000000',recipient='Debtor',due='2026-11-01',authorization='Dad phone approval')['sale_id']
        snapshot=self.root/'snapshot.sqlite3'
        with sqlite3.connect(snapshot) as target:self.c.backup(target)
        restored=self.root/'recovery'
        result=subprocess.run(['python','store_restore.py',str(snapshot)],input='RESTORE\n',text=True,capture_output=True,env={**os.environ,'IMS_DATA_DIR':str(restored)})
        self.assertEqual(result.returncode,0,result.stderr)
        create_app(restored)
        with sqlite3.connect(restored/'inventory.db') as c:
            self.assertEqual(c.execute('SELECT total FROM pos_sales WHERE id=?',(sid,)).fetchone()[0],6800)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM web_sessions').fetchone()[0],0)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_restart_receipt_and_api_auth(self):
        sid=self.checkout()['sale_id'];app=create_app(self.root);client=app.test_client();self.assertEqual(client.get('/api/pos').status_code,401)
        client.get('/login')
        with client.session_transaction() as s:csrf=s['csrf']
        client.post('/login',data={'username':'owner','password':'owner-password-123','csrf':csrf})
        self.assertEqual(client.get('/receipt/'+sid).status_code,200)
        self.assertIn(b'PAPINO',client.get('/').data)
        self.assertEqual(client.get('/api/pos').json['sales'][0]['total'],6800)

if __name__=='__main__':unittest.main()
