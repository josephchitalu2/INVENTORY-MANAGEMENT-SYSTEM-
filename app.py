"""Vercel entry point: isolated, browser-persisted portfolio demo.

Never uses the CLI's real database. Snapshots are untrusted synthetic demo data,
not authenticated business records. Each request gets its own SQLite database.
"""
import math
import secrets
import sqlite3
from contextlib import contextmanager

from flask import Flask, jsonify, render_template, request
import ims

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 1_000_000
TABLES = {'items': 100, 'stock_movements': 500, 'audit_log': 1000}
# Fixed hash of a random, discarded password; the demo has no login endpoint.
DEMO_HASH = ims.hash_password(secrets.token_urlsafe(32))


def validate_tree(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ims.ValidationError('Numbers must be finite')
    if isinstance(value, str) and len(value) > 2000:
        raise ims.ValidationError('Text fields must be at most 2000 characters')
    if isinstance(value, dict):
        for child in value.values():
            validate_tree(child)
    elif isinstance(value, list):
        for child in value:
            validate_tree(child)


@contextmanager
def workspace(snapshot):
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    token = ims.REQUEST_DATABASE.set(conn)
    try:
        ims.init_database()
        conn.execute('INSERT INTO users(id,username,password_hash,role) VALUES(1,?,?,?)',
                     ('Demo visitor', DEMO_HASH, 'admin'))
        if snapshot is not None:
            if not isinstance(snapshot, dict) or snapshot.get('version') != 1:
                raise ims.ValidationError('Unsupported backup format')
            if set(snapshot) != {'version', *TABLES}:
                raise ims.ValidationError('Invalid backup tables')
            validate_tree(snapshot)
            for table, limit in TABLES.items():
                rows = snapshot[table]
                if not isinstance(rows, list) or len(rows) > limit:
                    raise ims.ValidationError(f'Demo limit: {limit} {table} records')
                columns = [r['name'] for r in conn.execute(f'PRAGMA table_info({table})')]
                for row in rows:
                    if not isinstance(row, dict) or set(row) != set(columns):
                        raise ims.ValidationError('Invalid backup fields')
                    if any(isinstance(v, (dict, list, bool)) for v in row.values()):
                        raise ims.ValidationError('Invalid backup value')
                    conn.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',
                                 [row[c] for c in columns])
            for item in ims.ItemRepository().all():
                if not isinstance(item['name'], str) or not item['name'].strip():
                    raise ims.ValidationError('Item name is required')
                for key in ('quantity', 'cost_price', 'selling_price', 'reorder_level'):
                    ims.validate_price(item[key], key)
                if item['unit_type'] in ims.DISCRETE_UNITS:
                    if not float(item['quantity']).is_integer() or not float(item['reorder_level']).is_integer():
                        raise ims.ValidationError('Discrete units require whole quantities')
        conn.commit()
        yield conn
    finally:
        ims.REQUEST_DATABASE.reset(token)
        conn.close()


def snapshot_of(conn):
    snapshot = {'version': 1}
    for table, limit in TABLES.items():
        rows = [dict(r) for r in conn.execute(f'SELECT * FROM {table} ORDER BY id')]
        if len(rows) > limit:
            raise ims.ValidationError('Demo storage limit reached. Download a backup, then reset the demo.')
        snapshot[table] = rows
    return snapshot


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


@app.get('/')
def home():
    return render_template('index.html')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'isolated-browser-demo'}


@app.post('/api/inventory')
def inventory():
    if not request.is_json:
        return jsonify(error='Send application/json'), 415
    body = request.get_json()
    if not isinstance(body, dict):
        return jsonify(error='Expected a JSON object'), 400
    action = body.get('action', 'load')
    data = body.get('data', {})
    if not isinstance(data, dict):
        return jsonify(error='Invalid form data'), 400
    validate_tree(data)
    with workspace(None if action == 'reset' else body.get('snapshot')) as conn:
        service = ims.InventoryService()
        if action == 'seed' or (action == 'load' and body.get('snapshot') is None):
            ims.seed_demo(1)
        elif action == 'add':
            service.add_item(1, name=str(data.get('name', '')), category=str(data.get('category', '')),
                             unit_type=str(data.get('unit_type', 'kg')), quantity=float(data.get('quantity', 0)),
                             cost_price=float(data.get('cost_price', 0)), selling_price=float(data.get('selling_price', 0)),
                             supplier=str(data.get('supplier', '')), reorder_level=float(data.get('reorder_level', 5)))
        elif action == 'stock':
            service.adjust_stock(1, int(data.get('item_id', 0)), float(data.get('amount', 0)),
                                 str(data.get('direction', '')), str(data.get('note', '')))
        elif action == 'update':
            changes = {k: v for k, v in data.items() if k in {'name', 'category', 'cost_price', 'selling_price', 'supplier', 'reorder_level'}}
            service.update_item(1, int(data.get('item_id', 0)), **changes)
        elif action not in {'load', 'reset'}:
            raise ims.ValidationError('Unknown action')
        snapshot = snapshot_of(conn)
        return jsonify(snapshot=snapshot, items=service.items.all(),
                       movements=ims.ReportService().movements(), audit=ims.ReportService().audit())


@app.errorhandler(ims.IMSException)
@app.errorhandler(ValueError)
@app.errorhandler(TypeError)
@app.errorhandler(sqlite3.Error)
def invalid(exc):
    message = str(exc) if isinstance(exc, ims.IMSException) else 'Invalid data or backup. Check the supplied values.'
    return jsonify(error=message), 400


@app.errorhandler(413)
def too_large(exc):
    return jsonify(error='Backup is too large. Maximum size is 1 MB.'), 413


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
