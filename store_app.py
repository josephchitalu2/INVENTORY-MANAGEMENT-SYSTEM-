"""Single-PC IMS. Run with python store_app.py; never deploy this on Vercel."""
import hashlib
import csv
import io
import os
from pathlib import Path
import secrets
import sqlite3
import time

from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_file, session
import ims
import papino


def create_app(data_dir=None):
    root = Path(data_dir or os.environ.get('IMS_DATA_DIR', Path.home() / '.local/share/chitalu-ims')).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    secret_path = root / 'session.key'
    try:
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secret_path.read_text(), MAX_CONTENT_LENGTH=65536,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      PERMANENT_SESSION_LIFETIME=1800, TRUSTED_HOSTS=['localhost', '127.0.0.1'])
    database = root / 'inventory.db'

    def connect():
        conn = sqlite3.connect(database, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
        return conn

    conn = connect()
    token = ims.REQUEST_DATABASE.set(conn)
    try:
        ims.init_database()
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS web_sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_attempts (timestamp REAL NOT NULL);
        ''')
        papino.init(conn)
        conn.execute('PRAGMA journal_mode=WAL')
    finally:
        ims.REQUEST_DATABASE.reset(token)
        conn.close()
    os.chmod(database, 0o600)

    def backup():
        directory = root / 'backups'
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / (time.strftime('%Y-%m-%d_%H-%M-%S') + '-' + secrets.token_hex(3) + '.sqlite3')
        with connect() as source, sqlite3.connect(path) as target:
            source.backup(target)
        os.chmod(path, 0o600)
        # Keep the newest 30 automatic copies. External daily copies are separate.
        for old in sorted(directory.glob('*.sqlite3'), key=lambda p: p.stat().st_mtime, reverse=True)[30:]:
            old.unlink()
        return path

    # A consistent backup on each process start, plus one before each stock write.
    backup()

    @app.before_request
    def security():
        g.conn = connect()
        g.db_token = ims.REQUEST_DATABASE.set(g.conn)
        session.setdefault('csrf', secrets.token_hex(32))
        g.user = None
        if session.get('sid'):
            row = g.conn.execute('SELECT user_id FROM web_sessions WHERE token_hash=? AND expires>?',
                (hashlib.sha256(session['sid'].encode()).hexdigest(), time.time())).fetchone()
            if row:
                user = ims.UserRepository().find(row['user_id'])
                if user and user['active']:
                    g.user = user
        if request.method == 'POST':
            csrf = request.headers.get('X-CSRF-Token') or request.form.get('csrf', '')
            if not secrets.compare_digest(csrf, session['csrf']):
                abort(403)
        if request.endpoint not in {'login', 'static', 'health'} and not g.user:
            if request.path.startswith('/api/'):
                return jsonify(error='Please sign in again.'), 401
            return redirect('/login')

    @app.teardown_request
    def close(exc):
        if hasattr(g, 'db_token'):
            ims.REQUEST_DATABASE.reset(g.db_token)
            g.conn.close()

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            cutoff = time.time() - 300
            with g.conn:
                g.conn.execute('DELETE FROM login_attempts WHERE timestamp<?', (cutoff,))
                if g.conn.execute('SELECT COUNT(*) FROM login_attempts').fetchone()[0] >= 10:
                    return render_template('store_login.html', error='Too many attempts. Wait five minutes.'), 429
                g.conn.execute('INSERT INTO login_attempts VALUES(?)', (time.time(),))
            try:
                user = ims.AuthService().authenticate(request.form.get('username', ''), request.form.get('password', ''))
                sid = secrets.token_hex(32)
                with g.conn:
                    g.conn.execute('DELETE FROM login_attempts')
                    g.conn.execute('DELETE FROM web_sessions WHERE expires<?', (time.time(),))
                    g.conn.execute('INSERT INTO web_sessions VALUES(?,?,?)',
                        (hashlib.sha256(sid.encode()).hexdigest(), user['id'], time.time()+1800))
                session.clear()
                session.update(sid=sid, csrf=secrets.token_hex(32))
                session.permanent = True
                return redirect('/')
            except ims.AuthenticationError:
                error = 'Invalid username or password.'
        return render_template('store_login.html', error=error)

    @app.post('/logout')
    def logout():
        with g.conn:
            g.conn.execute('DELETE FROM web_sessions WHERE token_hash=?',
                (hashlib.sha256(session['sid'].encode()).hexdigest(),))
        session.clear()
        return redirect('/login')

    @app.get('/')
    def home():
        return render_template('papino.html', user=g.user)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'mode': 'local-store'}

    @app.post('/api/inventory')
    def inventory():
        body = request.get_json()
        if not isinstance(body, dict) or not isinstance(body.get('data', {}), dict):
            abort(400)
        if body.get('snapshot') is not None:
            return jsonify(error='Browser snapshots cannot replace store records.'), 400
        action, data = body.get('action', 'load'), body.get('data', {})
        service, uid = ims.InventoryService(), g.user['id']
        if action in {'add', 'update', 'stock'}:
            backup()
        if action == 'add':
            service.add_item(uid, name=str(data.get('name', '')), category=str(data.get('category', '')),
                unit_type=str(data.get('unit_type', 'kg')), quantity=float(data.get('quantity', 0)),
                cost_price=float(data.get('cost_price', 0)), selling_price=float(data.get('selling_price', 0)),
                supplier=str(data.get('supplier', '')), reorder_level=float(data.get('reorder_level', 5)))
        elif action == 'stock':
            ims.AuthService().require_role(uid, {'admin', 'manager'})
            if not str(data.get('note', '')).strip():
                raise ims.ValidationError('A stock adjustment reason is required.')
            service.adjust_stock(uid, int(data.get('item_id', 0)), float(data.get('amount', 0)),
                str(data.get('direction', '')), str(data.get('note', '')))
        elif action == 'update':
            changes = {k:v for k,v in data.items() if k in {'name','category','cost_price','selling_price','supplier','reorder_level'}}
            service.update_item(uid, int(data.get('item_id', 0)), **changes)
        elif action != 'load':
            return jsonify(error='This action is unavailable in the store edition.'), 400
        return jsonify(items=service.items.all(), movements=ims.ReportService().movements(), audit=[])

    @app.get('/inventory')
    def inventory_page():
        return render_template('store_index.html', user=g.user)

    @app.get('/api/pos')
    def pos_state():
        return jsonify(papino.POS(g.conn,g.user).state())

    @app.post('/api/pos')
    def pos_action():
        body=request.get_json()
        if not isinstance(body,dict) or not isinstance(body.get('data'),dict):
            abort(400)
        action=body.get('action')
        if action not in {'open','start_close','count','confirm_cash','confirm_payment','review_shift','resolve_exception'}:
            backup()
        return jsonify(papino.POS(g.conn,g.user).act(action,body['data']))

    @app.get('/receipt/<sale_id>')
    def receipt(sale_id):
        sale=g.conn.execute('SELECT s.*,u.username FROM pos_sales s JOIN users u ON u.id=s.user_id WHERE s.id=?',(sale_id,)).fetchone()
        if not sale: abort(404)
        lines=g.conn.execute('SELECT * FROM pos_lines WHERE sale_id=?',(sale_id,)).fetchall()
        payments=g.conn.execute('SELECT * FROM pos_payments WHERE sale_id=? ORDER BY id',(sale_id,)).fetchall()
        return render_template('papino_receipt.html',sale=sale,lines=lines,payments=payments,balance=papino.POS(g.conn,g.user).balance(sale))

    @app.get('/report.csv')
    def report_csv():
        ims.AuthService().require_role(g.user['id'], {'admin','manager'})
        output=io.StringIO()
        writer=csv.writer(output)
        writer.writerow(['record_type','record_id','time','data_json'])
        for table in ('pos_shifts','pos_counts','pos_sales','pos_lines','pos_payments','pos_cash','pos_events'):
            for row in g.conn.execute('SELECT * FROM '+table):
                data=dict(row)
                import json
                writer.writerow([table,str(data.get('id','')),str(data.get('created',data.get('opened',''))),json.dumps(data,ensure_ascii=False)])
        return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='PAPINO-full-ledger.csv')

    @app.get('/backup')
    def download_backup():
        ims.AuthService().require_role(g.user['id'], {'admin'})
        return send_file(backup(), as_attachment=True, download_name='ims-store-backup.sqlite3')

    @app.route('/account', methods=['GET', 'POST'])
    def account():
        message = None
        if request.method == 'POST':
            if request.form.get('action') == 'create_user':
                ims.AuthService().create_user(g.user['id'], request.form.get('username',''),
                    request.form.get('password',''), request.form.get('role','staff'))
                message = 'Staff account created.'
            else:
                ims.AuthService().change_password(g.user['id'], request.form.get('current',''), request.form.get('password',''))
                with g.conn:
                    g.conn.execute('DELETE FROM web_sessions WHERE user_id=?', (g.user['id'],))
                session.clear()
                return redirect('/login')
        return render_template('store_account.html', user=g.user, message=message)

    @app.errorhandler(ims.IMSException)
    @app.errorhandler(ValueError)
    @app.errorhandler(TypeError)
    @app.errorhandler(sqlite3.Error)
    def invalid(exc):
        status = 403 if isinstance(exc, ims.AuthorizationError) else 400
        message = str(exc) if isinstance(exc, ims.IMSException) else 'Invalid data. Check the supplied values.'
        if request.path.startswith('/api/'):
            return jsonify(error=message), status
        return render_template('store_account.html', user=g.user, message=message), status

    return app


if __name__ == '__main__':
    if os.environ.get('VERCEL'):
        raise SystemExit('The store edition requires a persistent PC disk; use app.py for the Vercel demo.')
    from waitress import serve
    application = create_app()
    print('Store IMS: http://127.0.0.1:8080 (this PC only)')
    serve(application, host='127.0.0.1', port=8080, threads=4)
