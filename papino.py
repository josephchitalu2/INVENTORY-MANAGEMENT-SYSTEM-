"""PAPINO local POS: transaction-scoped services; monetary values are integer ngwee."""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import ims

ZONE = ZoneInfo('Africa/Lusaka')

def stamp():
    return datetime.now(ZONE).isoformat(timespec='seconds')

def cents(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d > 10000000 or d.as_tuple().exponent < -2:
            raise ValueError()
        return int(d * 100)
    except (InvalidOperation, ValueError, TypeError):
        raise ims.ValidationError('Enter a non-negative amount with at most two decimal places.')

def qty(value, unit):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d <= 0 or d > 1000000 or d.as_tuple().exponent < -3:
            raise ValueError()
        if unit != 'kg' and d != d.to_integral_value():
            raise ValueError()
        return int(d * 1000)
    except (InvalidOperation, ValueError, TypeError):
        raise ims.ValidationError('Quantity must be positive; kilograms allow three decimals, other units whole numbers.')

def text(value, required=True):
    value = str(value or '').strip()
    if (required and not value) or len(value) > 500:
        raise ims.ValidationError('Supply the required details (maximum 500 characters).')
    return value

def init(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS pos_requests(request_key TEXT PRIMARY KEY,user_id INTEGER NOT NULL,action TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS pos_shifts(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), opened TEXT NOT NULL, opening INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'open', close_started TEXT, counted_at TEXT, counted INTEGER, expected INTEGER, denominations TEXT, explanation TEXT, closed TEXT, reviewed_by INTEGER REFERENCES users(id));
    CREATE UNIQUE INDEX IF NOT EXISTS one_active_till ON pos_shifts((1)) WHERE status != 'closed';
    CREATE TABLE IF NOT EXISTS pos_counts(id INTEGER PRIMARY KEY,shift_id INTEGER NOT NULL REFERENCES pos_shifts(id),user_id INTEGER NOT NULL REFERENCES users(id),amount INTEGER NOT NULL,expected INTEGER NOT NULL,cash_cutoff INTEGER NOT NULL,denominations TEXT NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS pos_sales(id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, shift_id INTEGER NOT NULL REFERENCES pos_shifts(id), user_id INTEGER NOT NULL REFERENCES users(id), created TEXT NOT NULL, total INTEGER NOT NULL, customer TEXT, contact TEXT, recipient TEXT, due TEXT, authorization TEXT, reversed INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS pos_lines(id INTEGER PRIMARY KEY, sale_id TEXT NOT NULL REFERENCES pos_sales(id), item_id INTEGER NOT NULL REFERENCES items(id), name TEXT NOT NULL, category TEXT, unit TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price INTEGER NOT NULL, total INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS pos_payments(id INTEGER PRIMARY KEY, sale_id TEXT NOT NULL REFERENCES pos_sales(id), shift_id INTEGER NOT NULL REFERENCES pos_shifts(id), user_id INTEGER NOT NULL REFERENCES users(id), method TEXT NOT NULL, amount INTEGER NOT NULL, reference TEXT, created TEXT NOT NULL, request_key TEXT UNIQUE NOT NULL, reviewed_by INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS pos_cash(id INTEGER PRIMARY KEY, shift_id INTEGER NOT NULL REFERENCES pos_shifts(id), user_id INTEGER NOT NULL REFERENCES users(id), kind TEXT NOT NULL, amount INTEGER NOT NULL, details TEXT NOT NULL, reference TEXT, created TEXT NOT NULL, request_key TEXT UNIQUE NOT NULL, confirmed_by INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS pos_credit_reviews(sale_id TEXT PRIMARY KEY REFERENCES pos_sales(id),user_id INTEGER NOT NULL REFERENCES users(id),details TEXT NOT NULL,created TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS pos_barcodes(item_id INTEGER PRIMARY KEY REFERENCES items(id),barcode TEXT UNIQUE NOT NULL);
    CREATE TABLE IF NOT EXISTS pos_events(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), kind TEXT NOT NULL, details TEXT NOT NULL, created TEXT NOT NULL);
    ''')

class POS:
    def __init__(self, conn, user):
        self.c, self.user, self.uid = conn, user, user['id']

    @contextmanager
    def transaction(self):
        self.c.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.c.commit()
        except Exception:
            self.c.rollback()
            raise

    def owner(self):
        if self.user['role'] not in {'admin','manager'}:
            raise ims.AuthorizationError('Owner/manager permission required.')

    def event(self, kind, data):
        self.c.execute('INSERT INTO pos_events(user_id,kind,details,created) VALUES(?,?,?,?)', (self.uid,kind,json.dumps(data),stamp()))

    def shift(self, statuses=('open',), owner_override=False):
        row = self.c.execute("SELECT * FROM pos_shifts WHERE status!='closed' ORDER BY id DESC LIMIT 1").fetchone()
        if not row or row['status'] not in statuses:
            raise ims.ValidationError('Open a shift, or finish the closing process first.')
        if row['user_id'] != self.uid and not (owner_override and self.user['role'] in {'admin','manager'}):
            raise ims.AuthorizationError('This till belongs to another cashier. Close and hand over their shift first.')
        return row

    def expected(self, shift):
        return shift['opening'] + self.c.execute('SELECT COALESCE(SUM(amount),0) FROM pos_cash WHERE shift_id=?',(shift['id'],)).fetchone()[0]

    def balance(self, sale):
        return 0 if sale['reversed'] else sale['total']-self.c.execute('SELECT COALESCE(SUM(amount),0) FROM pos_payments WHERE sale_id=?',(sale['id'],)).fetchone()[0]

    def cash(self, shift, kind, amount, details, key, reference=''):
        self.c.execute('INSERT INTO pos_cash(shift_id,user_id,kind,amount,details,reference,created,request_key) VALUES(?,?,?,?,?,?,?,?)', (shift['id'],self.uid,kind,amount,details,reference,stamp(),key))

    def movement(self, item, milli, reason):
        previous=Decimal(str(item['quantity']))
        new=previous+Decimal(milli)/1000
        if new < 0:
            raise ims.ValidationError('Insufficient stock: '+item['name'])
        self.c.execute('UPDATE items SET quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(float(new),item['id']))
        self.c.execute('INSERT INTO stock_movements(item_id,user_id,action,quantity_change,previous_quantity,new_quantity,unit_type,unit_price,total_value,note) VALUES(?,?,?,?,?,?,?,?,?,?)', (item['id'],self.uid,'stock_out' if milli<0 else 'stock_in',milli/1000,float(previous),float(new),item['unit_type'],item['cost_price'],abs(milli/1000)*item['cost_price'],reason))

    def payments(self, data, total):
        rows=data.get('payments',[])
        if not isinstance(rows,list) or len(rows)>10:
            raise ims.ValidationError('Invalid payment list.')
        result=[]
        for p in rows:
            method=p.get('method')
            if method not in {'cash','zanaco','airtel'}:
                raise ims.ValidationError('Choose cash, Zanaco, or Airtel.')
            amount=cents(p.get('amount',0))
            if not amount:
                continue
            reference=text(p.get('reference'),required=method!='cash')
            if method!='cash' and self.c.execute('SELECT 1 FROM pos_payments WHERE method=? AND reference=? AND amount>0',(method,reference)).fetchone():
                raise ims.ValidationError('This payment reference is already recorded. Check it before proceeding.')
            result.append((method,amount,reference))
        if sum(p[1] for p in result)>total:
            raise ims.ValidationError('Allocated payments exceed the balance. Enter cash received separately for change.')
        return result

    def add_payments(self, sale_id, shift, rows, key):
        for n,(method,amount,reference) in enumerate(rows):
            self.c.execute('INSERT INTO pos_payments(sale_id,shift_id,user_id,method,amount,reference,created,request_key) VALUES(?,?,?,?,?,?,?,?)',(sale_id,shift['id'],self.uid,method,amount,reference,stamp(),key+':'+str(n)))
            if method=='cash':
                self.cash(shift,'sale_cash',amount,sale_id,key+':cash:'+str(n))

    def act(self, action, d):
        with self.transaction():
            key=text(d.get('key')) if action in {'checkout','repay','cash','refund','withdraw'} else ''
            if key:
                try:uuid.UUID(key)
                except ValueError:raise ims.ValidationError('Invalid request identifier. Reload the page.')
            if action=='withdraw' and self.c.execute('SELECT 1 FROM pos_requests WHERE request_key=?',(key,)).fetchone():return {'duplicate':True}
            if action=='catalog':
                self.owner()
                for name,unit,price in [('Fish','kg',68),('Sausage','kg',100),('Fresh kapenta','pack',30),('Buka fish','kg',90),('Chicken pieces','kg',120),('Game meat (bundle)','pack',350)]:
                    if not self.c.execute('SELECT 1 FROM items WHERE name=?',(name,)).fetchone():
                        self.c.execute('INSERT INTO items(name,category,unit_type,quantity,cost_price,selling_price,reorder_level) VALUES(?,?,?,?,?,?,?)',(name,'Fresh products',unit,0,0,price,5))
            elif action=='open':
                opening=cents(d.get('opening'))
                last_close=self.c.execute("SELECT details FROM pos_events WHERE kind='closing_summary' ORDER BY id DESC LIMIT 1").fetchone()
                last_float=json.loads(last_close['details'])['remaining'] if last_close else 50000
                if opening!=50000 or opening!=last_float:
                    text(d.get('explanation'))
                self.c.execute('INSERT INTO pos_shifts(user_id,opened,opening,explanation) VALUES(?,?,?,?)',(self.uid,stamp(),opening,text(d.get('explanation'),False)))
            elif action=='checkout':
                existing=self.c.execute('SELECT id,user_id FROM pos_sales WHERE request_key=?',(key,)).fetchone()
                if existing:
                    if existing['user_id']!=self.uid: raise ims.AuthorizationError('Request belongs to another user.')
                    return {'sale_id':existing['id'],'duplicate':True}
                shift=self.shift()
                cart=d.get('items')
                if not isinstance(cart,list) or not 1<=len(cart)<=100:
                    raise ims.ValidationError('Basket must contain 1–100 products.')
                lines=[]; seen=set(); total=0
                for line in cart:
                    item=self.c.execute('SELECT * FROM items WHERE id=?',(int(line['id']),)).fetchone()
                    if not item or item['id'] in seen: raise ims.ValidationError('Invalid or repeated product.')
                    seen.add(item['id']); quantity=qty(line['quantity'],item['unit_type'])
                    if Decimal(str(item['quantity']))*1000<quantity: raise ims.ValidationError('Insufficient stock: '+item['name'])
                    price=cents(item['selling_price'])
                    subtotal=int((Decimal(price)*quantity/1000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
                    if subtotal<=0: raise ims.ValidationError('Product must have a positive sale value.')
                    total+=subtotal;lines.append((item,quantity,price,subtotal))
                rows=self.payments(d,total); paid=sum(p[1] for p in rows)
                if paid<total:
                    for field in ('customer','contact','recipient','authorization','due'): text(d.get(field))
                    try: datetime.strptime(d['due'],'%Y-%m-%d')
                    except ValueError: raise ims.ValidationError('Supply the agreed due date.')
                cash=sum(p[1] for p in rows if p[0]=='cash')
                if cash and cents(d.get('tendered',0))<cash: raise ims.ValidationError('Cash received is less than the cash allocation.')
                sid='PAP-'+uuid.uuid4().hex[:12].upper()
                self.c.execute('INSERT INTO pos_sales(id,request_key,shift_id,user_id,created,total,customer,contact,recipient,due,authorization) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(sid,key,shift['id'],self.uid,stamp(),total,*[text(d.get(k),False) for k in ('customer','contact','recipient','due','authorization')]))
                for item,quantity,price,subtotal in lines:
                    self.c.execute('INSERT INTO pos_lines(sale_id,item_id,name,category,unit,quantity,unit_price,total) VALUES(?,?,?,?,?,?,?,?)',(sid,item['id'],item['name'],item['category'],item['unit_type'],quantity,price,subtotal))
                    self.movement(item,-quantity,'Sale '+sid)
                self.add_payments(sid,shift,rows,key)
                self.event('checkout',{'sale':sid,'total':total,'credit':total-paid,'tendered':cents(d.get('tendered',0)),'change':cents(d.get('tendered',0))-cash if cash else 0})
                return {'sale_id':sid}
            elif action=='repay':
                if self.c.execute('SELECT 1 FROM pos_payments WHERE request_key LIKE ?',(key+':%',)).fetchone(): return {'duplicate':True}
                shift=self.shift(); sale=self.c.execute('SELECT * FROM pos_sales WHERE id=?',(text(d.get('sale_id')),)).fetchone()
                if not sale or sale['reversed']: raise ims.ValidationError('Sale unavailable.')
                rows=self.payments(d,self.balance(sale))
                if not rows: raise ims.ValidationError('Enter a payment.')
                cash=sum(p[1] for p in rows if p[0]=='cash')
                if cash and cents(d.get('tendered',0))<cash:raise ims.ValidationError('Cash received is less than the cash repayment.')
                self.add_payments(sale['id'],shift,rows,key); self.event('credit_repayment',{'sale':sale['id'],'payments':rows,'tendered':cents(d.get('tendered',0)),'change':cents(d.get('tendered',0))-cash if cash else 0})
            elif action=='cash':
                if self.c.execute('SELECT 1 FROM pos_cash WHERE request_key=?',(key,)).fetchone():return {'duplicate':True}
                shift=self.shift(('open','counted'));kind=d.get('kind');amount=cents(d.get('amount'))
                if not amount: raise ims.ValidationError('Amount must be positive.')
                if kind not in {'expense','owner_deposit','cash_added','cash_returned'}:raise ims.ValidationError('Invalid cash movement.')
                details=text(d.get('details'))
                if kind=='expense':
                    category=text(d.get('category'))
                    recipient=text(d.get('recipient'))
                    approval=text(d.get('authorization'),required=category not in {'lunch','plastics'})
                    details=json.dumps({'reason':details,'category':category,'recipient':recipient,'approval':approval or 'Routine permitted expense — pending owner review'})
                if kind=='owner_deposit': details=json.dumps({'request':details,'agent':text(d.get('recipient'))})
                if kind in {'cash_added','cash_returned'}: self.owner()
                delta=-amount if kind in {'expense','owner_deposit'} else amount
                if self.expected(shift)+delta<0:raise ims.ValidationError('This would make expected till cash negative.')
                if shift['status']=='counted' and kind!='owner_deposit':raise ims.ValidationError('After the count, only record the closing owner deposit.')
                self.cash(shift,kind,delta,details,key,text(d.get('reference'),kind=='owner_deposit'))
            elif action=='confirm_cash':
                self.owner(); row=self.c.execute('SELECT * FROM pos_cash WHERE id=?',(int(d['id']),)).fetchone()
                if not row:raise ims.ValidationError('Movement not found.')
                if row['confirmed_by']:raise ims.ValidationError('Already reviewed.')
                self.c.execute('UPDATE pos_cash SET confirmed_by=? WHERE id=?',(self.uid,row['id']))
                self.event('cash_review',{'movement':row['id'],'confirmation':text(d.get('details'))})
            elif action=='review_credit':
                self.owner();sid=text(d.get('sale_id'))
                if not self.c.execute('SELECT 1 FROM pos_sales WHERE id=?',(sid,)).fetchone():raise ims.ValidationError('Sale not found.')
                self.c.execute('INSERT INTO pos_credit_reviews VALUES(?,?,?,?)',(sid,self.uid,text(d.get('details')),stamp()))
            elif action=='confirm_payment':
                self.owner();self.c.execute('UPDATE pos_payments SET reviewed_by=? WHERE id=?',(self.uid,int(d['id'])))
                self.event('payment_review',{'payment':int(d['id']),'details':text(d.get('details'))})
            elif action=='start_close':
                shift=self.shift(); self.c.execute("UPDATE pos_shifts SET status='closing',close_started=? WHERE id=?",(stamp(),shift['id']))
            elif action in {'count','recount'}:
                shift=self.shift(('closing',) if action=='count' else ('counted',)); counts=d.get('denominations')
                if action=='recount':text(d.get('explanation'))
                if not isinstance(counts,dict) or set(counts)-{'50000','20000','10000','5000','2000','1000','500','200','100','50','10','5'}: raise ims.ValidationError('Invalid denominations.')
                amount=0
                for denomination,n in counts.items():
                    if isinstance(n,bool) or not isinstance(n,int) or not 0<=n<=100000: raise ims.ValidationError('Enter whole note/coin counts.')
                    amount+=int(denomination)*n
                cutoff=self.c.execute('SELECT COALESCE(MAX(id),0) FROM pos_cash').fetchone()[0]
                self.c.execute('INSERT INTO pos_counts(shift_id,user_id,amount,expected,cash_cutoff,denominations,reason,created) VALUES(?,?,?,?,?,?,?,?)',(shift['id'],self.uid,amount,self.expected(shift),cutoff,json.dumps(counts),text(d.get('explanation'),False),stamp()))
                if action=='count':
                    self.c.execute("UPDATE pos_shifts SET status='counted',counted_at=?,counted=?,expected=?,denominations=?,explanation=? WHERE id=?",(stamp(),amount,self.expected(shift),json.dumps(counts),text(d.get('explanation'),False),shift['id']))
            elif action=='finish_close':
                shift=self.shift(('counted',));remaining=cents(d.get('remaining')); reason=text(d.get('explanation'),False)
                last=self.c.execute('SELECT * FROM pos_counts WHERE shift_id=? ORDER BY id DESC LIMIT 1',(shift['id'],)).fetchone()
                removed=self.c.execute("SELECT COALESCE(-SUM(amount),0) FROM pos_cash WHERE shift_id=? AND id>? AND kind='owner_deposit'",(shift['id'],last['cash_cutoff'])).fetchone()[0]
                if remaining!=last['amount']-removed:raise ims.ValidationError('Remaining float must equal the latest physical count minus subsequent closing deposits.')
                if (remaining!=50000 or shift['counted']!=shift['expected'] or last['amount']!=last['expected']) and not reason:raise ims.ValidationError('Explain the first/final variance or non-K500 float.')
                self.c.execute("UPDATE pos_shifts SET status='closed',closed=? WHERE id=?",(stamp(),shift['id']))
                self.event('closing_summary',{'shift':shift['id'],'remaining':remaining,'first_variance':shift['counted']-shift['expected'],'final_variance':last['amount']-last['expected'],'explanation':reason})
            elif action=='resume':
                shift=self.shift(('closing',)); self.owner();self.c.execute("UPDATE pos_shifts SET status='open',close_started=NULL WHERE id=?",(shift['id'],));text(d.get('explanation'))
            elif action=='review_shift':
                self.owner(); row=self.c.execute('SELECT * FROM pos_shifts WHERE id=?',(int(d['id']),)).fetchone()
                if not row or row['status']!='closed':raise ims.ValidationError('Close the shift first.')
                if self.c.execute("SELECT 1 FROM pos_cash WHERE shift_id=? AND kind='owner_deposit' AND confirmed_by IS NULL",(row['id'],)).fetchone():raise ims.ValidationError('Confirm all owner deposits before reconciling.')
                if self.c.execute("SELECT 1 FROM pos_cash WHERE shift_id=? AND kind='expense' AND confirmed_by IS NULL",(row['id'],)).fetchone():raise ims.ValidationError('Review all expenses before reconciling.')
                if self.c.execute("SELECT 1 FROM pos_payments WHERE shift_id=? AND method!='cash' AND reviewed_by IS NULL",(row['id'],)).fetchone():raise ims.ValidationError('Reconcile electronic receipts before reviewing the shift.')
                if self.c.execute("SELECT 1 FROM pos_sales s WHERE s.shift_id=? AND s.customer!='' AND s.reversed=0 AND NOT EXISTS(SELECT 1 FROM pos_credit_reviews r WHERE r.sale_id=s.id)",(row['id'],)).fetchone():raise ims.ValidationError('Verify the declared credit authorizations first.')
                self.c.execute('UPDATE pos_shifts SET reviewed_by=? WHERE id=?',(self.uid,row['id']))
                text(d.get('details'))
            elif action=='withdraw':
                self.owner();shift=self.shift(owner_override=True);item=self.c.execute('SELECT * FROM items WHERE id=?',(int(d['item_id']),)).fetchone()
                if not item:raise ims.ValidationError('Product not found.')
                quantity=qty(d['quantity'],item['unit_type']); reason=text(d.get('reason'));mode=d.get('mode')
                if mode not in {'dawari','disposal','staff_use','gift'}:raise ims.ValidationError('Choose a stock withdrawal reason.')
                self.movement(item,-quantity,mode+': '+reason)
                if mode=='dawari':
                    price=cents(d['price'])
                    if not price:raise ims.ValidationError('Set a positive approved ma dawari price.')
                    name=item['name']+' · ma dawari · '+uuid.uuid4().hex[:6]
                    cur=self.c.execute('INSERT INTO items(name,category,unit_type,quantity,cost_price,selling_price,supplier,reorder_level) VALUES(?,?,?,?,?,?,?,?)',(name,'Ma dawari',item['unit_type'],0,item['cost_price'],price/100,item['supplier'],0))
                    target=self.c.execute('SELECT * FROM items WHERE id=?',(cur.lastrowid,)).fetchone();self.movement(target,quantity,'Reclassified from '+item['name'])
            elif action=='refund':
                self.owner()
                if self.c.execute('SELECT 1 FROM pos_cash WHERE request_key=?',(key,)).fetchone():return {'duplicate':True}
                shift=self.shift(owner_override=True);sale=self.c.execute('SELECT * FROM pos_sales WHERE id=?',(text(d['sale_id']),)).fetchone()
                if not sale or sale['reversed']:raise ims.ValidationError('Sale unavailable or already reversed.')
                reason=text(d.get('reason')); paid=sale['total']-self.balance(sale)
                rows=self.payments(d,paid)
                if sum(p[1] for p in rows)!=paid:raise ims.ValidationError('Full reversal must refund exactly the amount received, including repayments.')
                refund_cash=sum(p[1] for p in rows if p[0]=='cash')
                if refund_cash>self.expected(shift):raise ims.ValidationError('Insufficient expected till cash for refund.')
                for line in self.c.execute('SELECT * FROM pos_lines WHERE sale_id=?',(sale['id'],)).fetchall():
                    if d.get('restock') is True:
                        item=self.c.execute('SELECT * FROM items WHERE id=?',(line['item_id'],)).fetchone();self.movement(item,line['quantity'],'Sale reversal '+sale['id'])
                self.c.execute('UPDATE pos_sales SET reversed=1 WHERE id=?',(sale['id'],))
                self.cash(shift,'refund',-refund_cash,json.dumps({'sale':sale['id'],'payments':rows,'reason':reason,'restock':d.get('restock') is True}),key)
            elif action=='barcode':
                self.owner();item_id=int(d['item_id']);code=text(d.get('barcode'))
                self.c.execute('INSERT INTO pos_barcodes(item_id,barcode) VALUES(?,?) ON CONFLICT(item_id) DO UPDATE SET barcode=excluded.barcode',(item_id,code))
            elif action=='exception':
                shift=self.shift();self.event('payment_exception',{'shift':shift['id'],'method':text(d.get('method')),'amount':cents(d.get('amount')),'reference':text(d.get('reference')),'goods_handed_over':bool(d.get('goods_handed_over')),'details':text(d.get('details'))})
                if d.get('goods_handed_over'):raise ims.ValidationError('If goods leave unpaid, record an owner-authorized credit sale and reference the dispute. This exception log does not deduct stock.')
            elif action=='resolve_exception':
                self.owner();event=self.c.execute("SELECT * FROM pos_events WHERE id=? AND kind='payment_exception'",(int(d['id']),)).fetchone()
                if not event:raise ims.ValidationError('Exception not found.')
                self.event('exception_resolution',{'exception':event['id'],'details':text(d.get('details'))})
            else:raise ims.ValidationError('Unknown operation.')
            details=dict(d);details.pop('key',None)
            if action in {'count','recount'}:details={'shift':shift['id'],'cash_id':self.c.execute('SELECT COALESCE(MAX(id),0) FROM pos_cash').fetchone()[0]}
            self.event(action,details)
            if action=='withdraw':self.c.execute('INSERT INTO pos_requests VALUES(?,?,?)',(key,self.uid,action))
        return {'ok':True}

    def state(self):
        owner=self.user['role'] in {'admin','manager'}
        shifts=[dict(r) for r in self.c.execute('SELECT s.*,u.username FROM pos_shifts s JOIN users u ON u.id=s.user_id ORDER BY s.id DESC LIMIT 100')]
        for s in shifts:
            last=self.c.execute('SELECT * FROM pos_counts WHERE shift_id=? ORDER BY id DESC LIMIT 1',(s['id'],)).fetchone()
            s['latest_count']=dict(last) if last else None
            if owner or s['status'] in {'counted','closed'}:
                s['payment_totals']={r['method']:r['total'] for r in self.c.execute('SELECT method,SUM(amount) total FROM pos_payments WHERE shift_id=? GROUP BY method',(s['id'],))}
                s['cash_totals']={r['kind']:r['total'] for r in self.c.execute('SELECT kind,SUM(amount) total FROM pos_cash WHERE shift_id=? GROUP BY kind',(s['id'],))}
                s['sales_total']=self.c.execute('SELECT COALESCE(SUM(total),0) FROM pos_sales WHERE shift_id=? AND reversed=0',(s['id'],)).fetchone()[0]
            if s['status'] in {'open','closing'} and not owner:
                s['expected']=None
            elif s['status']=='open':s['expected']=self.expected(s)
        sales=[]
        for r in self.c.execute('SELECT * FROM pos_sales ORDER BY rowid DESC'):
            sale=dict(r);sale['balance']=self.balance(r);sale['credit_reviewed']=bool(self.c.execute('SELECT 1 FROM pos_credit_reviews WHERE sale_id=?',(sale['id'],)).fetchone());sales.append(sale)
        cash=[dict(r) for r in self.c.execute('SELECT * FROM pos_cash WHERE confirmed_by IS NULL OR id IN (SELECT id FROM pos_cash ORDER BY id DESC LIMIT 1000) ORDER BY id DESC')]
        payments=[dict(r) for r in self.c.execute('SELECT * FROM pos_payments WHERE reviewed_by IS NULL OR id IN (SELECT id FROM pos_payments ORDER BY id DESC LIMIT 1000) ORDER BY id DESC')]
        if not owner:
            active=next((s for s in shifts if s['status']!='closed'),None)
            # Hide pre-count cash totals, including historical records, from the blind-count screen.
            if active and active['status'] in {'open','closing'}:
                cash=[];payments=[]
        categories=[dict(r) for r in self.c.execute('SELECT l.category, SUM(l.total) total FROM pos_lines l JOIN pos_sales s ON s.id=l.sale_id WHERE s.reversed=0 GROUP BY l.category')]
        items=ims.ItemRepository().all()
        codes={r['item_id']:r['barcode'] for r in self.c.execute('SELECT * FROM pos_barcodes')}
        for item in items:item['barcode']=codes.get(item['id'],'')
        if not owner and any(s['status']=='closing' for s in shifts):sales=[]
        return {'items':items,'shifts':shifts,'sales':sales,'cash':cash,'payments':payments,'categories':categories if owner else [],'events':[dict(r) for r in self.c.execute('SELECT * FROM pos_events ORDER BY id DESC LIMIT 300')] if owner else []}
