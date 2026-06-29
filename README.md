# INVENTORY-MANAGEMENT-INVENTORY MANAGEMENT SYSTEM v4.0 - ENTERPRISE EDITION
================================================================================
Production-Ready Inventory Management System

Developer: Joseph Simwinga Chitalu
Version: 4.0
Date: March 2026

Architecture Features:
- Repository Pattern for data access
- Service Layer for business logic
- Custom Exception Hierarchy
- Comprehensive Input Validation
- Full Type Hints
- Detailed Docstrings
- Configuration Management
- Audit Trail
- Transaction Management
- CSV Backup & Restore System
================================================================================
"""

import sys
import os
import sqlite3
import hashlib
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional, Generator
from contextlib import contextmanager
from pathlib import Path

# =============================================================================
# CONFIGURATION
# =============================================================================

APP_NAME = "Inventory Management System v4.0"
APP_VERSION = "4.0"
APP_AUTHOR = "Joseph Simwinga Chitalu"
APP_DATE = "March 2026"

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"
REPORT_DIR = DATA_DIR / "reports"
DATABASE_PATH = DATA_DIR / "inventory.db"

PASSWORD_MIN_LENGTH = 6
DEFAULT_REORDER_LEVEL = 5
DB_POOL_SIZE = 5

# Ensure directories exist
for directory in [DATA_DIR, BACKUP_DIR, REPORT_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


# =============================================================================
# EXCEPTIONS
# =============================================================================

class IMSException(Exception):
    """Base exception for all IMS errors."""
    pass

class DatabaseError(IMSException):
    pass

class AuthenticationError(IMSException):
    pass

class AuthorizationError(IMSException):
    pass

class ValidationError(IMSException):
    pass

class ItemNotFoundError(IMSException):
    pass

class InsufficientStockError(IMSException):
    pass

class DuplicateItemError(IMSException):
    pass

class BackupError(IMSException):
    pass

class UserNotFoundError(IMSException):
    pass


# =============================================================================
# DATABASE CONNECTION
# =============================================================================

@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection with context manager."""
    try:
        conn = sqlite3.connect(str(DATABASE_PATH))
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        raise DatabaseError(f"Database connection failed: {e}")
    finally:
        if conn:
            conn.close()


def execute_query(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute a SELECT query and return results as list of dicts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def execute_write(query: str, params: tuple = ()) -> Optional[int]:
    """Execute an INSERT/UPDATE/DELETE query."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        return cursor.lastrowid if query.strip().upper().startswith('INSERT') else None


def init_database():
    """Initialize the database with all tables and default admin user."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'staff',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Items table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                quantity INTEGER DEFAULT 0,
                price REAL DEFAULT 0.0,
                supplier TEXT,
                reorder_level INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                user_id INTEGER,
                action TEXT,
                quantity_change INTEGER,
                previous_quantity INTEGER,
                new_quantity INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES items(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # Audit log table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                table_name TEXT,
                record_id INTEGER,
                old_values TEXT,
                new_values TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        # Create default admin user
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            default_hash = hashlib.sha256('admin123'.encode()).hexdigest()
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ('admin', default_hash, 'admin')
            )
            print("✅ Default admin created: username='admin', password='admin123'")

        conn.commit()
        print("✅ Database initialized successfully!")


# =============================================================================
# REPOSITORY LAYER
# =============================================================================

class UserRepository:
    """Handles all user-related database operations."""

    def find_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        results = execute_query(
            "SELECT id, username, password_hash, role, created_at FROM users WHERE username = ?",
            (username,)
        )
        return results[0] if results else None

    def find_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        results = execute_query(
            "SELECT id, username, password_hash, role, created_at FROM users WHERE id = ?",
            (user_id,)
        )
        return results[0] if results else None

    def create(self, username: str, password_hash: str, role: str = 'staff') -> int:
        return execute_write(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role)
        )

    def update_password(self, user_id: int, new_hash: str) -> bool:
        execute_write("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
        return True

    def delete(self, user_id: int) -> bool:
        execute_write("DELETE FROM users WHERE id = ?", (user_id,))
        return True

    def list_all(self) -> List[Dict[str, Any]]:
        return execute_query("SELECT id, username, role, created_at FROM users ORDER BY username")


class ItemRepository:
    """Handles all item-related database operations."""

    def find_all(self) -> List[Dict[str, Any]]:
        return execute_query("SELECT * FROM items ORDER BY name")

    def find_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        results = execute_query("SELECT * FROM items WHERE id = ?", (item_id,))
        return results[0] if results else None

    def find_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        results = execute_query("SELECT * FROM items WHERE name = ?", (name,))
        return results[0] if results else None

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        return execute_query(
            "SELECT * FROM items WHERE LOWER(name) LIKE ? OR LOWER(category) LIKE ? ORDER BY name",
            (f'%{keyword.lower()}%', f'%{keyword.lower()}%')
        )

    def find_low_stock(self) -> List[Dict[str, Any]]:
        return execute_query(
            "SELECT * FROM items WHERE quantity <= reorder_level ORDER BY quantity ASC"
        )

    def create(self, data: Dict[str, Any]) -> int:
        return execute_write('''
            INSERT INTO items (name, category, quantity, price, supplier, reorder_level)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data['name'],
            data.get('category', ''),
            data.get('quantity', 0),
            data.get('price', 0.0),
            data.get('supplier', ''),
            data.get('reorder_level', 5)
        ))

    def update(self, item_id: int, data: Dict[str, Any]) -> bool:
        fields = []
        params = []
        for key in ['name', 'category', 'quantity', 'price', 'supplier', 'reorder_level']:
            if key in data:
                fields.append(f"{key} = ?")
                params.append(data[key])

        if not fields:
            return False

        fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(item_id)
        query = f"UPDATE items SET {', '.join(fields)} WHERE id = ?"
        execute_write(query, tuple(params))
        return True

    def update_stock(self, item_id: int, new_quantity: int) -> bool:
        execute_write(
            "UPDATE items SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_quantity, item_id)
        )
        return True

    def delete(self, item_id: int) -> bool:
        execute_write("DELETE FROM items WHERE id = ?", (item_id,))
        return True

    def get_total_value(self) -> float:
        results = execute_query("SELECT SUM(price * quantity) as total FROM items")
        return results[0]['total'] if results and results[0]['total'] else 0.0

    def count(self) -> int:
        results = execute_query("SELECT COUNT(*) as count FROM items")
        return results[0]['count'] if results else 0


class TransactionRepository:
    """Handles all transaction-related database operations."""

    def log(self, item_id: int, user_id: int, action: str,
            quantity_change: int, previous_quantity: int, new_quantity: int) -> int:
        return execute_write('''
            INSERT INTO transactions (item_id, user_id, action, quantity_change, previous_quantity, new_quantity)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (item_id, user_id, action, quantity_change, previous_quantity, new_quantity))

    def find_all(self) -> List[Dict[str, Any]]:
        return execute_query('''
            SELECT t.*, i.name as item_name, u.username
            FROM transactions t
            JOIN items i ON t.item_id = i.id
            JOIN users u ON t.user_id = u.id
            ORDER BY t.timestamp DESC
        ''')

    def find_by_item(self, item_id: int) -> List[Dict[str, Any]]:
        return execute_query('''
            SELECT t.*, u.username
            FROM transactions t
            JOIN users u ON t.user_id = u.id
            WHERE t.item_id = ?
            ORDER BY t.timestamp DESC
        ''', (item_id,))


class AuditLogRepository:
    """Handles audit trail operations."""

    def log(self, user_id: int, action: str, table_name: str,
            record_id: int, old_values: str = '', new_values: str = '') -> int:
        return execute_write('''
            INSERT INTO audit_log (user_id, action, table_name, record_id, old_values, new_values)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, action, table_name, record_id, old_values, new_values))


# =============================================================================
# SERVICE LAYER
# =============================================================================

class AuthService:
    """Handles authentication and user management."""

    def __init__(self):
        self.user_repo = UserRepository()
        self.audit_repo = AuditLogRepository()

    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        if not username or not password:
            raise ValidationError("Username and password are required")

        user = self.user_repo.find_by_username(username)
        if not user:
            return None

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if user['password_hash'] != password_hash:
            return None

        self.audit_repo.log(
            user_id=user['id'],
            action='login',
            table_name='users',
            record_id=user['id'],
            new_values="Login successful"
        )

        del user['password_hash']
        return user

    def create_user(self, admin_id: int, username: str, password: str, role: str = 'staff') -> int:
        if len(password) < 6:
            raise ValidationError("Password must be at least 6 characters")
        if role not in ['admin', 'manager', 'staff']:
            raise ValidationError("Invalid role. Must be admin, manager, or staff")

        existing = self.user_repo.find_by_username(username)
        if existing:
            raise DuplicateItemError(f"Username '{username}' already exists")

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        user_id = self.user_repo.create(username, password_hash, role)

        self.audit_repo.log(
            user_id=admin_id,
            action='create_user',
            table_name='users',
            record_id=user_id,
            new_values=f"Username: {username}, Role: {role}"
        )
        return user_id

    def change_password(self, user_id: int, current_password: str, new_password: str) -> bool:
        user = self.user_repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError("User not found")

        current_hash = hashlib.sha256(current_password.encode()).hexdigest()
        if user['password_hash'] != current_hash:
            raise AuthenticationError("Current password is incorrect")

        if len(new_password) < 6:
            raise ValidationError("New password must be at least 6 characters")

        new_hash = hashlib.sha256(new_password.encode()).hexdigest()
        result = self.user_repo.update_password(user_id, new_hash)

        self.audit_repo.log(
            user_id=user_id,
            action='change_password',
            table_name='users',
            record_id=user_id,
            new_values="Password changed"
        )
        return result


class InventoryService:
    """Handles all inventory operations."""

    def __init__(self):
        self.item_repo = ItemRepository()
        self.transaction_repo = TransactionRepository()
        self.audit_repo = AuditLogRepository()

    def add_item(self, user_id: int, data: Dict[str, Any]) -> int:
        if not data.get('name'):
            raise ValidationError("Item name is required")

        existing = self.item_repo.find_by_name(data['name'])
        if existing:
            raise DuplicateItemError(f"Item '{data['name']}' already exists")

        item_id = self.item_repo.create(data)

        self.transaction_repo.log(
            item_id=item_id,
            user_id=user_id,
            action='added',
            quantity_change=data.get('quantity', 0),
            previous_quantity=0,
            new_quantity=data.get('quantity', 0)
        )

        self.audit_repo.log(
            user_id=user_id,
            action='add_item',
            table_name='items',
            record_id=item_id,
            new_values=f"Added: {data.get('name')}, Qty: {data.get('quantity', 0)}"
        )
        return item_id

    def get_all_items(self) -> List[Dict[str, Any]]:
        return self.item_repo.find_all()

    def get_item(self, item_id: int) -> Dict[str, Any]:
        item = self.item_repo.find_by_id(item_id)
        if not item:
            raise ItemNotFoundError(f"Item with ID {item_id} not found")
        return item

    def update_item(self, user_id: int, item_id: int, data: Dict[str, Any]) -> bool:
        current = self.item_repo.find_by_id(item_id)
        if not current:
            raise ItemNotFoundError(f"Item with ID {item_id} not found")

        result = self.item_repo.update(item_id, data)

        if 'quantity' in data and data['quantity'] != current['quantity']:
            self.transaction_repo.log(
                item_id=item_id,
                user_id=user_id,
                action='updated',
                quantity_change=data['quantity'] - current['quantity'],
                previous_quantity=current['quantity'],
                new_quantity=data['quantity']
            )

        self.audit_repo.log(
            user_id=user_id,
            action='update_item',
            table_name='items',
            record_id=item_id,
            old_values=f"Name: {current['name']}, Qty: {current['quantity']}",
            new_values=f"Name: {data.get('name', current['name'])}, Qty: {data.get('quantity', current['quantity'])}"
        )
        return result

    def delete_item(self, user_id: int, item_id: int) -> bool:
        current = self.item_repo.find_by_id(item_id)
        if not current:
            raise ItemNotFoundError(f"Item with ID {item_id} not found")

        self.transaction_repo.log(
            item_id=item_id,
            user_id=user_id,
            action='deleted',
            quantity_change=-current['quantity'],
            previous_quantity=current['quantity'],
            new_quantity=0
        )

        self.audit_repo.log(
            user_id=user_id,
            action='delete_item',
            table_name='items',
            record_id=item_id,
            old_values=f"Deleted: {current['name']}, Qty: {current['quantity']}"
        )
        return self.item_repo.delete(item_id)

    def adjust_stock(self, user_id: int, item_id: int, amount: int, action: str) -> int:
        if amount <= 0:
            raise ValidationError("Amount must be a positive number")

        current = self.item_repo.find_by_id(item_id)
        if not current:
            raise ItemNotFoundError(f"Item with ID {item_id} not found")

        new_quantity = current['quantity']

        if action == 'add':
            new_quantity += amount
            action_type = 'stock_in'
        elif action == 'remove':
            if amount > current['quantity']:
                raise InsufficientStockError(
                    f"Not enough stock. Current: {current['quantity']}, Requested: {amount}"
                )
            new_quantity -= amount
            action_type = 'stock_out'
        else:
            raise ValidationError("Action must be 'add' or 'remove'")

        self.item_repo.update_stock(item_id, new_quantity)

        self.transaction_repo.log(
            item_id=item_id,
            user_id=user_id,
            action=action_type,
            quantity_change=amount if action == 'add' else -amount,
            previous_quantity=current['quantity'],
            new_quantity=new_quantity
        )

        self.audit_repo.log(
            user_id=user_id,
            action=f'stock_{action}',
            table_name='items',
            record_id=item_id,
            old_values=f"Qty: {current['quantity']}",
            new_values=f"Qty: {new_quantity}"
        )
        return new_quantity

    def search_items(self, keyword: str) -> List[Dict[str, Any]]:
        if not keyword:
            raise ValidationError("Search keyword is required")
        return self.item_repo.search(keyword)

    def get_low_stock_items(self) -> List[Dict[str, Any]]:
        return self.item_repo.find_low_stock()

    def get_total_inventory_value(self) -> float:
        return self.item_repo.get_total_value()

    def get_item_count(self) -> int:
        return self.item_repo.count()


class ReportService:
    """Handles all report generation."""

    def __init__(self):
        self.item_repo = ItemRepository()
        self.transaction_repo = TransactionRepository()
        self.audit_repo = AuditLogRepository()

    def _generate_serial(self) -> str:
        return datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]

    def _write_csv_report(self, filename: str, headers: List[str], rows: List[List[Any]]) -> str:
        filepath = REPORT_DIR / filename
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        return str(filepath)

    def generate_inventory_report(self, user_id: int) -> Dict[str, Any]:
        items = self.item_repo.find_all()
        total_value = self.item_repo.get_total_value()
        item_count = len(items)

        serial = self._generate_serial()
        filename = f"inventory_report_{serial}.csv"

        headers = ['Serial No.', 'ID', 'Name', 'Category', 'Quantity', 'Price', 'Supplier', 'Reorder Level']
        rows = []
        for idx, item in enumerate(items, 1):
            rows.append([
                idx, item['id'], item['name'], item['category'] or 'N/A',
                item['quantity'], f"{item['price']:.2f}",
                item['supplier'] or 'N/A', item['reorder_level']
            ])

        rows.append([])
        rows.append(['TOTAL ITEMS:', item_count])
        rows.append(['TOTAL VALUE:', f"{total_value:.2f}"])
        rows.append(['GENERATED:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

        filepath = self._write_csv_report(filename, headers, rows)

        self.audit_repo.log(
            user_id=user_id,
            action='generate_report',
            table_name='report_logs',
            record_id=0,
            new_values=f"Inventory report: {filename}, {item_count} items"
        )

        return {
            'type': 'inventory',
            'generated_by': user_id,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_items': item_count,
            'total_value': total_value,
            'file_path': filepath,
            'filename': filename,
            'data': items
        }

    def generate_low_stock_report(self, user_id: int) -> Dict[str, Any]:
        items = self.item_repo.find_low_stock()
        item_count = len(items)

        serial = self._generate_serial()
        filename = f"low_stock_report_{serial}.csv"

        headers = ['Serial No.', 'ID', 'Name', 'Category', 'Current Qty', 'Reorder Level', 'Shortage']
        rows = []
        for idx, item in enumerate(items, 1):
            shortage = item['reorder_level'] - item['quantity']
            rows.append([
                idx, item['id'], item['name'], item['category'] or 'N/A',
                item['quantity'], item['reorder_level'], shortage
            ])

        rows.append([])
        rows.append(['TOTAL LOW STOCK ITEMS:', item_count])
        rows.append(['GENERATED:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

        filepath = self._write_csv_report(filename, headers, rows)

        self.audit_repo.log(
            user_id=user_id,
            action='generate_report',
            table_name='report_logs',
            record_id=0,
            new_values=f"Low stock report: {filename}, {item_count} items"
        )

        return {
            'type': 'low_stock',
            'generated_by': user_id,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_low_stock_items': item_count,
            'file_path': filepath,
            'filename': filename,
            'data': items
        }

    def generate_transaction_report(self, user_id: int) -> Dict[str, Any]:
        transactions = self.transaction_repo.find_all()
        count = len(transactions)

        serial = self._generate_serial()
        filename = f"transaction_report_{serial}.csv"

        headers = ['Serial No.', 'Item', 'User', 'Action', 'Change', 'Previous Qty', 'New Qty', 'Timestamp']
        rows = []
        for idx, t in enumerate(transactions, 1):
            rows.append([
                idx, t['item_name'], t['username'], t['action'],
                t['quantity_change'] or 0, t['previous_quantity'] or 0,
                t['new_quantity'] or 0, t['timestamp']
            ])

        rows.append([])
        rows.append(['TOTAL TRANSACTIONS:', count])
        rows.append(['GENERATED:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')])

        filepath = self._write_csv_report(filename, headers, rows)

        self.audit_repo.log(
            user_id=user_id,
            action='generate_report',
            table_name='report_logs',
            record_id=0,
            new_values=f"Transaction report: {filename}, {count} transactions"
        )

        return {
            'type': 'transactions',
            'generated_by': user_id,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_transactions': count,
            'file_path': filepath,
            'filename': filename,
            'data': transactions
        }


class BackupService:
    """Handles backup and restore operations."""

    def __init__(self):
        self.item_repo = ItemRepository()
        self.transaction_repo = TransactionRepository()
        self.user_repo = UserRepository()
        self.audit_repo = AuditLogRepository()

    def _export_table_to_csv(self, table_data: List[Dict], table_name: str, timestamp: str) -> Optional[str]:
        if not table_data:
            return None

        filename = f"{table_name}_{timestamp}.csv"
        filepath = BACKUP_DIR / filename

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            headers = list(table_data[0].keys())
            writer.writerow(headers)
            for row in table_data:
                writer.writerow([row.get(h, '') for h in headers])

        return str(filepath)

    def backup_all(self, user_id: int) -> Dict[str, str]:
        """Backup all tables to CSV files."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backups = {}

        # Export each table
        users = self.user_repo.list_all()
        items = self.item_repo.find_all()
        transactions = self.transaction_repo.find_all()

        backups['users'] = self._export_table_to_csv(users, 'users', timestamp)
        backups['items'] = self._export_table_to_csv(items, 'items', timestamp)
        backups['transactions'] = self._export_table_to_csv(transactions, 'transactions', timestamp)

        # Create manifest
        manifest_path = BACKUP_DIR / f"manifest_{timestamp}.txt"
        with open(manifest_path, 'w') as f:
            f.write(f"BACKUP MANIFEST\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 40 + "\n")
            for table, path in backups.items():
                f.write(f"{table}: {path}\n")

        self.audit_repo.log(
            user_id=user_id,
            action='backup',
            table_name='system',
            record_id=0,
            new_values=f"Full backup created at {timestamp}"
        )

        print(f"\n✅ Full backup completed at {timestamp}")
        for table, path in backups.items():
            print(f"   {table}: {os.path.basename(path) if path else 'No data'}")

        return backups

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backup files."""
        backups = []
        if not BACKUP_DIR.exists():
            return backups

        for file in BACKUP_DIR.glob('*.csv'):
            backups.append({
                'filename': file.name,
                'path': str(file),
                'size': file.stat().st_size,
                'modified': datetime.fromtimestamp(file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })

        return sorted(backups, key=lambda x: x['filename'], reverse=True)

    def restore_from_backup(self, user_id: int, table_name: str, filename: str) -> bool:
        """Restore a table from a CSV backup file."""
        filepath = BACKUP_DIR / filename
        if not filepath.exists():
            raise BackupError(f"Backup file not found: {filename}")

        # Read CSV
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            rows = list(reader)

        if not rows:
            raise BackupError(f"No data found in backup file: {filename}")

        # Determine table
        if table_name == 'items':
            # Clear existing items
            execute_write("DELETE FROM items")
            for row in rows:
                data = dict(zip(headers, row))
                execute_write('''
                    INSERT INTO items (id, name, category, quantity, price, supplier, reorder_level, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    int(data['id']) if 'id' in data else None,
                    data.get('name', ''),
                    data.get('category', ''),
                    int(data.get('quantity', 0)),
                    float(data.get('price', 0.0)),
                    data.get('supplier', ''),
                    int(data.get('reorder_level', 5)),
                    data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                    data.get('updated_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                ))

        elif table_name == 'users':
            execute_write("DELETE FROM users")
            for row in rows:
                data = dict(zip(headers, row))
                execute_write('''
                    INSERT INTO users (id, username, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    int(data['id']) if 'id' in data else None,
                    data.get('username', ''),
                    data.get('password_hash', ''),
                    data.get('role', 'staff'),
                    data.get('created_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                ))

        elif table_name == 'transactions':
            execute_write("DELETE FROM transactions")
            for row in rows:
                data = dict(zip(headers, row))
                execute_write('''
                    INSERT INTO transactions (id, item_id, user_id, action, quantity_change, previous_quantity, new_quantity, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    int(data['id']) if 'id' in data else None,
                    int(data['item_id']) if 'item_id' in data else None,
                    int(data['user_id']) if 'user_id' in data else None,
                    data.get('action', ''),
                    int(data.get('quantity_change', 0)),
                    int(data.get('previous_quantity', 0)),
                    int(data.get('new_quantity', 0)),
                    data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                ))

        else:
            raise ValidationError(f"Unknown table: {table_name}")

        self.audit_repo.log(
            user_id=user_id,
            action='restore',
            table_name=table_name,
            record_id=0,
            new_values=f"Restored from {filename}, {len(rows)} records"
        )

        print(f"✅ Restored {len(rows)} records into {table_name} from {filename}")
        return True


# =============================================================================
# CLI PRESENTATION LAYER
# =============================================================================

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header(title: str, subtitle: str = ""):
    """Print a formatted header."""
    clear_screen()
    print("=" * 60)
    print(f"  {APP_NAME}")
    print(f"  {APP_AUTHOR} - {APP_DATE}")
    if subtitle:
        print(f"  {subtitle}")
    print("=" * 60)


def print_table(items: List[Dict[str, Any]], headers: List[str], field_mapping: Dict[str, str]):
    """Print a formatted table."""
    if not items:
        print("\n📦 No items found.")
        return

    # Calculate column widths
    widths = {}
    for header in headers:
        widths[header] = len(header)

    for item in items:
        for header in headers:
            field = field_mapping.get(header, header)
            value = str(item.get(field, ''))
            widths[header] = max(widths[header], len(value))

    # Print header
    print("\n" + "=" * (sum(widths.values()) + len(headers) * 3 + 1))
    header_row = ""
    for header in headers:
        header_row += f" {header:<{widths[header]}} |"
    print(header_row)
    print("-" * (sum(widths.values()) + len(headers) * 3 + 1))

    # Print rows
    for item in items:
        row = ""
        for header in headers:
            field = field_mapping.get(header, header)
            value = str(item.get(field, ''))
            row += f" {value:<{widths[header]}} |"
        print(row)

    print("=" * (sum(widths.values()) + len(headers) * 3 + 1))
    print(f"Total: {len(items)} items")


def print_item_table(items: List[Dict[str, Any]]):
    """Print items in a formatted table."""
    if not items:
        print("\n📦 No items found.")
        return

    print("\n" + "=" * 80)
    print(f"{'ID':<5} {'Name':<20} {'Category':<12} {'Qty':<6} {'Price':<10} {'Supplier':<15} {'Reorder':<6}")
    print("=" * 80)
    for item in items:
        print(f"{item['id']:<5} {item['name']:<20} {item['category'] or '-':<12} "
              f"{item['quantity']:<6} K{item['price']:<9.2f} {item['supplier'] or '-':<15} "
              f"{item['reorder_level']:<6}")
    print("=" * 80)
    print(f"Total: {len(items)} items")
    total_value = sum(item['price'] * item['quantity'] for item in items)
    print(f"Total Inventory Value: K{total_value:.2f}")


def print_low_stock_table(items: List[Dict[str, Any]]):
    """Print low stock items in a formatted table."""
    if not items:
        print("\n✅ All items are above reorder level.")
        return

    print("\n" + "=" * 70)
    print("⚠️  LOW STOCK ALERT ⚠️")
    print("=" * 70)
    print(f"{'ID':<5} {'Name':<20} {'Qty':<6} {'Reorder':<8} {'Shortage':<8}")
    print("=" * 70)
    for item in items:
        shortage = item['reorder_level'] - item['quantity']
        print(f"{item['id']:<5} {item['name']:<20} {item['quantity']:<6} "
              f"{item['reorder_level']:<8} {shortage:<8}")
    print("=" * 70)
    print(f"⚠️  {len(items)} items need restocking.")


def print_backup_list(backups: List[Dict[str, Any]]):
    """Print available backups in a formatted table."""
    if not backups:
        print("\n📂 No backup files found.")
        return

    print("\n" + "=" * 70)
    print("📂 AVAILABLE BACKUPS")
    print("=" * 70)
    print(f"{'Filename':<40} {'Size':<12} {'Modified':<20}")
    print("=" * 70)
    for backup in backups:
        size = f"{backup['size']:,} bytes"
        print(f"{backup['filename']:<40} {size:<12} {backup['modified']:<20}")
    print("=" * 70)


def get_input(prompt: str, required: bool = True, default: Any = None) -> str:
    """Get user input with validation."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        if not required:
            return default
        print("❌ This field is required. Please try again.")


def get_int(prompt: str, required: bool = True, default: int = None) -> Optional[int]:
    """Get integer input with validation."""
    while True:
        value = input(prompt).strip()
        if not value:
            if not required:
                return default
            print("❌ This field is required. Please try again.")
            continue
        try:
            return int(value)
        except ValueError:
            print("❌ Please enter a valid number.")


def get_float(prompt: str, required: bool = True, default: float = None) -> Optional[float]:
    """Get float input with validation."""
    while True:
        value = input(prompt).strip()
        if not value:
            if not required:
                return default
            print("❌ This field is required. Please try again.")
            continue
        try:
            return float(value)
        except ValueError:
            print("❌ Please enter a valid number.")


def get_choice(prompt: str, options: List[str]) -> str:
    """Get a choice from a list of options."""
    while True:
        choice = input(prompt).strip().lower()
        if choice in options:
            return choice
        print(f"❌ Invalid choice. Please choose from: {', '.join(options)}")


# =============================================================================
# MENU FUNCTIONS
# =============================================================================

def login(auth_service: AuthService) -> Optional[Dict[str, Any]]:
    """Handle user login."""
    print_header("LOGIN")

    username = get_input("Username: ")
    password = get_input("Password: ", required=True)

    try:
        user = auth_service.authenticate(username, password)
        if user:
            print(f"\n✅ Welcome back, {user['username']} ({user['role']})!")
            return user
        else:
            print("\n❌ Invalid username or password.")
            return None
    except ValidationError as e:
        print(f"\n❌ {e}")
        return None


def add_item_menu(inventory_service: InventoryService, user: Dict[str, Any]):
    """Add a new item."""
    print_header("ADD NEW ITEM")

    try:
        data = {
            'name': get_input("Item name: "),
            'category': get_input("Category (optional): ", required=False, default=''),
            'quantity': get_int("Quantity: ", default=0),
            'price': get_float("Price: ", default=0.0),
            'supplier': get_input("Supplier (optional): ", required=False, default=''),
            'reorder_level': get_int("Reorder level (default 5): ", required=False, default=5)
        }

        item_id = inventory_service.add_item(user['id'], data)
        print(f"\n✅ Item '{data['name']}' added successfully! (ID: {item_id})")

    except (ValidationError, DuplicateItemError) as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def view_items_menu(inventory_service: InventoryService):
    """View all items."""
    print_header("VIEW ALL ITEMS")

    try:
        items = inventory_service.get_all_items()
        print_item_table(items)
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def update_item_menu(inventory_service: InventoryService, user: Dict[str, Any]):
    """Update an existing item."""
    print_header("UPDATE ITEM")

    try:
        # Show current items
        items = inventory_service.get_all_items()
        print_item_table(items)

        item_id = get_int("Enter item ID to update: ")
        current = inventory_service.get_item(item_id)

        print(f"\nCurrent details for {current['name']}:")
        print(f"  Quantity: {current['quantity']}")
        print(f"  Price: {current['price']}")
        print(f"  Supplier: {current['supplier'] or 'None'}")
        print(f"  Reorder level: {current['reorder_level']}")
        print("\nLeave blank to keep current value.\n")

        data = {}
        name = get_input(f"Name ({current['name']}): ", required=False, default=None)
        if name:
            data['name'] = name

        category = get_input(f"Category ({current['category'] or 'None'}): ", required=False, default=None)
        if category:
            data['category'] = category

        qty = get_int(f"Quantity ({current['quantity']}): ", required=False, default=None)
        if qty is not None:
            data['quantity'] = qty

        price = get_float(f"Price ({current['price']}): ", required=False, default=None)
        if price is not None:
            data['price'] = price

        supplier = get_input(f"Supplier ({current['supplier'] or 'None'}): ", required=False, default=None)
        if supplier:
            data['supplier'] = supplier

        reorder = get_int(f"Reorder level ({current['reorder_level']}): ", required=False, default=None)
        if reorder is not None:
            data['reorder_level'] = reorder

        if not data:
            print("❌ No changes made.")
        else:
            inventory_service.update_item(user['id'], item_id, data)
            print("✅ Item updated successfully!")

    except (ItemNotFoundError, ValidationError) as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def delete_item_menu(inventory_service: InventoryService, user: Dict[str, Any]):
    """Delete an item."""
    print_header("DELETE ITEM")

    try:
        items = inventory_service.get_all_items()
        print_item_table(items)

        item_id = get_int("Enter item ID to delete: ")
        item = inventory_service.get_item(item_id)

        confirm = get_input(f"Are you sure you want to delete '{item['name']}'? (y/n): ")
        if confirm.lower() != 'y':
            print("❌ Deletion cancelled.")
        else:
            inventory_service.delete_item(user['id'], item_id)
            print(f"✅ Item '{item['name']}' deleted successfully!")

    except (ItemNotFoundError, ValidationError) as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def search_items_menu(inventory_service: InventoryService):
    """Search for items."""
    print_header("SEARCH ITEMS")

    try:
        keyword = get_input("Enter search term: ")
        items = inventory_service.search_items(keyword)

        if not items:
            print(f"\n❌ No items found matching '{keyword}'.")
        else:
            print(f"\nFound {len(items)} item(s) matching '{keyword}':")
            print_item_table(items)

    except ValidationError as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def low_stock_menu(inventory_service: InventoryService):
    """View low stock items."""
    print_header("LOW STOCK ALERT")

    try:
        items = inventory_service.get_low_stock_items()
        print_low_stock_table(items)
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def adjust_stock_menu(inventory_service: InventoryService, user: Dict[str, Any]):
    """Adjust stock for an item."""
    print_header("ADJUST STOCK")

    try:
        items = inventory_service.get_all_items()
        print_item_table(items)

        item_id = get_int("Enter item ID: ")
        item = inventory_service.get_item(item_id)

        print(f"\nCurrent stock for {item['name']}: {item['quantity']}")
        action = get_choice("Add or remove? (add/remove): ", ['add', 'remove'])
        amount = get_int("Amount: ")

        new_quantity = inventory_service.adjust_stock(user['id'], item_id, amount, action)
        print(f"✅ Stock updated! {item['name']} now has {new_quantity} units.")

    except (ItemNotFoundError, ValidationError, InsufficientStockError) as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def generate_report_menu(report_service: ReportService, user: Dict[str, Any]):
    """Generate reports."""
    print_header("GENERATE REPORT")

    print("\n1. Inventory Report")
    print("2. Low Stock Report")
    print("3. Transaction Report")

    choice = get_input("\nChoose report type (1-3): ")

    try:
        if choice == '1':
            result = report_service.generate_inventory_report(user['id'])
            print(f"\n📊 Inventory report generated!")
            print(f"   File: {result['filename']}")
            print(f"   Path: {result['file_path']}")
            print(f"   Total items: {result['total_items']}")
            print(f"   Total inventory value: K{result['total_value']:.2f}")

        elif choice == '2':
            result = report_service.generate_low_stock_report(user['id'])
            if result['total_low_stock_items'] > 0:
                print(f"\n⚠️ Low stock report generated!")
                print(f"   File: {result['filename']}")
                print(f"   Path: {result['file_path']}")
                print(f"   Items needing restock: {result['total_low_stock_items']}")
            else:
                print("\n✅ All items are above reorder level. No report generated.")

        elif choice == '3':
            result = report_service.generate_transaction_report(user['id'])
            print(f"\n📋 Transaction report generated!")
            print(f"   File: {result['filename']}")
            print(f"   Path: {result['file_path']}")
            print(f"   Total transactions: {result['total_transactions']}")

        else:
            print("❌ Invalid choice.")

    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def backup_menu(backup_service: BackupService, user: Dict[str, Any]):
    """Backup and restore menu."""
    print_header("BACKUP & RESTORE")

    print("\n1. Create Full Backup")
    print("2. List Available Backups")
    print("3. Restore from Backup")

    choice = get_input("\nChoose option (1-3): ")

    try:
        if choice == '1':
            backup_service.backup_all(user['id'])

        elif choice == '2':
            backups = backup_service.list_backups()
            print_backup_list(backups)

        elif choice == '3':
            backups = backup_service.list_backups()
            print_backup_list(backups)

            table = get_input("Enter table name (items/users/transactions): ")
            if table not in ['items', 'users', 'transactions']:
                print("❌ Invalid table name.")
                return

            filename = get_input("Enter backup filename: ")
            backup_service.restore_from_backup(user['id'], table, filename)

        else:
            print("❌ Invalid choice.")

    except (BackupError, ValidationError) as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


def user_menu(auth_service: AuthService, user: Dict[str, Any]):
    """User account management."""
    print_header("ACCOUNT MANAGEMENT")

    print("\n1. Change Password")
    if user['role'] == 'admin':
        print("2. Create New User")
        print("3. List All Users")

    choice = get_input("\nChoose option (1-3): ")

    try:
        if choice == '1':
            current = get_input("Current password: ", required=True)
            new = get_input("New password (min 6 chars): ", required=True)
            confirm = get_input("Confirm new password: ", required=True)

            if new != confirm:
                print("❌ Passwords do not match.")
            else:
                auth_service.change_password(user['id'], current, new)
                print("✅ Password updated successfully!")

        elif choice == '2' and user['role'] == 'admin':
            username = get_input("New username: ")
            password = get_input("New password (min 6 chars): ", required=True)
            role = get_input("Role (admin/manager/staff): ", required=False, default='staff')

            auth_service.create_user(user['id'], username, password, role)
            print(f"✅ User '{username}' created successfully with role '{role}'.")

        elif choice == '3' and user['role'] == 'admin':
            users = auth_service.user_repo.list_all()
            print("\n" + "=" * 50)
            print(f"{'ID':<5} {'Username':<15} {'Role':<10} {'Created At':<20}")
            print("=" * 50)
            for u in users:
                print(f"{u['id']:<5} {u['username']:<15} {u['role']:<10} {u['created_at']:<20}")
            print("=" * 50)

        else:
            print("❌ Invalid choice.")

    except (AuthenticationError, ValidationError, DuplicateItemError) as e:
        print(f"\n❌ {e}")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")

    input("\nPress Enter to continue...")


# =============================================================================
# MAIN MENU
# =============================================================================

def main_menu(user: Dict[str, Any]):
    """Display the main menu and handle user choices."""
    # Initialize services
    auth_service = AuthService()
    inventory_service = InventoryService()
    report_service = ReportService()
    backup_service = BackupService()

    while True:
        clear_screen()
        print("=" * 60)
        print(f"  {APP_NAME}")
        print(f"  Logged in as: {user['username']} ({user['role']})")
        print("=" * 60)

        print("\n📦 INVENTORY")
        print("  1. Add item")
        print("  2. View all items")
        print("  3. Update item")
        print("  4. Delete item")
        print("  5. Search items")
        print("  6. View low stock alert")
        print("  7. Adjust stock (add/remove)")

        print("\n📊 REPORTS")
        print("  8. Generate report")

        print("\n💾 BACKUP & RESTORE")
        print("  9. Backup / Restore")

        print("\n👤 ACCOUNT")
        print(" 10. Account management")

        print("\n 0. Logout and exit")
        print("=" * 60)

        choice = get_input("\nEnter your choice: ")

        if choice == '0':
            print("\n👋 Goodbye!")
            sys.exit(0)

        elif choice == '1':
            add_item_menu(inventory_service, user)

        elif choice == '2':
            view_items_menu(inventory_service)

        elif choice == '3':
            update_item_menu(inventory_service, user)

        elif choice == '4':
            delete_item_menu(inventory_service, user)

        elif choice == '5':
            search_items_menu(inventory_service)

        elif choice == '6':
            low_stock_menu(inventory_service)

        elif choice == '7':
            adjust_stock_menu(inventory_service, user)

        elif choice == '8':
            generate_report_menu(report_service, user)

        elif choice == '9':
            backup_menu(backup_service, user)

        elif choice == '10':
            user_menu(auth_service, user)

        else:
            print("❌ Invalid choice. Please try again.")
            input("\nPress Enter to continue...")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    """Main entry point for the application."""
    clear_screen()
    print("=" * 60)
    print(f"  {APP_NAME}")
    print(f"  {APP_AUTHOR}")
    print(f"  Version: {APP_VERSION} - {APP_DATE}")
    print("=" * 60)

    # Initialize database
    try:
        init_database()
    except Exception as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)

    # Authentication loop
    auth_service = AuthService()
    user = None

    while not user:
        user = login(auth_service)
        if not user:
            retry = get_input("\nTry again? (y/n): ")
            if retry.lower() != 'y':
                print("\nGoodbye.")
                sys.exit(0)

    # Start the main menu
    main_menu(user)


if __name__ == '__main__':
    main()
