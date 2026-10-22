#!/usr/bin/env python3
"""Roberts Fish & Veggies - Inventory Management System v5.0

A deliberately small, real SQLite-backed inventory system.  The CLI is only a
presentation layer; business rules live in services and database writes that
belong together are committed atomically.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Any, Iterator

APP_NAME = "Roberts Fish & Veggies IMS"
APP_VERSION = "5.0"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = DATA_DIR / "backups"
REPORT_DIR = DATA_DIR / "reports"
DATABASE_PATH = DATA_DIR / "inventory.db"
PASSWORD_MIN_LENGTH = 8
ALLOWED_UNITS = {"kg", "pack", "bottle", "piece"}
DISCRETE_UNITS = {"pack", "bottle", "piece"}
ROLES = {"admin", "manager", "staff"}

for directory in (DATA_DIR, BACKUP_DIR, REPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)


class IMSException(Exception): pass
class ValidationError(IMSException): pass
class AuthenticationError(IMSException): pass
class AuthorizationError(IMSException): pass
class ItemNotFoundError(IMSException): pass
class UserNotFoundError(IMSException): pass
class DuplicateItemError(IMSException): pass
class DuplicateUserError(IMSException): pass
class InsufficientStockError(IMSException): pass
class DatabaseError(IMSException): pass


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def money(value: float) -> str:
    return f"K{float(value):,.2f}"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"pbkdf2_sha256$210000${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def validate_quantity(amount: float, unit: str) -> float:
    try:
        value = float(amount)
    except (TypeError, ValueError):
        raise ValidationError("Quantity must be a number")
    if value <= 0:
        raise ValidationError("Quantity must be greater than zero")
    if unit not in ALLOWED_UNITS:
        raise ValidationError(f"Invalid unit '{unit}'. Allowed: {', '.join(sorted(ALLOWED_UNITS))}")
    if unit in DISCRETE_UNITS and not value.is_integer():
        raise ValidationError(f"{unit} quantities must be whole numbers")
    return value


def validate_price(value: float, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number")
    if result < 0:
        raise ValidationError(f"{field} cannot be negative")
    return result


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = None
    try:
        conn = sqlite3.connect(str(DATABASE_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        yield conn
    except sqlite3.Error as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        if conn is not None:
            conn.close()


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    with db() as conn:
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_database() -> None:
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','manager','staff')),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            category TEXT,
            unit_type TEXT NOT NULL CHECK(unit_type IN ('kg','pack','bottle','piece')),
            quantity REAL NOT NULL DEFAULT 0 CHECK(quantity >= 0),
            cost_price REAL NOT NULL DEFAULT 0 CHECK(cost_price >= 0),
            selling_price REAL NOT NULL DEFAULT 0 CHECK(selling_price >= 0),
            supplier TEXT,
            reorder_level REAL NOT NULL DEFAULT 5 CHECK(reorder_level >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('initial_stock','stock_in','stock_out','adjustment')),
            quantity_change REAL NOT NULL,
            previous_quantity REAL NOT NULL,
            new_quantity REAL NOT NULL,
            unit_type TEXT NOT NULL,
            unit_price REAL NOT NULL DEFAULT 0,
            total_value REAL NOT NULL DEFAULT 0,
            note TEXT,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(item_id) REFERENCES items(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            table_name TEXT,
            record_id INTEGER,
            old_values TEXT,
            new_values TEXT,
            timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_movements_item ON stock_movements(item_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(timestamp);
        """)


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


class UserRepository:
    def find_by_username(self, username: str) -> dict[str, Any] | None:
        with db() as conn:
            return row_dict(conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone())

    def find(self, user_id: int) -> dict[str, Any] | None:
        with db() as conn:
            return row_dict(conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def count(self) -> int:
        with db() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def all(self) -> list[dict[str, Any]]:
        with db() as conn:
            return [dict(r) for r in conn.execute("SELECT id,username,role,active,created_at FROM users ORDER BY username")]


class ItemRepository:
    def all(self) -> list[dict[str, Any]]:
        with db() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM items ORDER BY name")]

    def find(self, item_id: int) -> dict[str, Any] | None:
        with db() as conn:
            return row_dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())

    def search(self, keyword: str) -> list[dict[str, Any]]:
        with db() as conn:
            q = f"%{keyword.strip().lower()}%"
            return [dict(r) for r in conn.execute("SELECT * FROM items WHERE lower(name) LIKE ? OR lower(category) LIKE ? ORDER BY name", (q, q))]

    def low_stock(self) -> list[dict[str, Any]]:
        with db() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM items WHERE quantity <= reorder_level ORDER BY quantity")]


class AuthService:
    def __init__(self) -> None:
        self.users = UserRepository()

    def create_first_admin(self, username: str, password: str) -> int:
        if self.users.count() != 0:
            raise ValidationError("First-run setup is no longer available")
        self._validate_credentials(username, password)
        with transaction() as conn:
            cur = conn.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)", (username.strip(), hash_password(password), "admin"))
            user_id = int(cur.lastrowid)
            conn.execute("INSERT INTO audit_log(user_id,action,table_name,record_id,new_values) VALUES(?,?,?,?,?)", (user_id,"create_first_admin","users",user_id,json.dumps({"username":username,"role":"admin"})))
            return user_id

    def create_user(self, actor_id: int, username: str, password: str, role: str) -> int:
        self.require_role(actor_id, {"admin"})
        self._validate_credentials(username, password)
        if role not in ROLES:
            raise ValidationError("Role must be admin, manager, or staff")
        if self.users.find_by_username(username):
            raise DuplicateUserError(f"Username '{username}' already exists")
        with transaction() as conn:
            cur = conn.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)", (username.strip(), hash_password(password), role))
            uid = int(cur.lastrowid)
            conn.execute("INSERT INTO audit_log(user_id,action,table_name,record_id,new_values) VALUES(?,?,?,?,?)", (actor_id,"create_user","users",uid,json.dumps({"username":username,"role":role})))
            return uid

    def authenticate(self, username: str, password: str) -> dict[str, Any]:
        user = self.users.find_by_username(username)
        if not user or not user["active"] or not verify_password(password, user["password_hash"]):
            raise AuthenticationError("Invalid username or password")
        with db() as conn:
            conn.execute("INSERT INTO audit_log(user_id,action,table_name,record_id,new_values) VALUES(?,?,?,?,?)", (user["id"],"login","users",user["id"],json.dumps({"success":True})))
        user.pop("password_hash", None)
        return user

    def change_password(self, user_id: int, current: str, new: str) -> None:
        user = self.users.find(user_id)
        if not user or not verify_password(current, user["password_hash"]):
            raise AuthenticationError("Current password is incorrect")
        self._validate_password(new)
        with transaction() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new), user_id))
            conn.execute("INSERT INTO audit_log(user_id,action,table_name,record_id,new_values) VALUES(?,?,?,?,?)", (user_id,"change_password","users",user_id,"Password changed"))

    def require_role(self, user_id: int, allowed: set[str]) -> dict[str, Any]:
        user = self.users.find(user_id)
        if not user:
            raise UserNotFoundError("User not found")
        if user["role"] not in allowed:
            raise AuthorizationError("You are not authorized to perform this operation")
        return user

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < PASSWORD_MIN_LENGTH:
            raise ValidationError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
        if not password.strip():
            raise ValidationError("Password cannot be blank")

    @classmethod
    def _validate_credentials(cls, username: str, password: str) -> None:
        username = username.strip()
        if not username or len(username) > 50 or any(c.isspace() for c in username):
            raise ValidationError("Username must be 1-50 characters and contain no spaces")
        cls._validate_password(password)


class InventoryService:
    def __init__(self) -> None:
        self.auth = AuthService()
        self.items = ItemRepository()

    def add_item(self, user_id: int, *, name: str, category: str, unit_type: str, quantity: float, cost_price: float, selling_price: float, supplier: str, reorder_level: float) -> int:
        self.auth.require_role(user_id, {"admin", "manager"})
        name = name.strip()
        if not name:
            raise ValidationError("Item name is required")
        quantity = float(quantity)
        if quantity < 0:
            raise ValidationError("Quantity cannot be negative")
        if unit_type not in ALLOWED_UNITS:
            raise ValidationError("Invalid unit")
        if unit_type in DISCRETE_UNITS and not quantity.is_integer():
            raise ValidationError(f"{unit_type} quantities must be whole numbers")
        cost_price = validate_price(cost_price, "Cost price")
        selling_price = validate_price(selling_price, "Selling price")
        reorder_level = float(reorder_level)
        if reorder_level < 0:
            raise ValidationError("Reorder level cannot be negative")
        if unit_type in DISCRETE_UNITS and not reorder_level.is_integer():
            raise ValidationError(f"{unit_type} reorder levels must be whole numbers")
        with transaction() as conn:
            try:
                cur = conn.execute("INSERT INTO items(name,category,unit_type,quantity,cost_price,selling_price,supplier,reorder_level) VALUES(?,?,?,?,?,?,?,?)", (name,category.strip(),unit_type,quantity,cost_price,selling_price,supplier.strip(),reorder_level))
            except sqlite3.IntegrityError as exc:
                raise DuplicateItemError(f"Item '{name}' already exists") from exc
            item_id = int(cur.lastrowid)
            if quantity > 0:
                conn.execute("INSERT INTO stock_movements(item_id,user_id,action,quantity_change,previous_quantity,new_quantity,unit_type,unit_price,total_value,note) VALUES(?,?,?,?,?,?,?,?,?,?)", (item_id,user_id,"initial_stock",quantity,0,quantity,unit_type,cost_price,quantity*cost_price,"Initial stock"))
            conn.execute("INSERT INTO audit_log(user_id,action,table_name,record_id,new_values) VALUES(?,?,?,?,?)", (user_id,"add_item","items",item_id,json.dumps({"name":name,"quantity":quantity,"unit":unit_type})))
            return item_id

    def adjust_stock(self, user_id: int, item_id: int, amount: float, action: str, note: str = "") -> float:
        self.auth.require_role(user_id, {"admin", "manager", "staff"})
        if action not in {"add", "remove"}:
            raise ValidationError("Action must be add or remove")
        with transaction() as conn:
            item = row_dict(conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone())
            if not item:
                raise ItemNotFoundError(f"Item {item_id} not found")
            amount = validate_quantity(amount, item["unit_type"])
            old = float(item["quantity"])
            new = old + amount if action == "add" else old - amount
            if new < 0:
                raise InsufficientStockError(f"Not enough {item['unit_type']} stock. Current: {old:g}, requested: {amount:g}")
            signed = amount if action == "add" else -amount
            movement = "stock_in" if action == "add" else "stock_out"
            conn.execute("UPDATE items SET quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new,item_id))
            conn.execute("INSERT INTO stock_movements(item_id,user_id,action,quantity_change,previous_quantity,new_quantity,unit_type,unit_price,total_value,note) VALUES(?,?,?,?,?,?,?,?,?,?)", (item_id,user_id,movement,signed,old,new,item["unit_type"],item["cost_price"],abs(signed)*item["cost_price"],note.strip()))
            conn.execute("INSERT INTO audit_log(user_id,action,table_name,record_id,old_values,new_values) VALUES(?,?,?,?,?,?)", (user_id,f"stock_{action}","items",item_id,json.dumps({"quantity":old}),json.dumps({"quantity":new,"unit":item["unit_type"]})))
            return new

    def update_item(self, user_id: int, item_id: int, **changes: Any) -> None:
        self.auth.require_role(user_id, {"admin", "manager"})
        allowed = {"name","category","unit_type","cost_price","selling_price","supplier","reorder_level"}
        changes = {k:v for k,v in changes.items() if k in allowed and v is not None}
        if not changes:
            raise ValidationError("No editable fields supplied")
        current = self.items.find(item_id)
        if not current:
            raise ItemNotFoundError(f"Item {item_id} not found")
        unit = changes.get("unit_type", current["unit_type"])
        if unit not in ALLOWED_UNITS:
            raise ValidationError("Invalid unit")
        if "cost_price" in changes: changes["cost_price"] = validate_price(changes["cost_price"], "Cost price")
        if "selling_price" in changes: changes["selling_price"] = validate_price(changes["selling_price"], "Selling price")
        if "reorder_level" in changes:
            changes["reorder_level"] = float(changes["reorder_level"])
            if changes["reorder_level"] < 0: raise ValidationError("Reorder level cannot be negative")
            if unit in DISCRETE_UNITS and not changes["reorder_level"].is_integer(): raise ValidationError(f"{unit} reorder level must be whole")
        if "name" in changes: changes["name"] = str(changes["name"]).strip()
        fields = ", ".join(f"{k}=?" for k in changes)
        with transaction() as conn:
            try:
                conn.execute(f"UPDATE items SET {fields}, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*changes.values(),item_id))
            except sqlite3.IntegrityError as exc:
                raise DuplicateItemError("Another item already has that name") from exc
            conn.execute("INSERT INTO audit_log(user_id,action,table_name,record_id,old_values,new_values) VALUES(?,?,?,?,?,?)", (user_id,"update_item","items",item_id,json.dumps(current,default=str),json.dumps(changes,default=str)))

    def delete_item(self, user_id: int, item_id: int) -> None:
        self.auth.require_role(user_id, {"admin"})
        current = self.items.find(item_id)
        if not current: raise ItemNotFoundError(f"Item {item_id} not found")
        with transaction() as conn:
            # Preserve the movement/audit history: do not physically delete an item with history.
            count = conn.execute("SELECT COUNT(*) FROM stock_movements WHERE item_id=?", (item_id,)).fetchone()[0]
            if count:
                raise ValidationError("This item has transaction history. Archive/delete functionality should be added later; physical deletion is blocked.")
            conn.execute("DELETE FROM items WHERE id=?", (item_id,))
            conn.execute("INSERT INTO audit_log(user_id,action,table_name,record_id,old_values) VALUES(?,?,?,?,?)", (user_id,"delete_item","items",item_id,json.dumps(current,default=str)))


class ReportService:
    def inventory(self) -> list[dict[str, Any]]:
        return ItemRepository().all()

    def movements(self) -> list[dict[str, Any]]:
        with db() as conn:
            return [dict(r) for r in conn.execute("SELECT m.*, i.name item_name, u.username FROM stock_movements m JOIN items i ON i.id=m.item_id JOIN users u ON u.id=m.user_id ORDER BY m.timestamp DESC, m.id DESC")]

    def audit(self) -> list[dict[str, Any]]:
        with db() as conn:
            return [dict(r) for r in conn.execute("SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.timestamp DESC, a.id DESC")]

    def write_csv(self, rows: list[dict[str, Any]], prefix: str) -> Path:
        path = REPORT_DIR / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        if not rows:
            path.write_text("No records\n", encoding="utf-8")
            return path
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader(); writer.writerows(rows)
        return path


def seed_demo(user_id: int) -> int:
    service = InventoryService()
    products = [
        ("Fresh Fish", "Fresh", "kg", 43.70, 48, 65, "Roberts Supplier", 10),
        ("Chicken Pieces", "Fresh Meat", "kg", 28.50, 55, 72, "Roberts Supplier", 8),
        ("Sausage", "Fresh Meat", "kg", 18.25, 60, 82, "Roberts Supplier", 5),
        ("Smoked Fish", "Fish", "kg", 16.80, 75, 105, "Roberts Supplier", 5),
        ("Game Meat - Impala", "Game Meat", "kg", 12.00, 90, 125, "Roberts Supplier", 4),
        ("Game Meat - Buffalo", "Game Meat", "kg", 9.50, 85, 120, "Roberts Supplier", 3),
        ("Dlite Cooking Oil", "Groceries", "bottle", 24, 30, 38, "Roberts Supplier", 6),
        ("Cornflakes", "Groceries", "pack", 18, 42, 52, "Roberts Supplier", 5),
    ]
    created = 0
    for p in products:
        try:
            service.add_item(user_id, name=p[0], category=p[1], unit_type=p[2], quantity=p[3], cost_price=p[4], selling_price=p[5], supplier=p[6], reorder_level=p[7])
            created += 1
        except DuplicateItemError:
            pass
    return created


def input_float(prompt: str) -> float:
    try: return float(input(prompt).strip())
    except ValueError: raise ValidationError("Please enter a valid number")


def pause() -> None:
    input("\nPress Enter to continue...")


def first_run(auth: AuthService) -> None:
    print("\n=== FIRST-RUN SETUP ===")
    print("Create the first administrator account. No default password is shipped.\n")
    while True:
        username = input("Administrator username: ").strip()
        password = getpass("Password: ")
        confirm = getpass("Confirm password: ")
        try:
            if password != confirm: raise ValidationError("Passwords do not match")
            uid = auth.create_first_admin(username, password)
            print(f"Administrator '{username}' created.")
            return
        except IMSException as exc:
            print(f"ERROR: {exc}")


def print_items(items: list[dict[str, Any]]) -> None:
    if not items:
        print("\nNo inventory records."); return
    print("\nID  Name                         Unit     Qty       Cost        Sell       Value")
    print("-"*86)
    for x in items:
        print(f"{x['id']:<3} {x['name'][:28]:<28} {x['unit_type']:<8} {x['quantity']:>8.2f}  {money(x['cost_price']):>10}  {money(x['selling_price']):>10}  {money(x['quantity']*x['cost_price']):>11}")
    print("-"*86)
    print(f"Inventory cost value: {money(sum(x['quantity']*x['cost_price'] for x in items))}")


def menu(user: dict[str, Any]) -> None:
    auth = AuthService(); inv = InventoryService(); reports = ReportService()
    while True:
        print("\n" + "="*70)
        print(f"{APP_NAME} v{APP_VERSION} | {user['username']} ({user['role']})")
        print("="*70)
        print("1. View inventory\n2. Search inventory\n3. Add item\n4. Stock in\n5. Stock out\n6. Update item\n7. Low stock\n8. Inventory report")
        print("9. Movement report\n10. Change password\n11. Create user\n12. List users\n13. Seed demo inventory\n0. Logout")
        choice = input("\nSelect: ").strip()
        try:
            if choice == "0": return
            if choice == "1": print_items(inv.items.all()); pause()
            elif choice == "2": print_items(inv.items.search(input("Search: "))); pause()
            elif choice == "3":
                name=input("Name: "); category=input("Category: "); unit=input("Unit (kg/pack/bottle/piece): ").strip().lower(); qty=input_float("Opening quantity: "); cost=input_float("Cost per unit: "); sell=input_float("Selling price per unit: "); supplier=input("Supplier: "); reorder=input_float("Reorder level: ")
                iid=inv.add_item(user["id"],name=name,category=category,unit_type=unit,quantity=qty,cost_price=cost,selling_price=sell,supplier=supplier,reorder_level=reorder); print(f"Created item #{iid}"); pause()
            elif choice in {"4","5"}:
                print_items(inv.items.all()); iid=int(input("Item ID: ")); amount=input_float("Quantity: "); note=input("Note (optional): "); new=inv.adjust_stock(user["id"],iid,amount,"add" if choice=="4" else "remove",note); print(f"New quantity: {new:g}"); pause()
            elif choice == "6":
                iid=int(input("Item ID: ")); print("Leave blank to keep current value.")
                data={};
                for key,prompt in [("name","Name"),("category","Category"),("unit_type","Unit"),("cost_price","Cost price"),("selling_price","Selling price"),("supplier","Supplier"),("reorder_level","Reorder level")]:
                    val=input(f"{prompt}: ").strip()
                    if val:
                        data[key]=float(val) if key in {"cost_price","selling_price","reorder_level"} else val
                inv.update_item(user["id"],iid,**data); print("Updated."); pause()
            elif choice == "7": print_items(inv.items.low_stock()); pause()
            elif choice == "8":
                p=reports.write_csv(reports.inventory(),"inventory_report"); print(f"Report: {p}"); pause()
            elif choice == "9":
                p=reports.write_csv(reports.movements(),"movement_report"); print(f"Report: {p}"); pause()
            elif choice == "10":
                auth.change_password(user["id"],getpass("Current password: "),getpass("New password: ")); print("Password changed."); pause()
            elif choice == "11":
                uid=auth.create_user(user["id"],input("Username: ").strip(),getpass("Password: "),input("Role (admin/manager/staff): ").strip().lower()); print(f"Created user #{uid}"); pause()
            elif choice == "12":
                auth.require_role(user["id"],{"admin"});
                for u in auth.users.all(): print(f"#{u['id']} {u['username']} | {u['role']} | {'active' if u['active'] else 'disabled'}")
                pause()
            elif choice == "13":
                auth.require_role(user["id"],{"admin"}); print(f"Seeded {seed_demo(user['id'])} demo items."); pause()
            else: print("Unknown option")
        except (ValueError, IMSException) as exc:
            print(f"\nERROR: {exc}"); pause()


def run_cli() -> None:
    init_database(); auth=AuthService()
    if auth.users.count() == 0: first_run(auth)
    while True:
        print(f"\n{APP_NAME} v{APP_VERSION}")
        username=input("Username (or q to quit): ").strip()
        if username.lower()=="q": return
        try:
            user=auth.authenticate(username,getpass("Password: "))
            menu(user)
        except IMSException as exc:
            print(f"ERROR: {exc}")


def main() -> None:
    parser=argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--seed-demo", action="store_true")
    parser.add_argument("--db", help="Override database path")
    args=parser.parse_args()
    global DATABASE_PATH, DATA_DIR, BACKUP_DIR, REPORT_DIR
    if args.db:
        DATABASE_PATH=Path(args.db).expanduser().resolve()
        DATA_DIR=DATABASE_PATH.parent; BACKUP_DIR=DATA_DIR/"backups"; REPORT_DIR=DATA_DIR/"reports"
        for d in (DATA_DIR,BACKUP_DIR,REPORT_DIR): d.mkdir(parents=True,exist_ok=True)
    init_database()
    if args.init_db: print(f"Database ready: {DATABASE_PATH}"); return
    if args.seed_demo:
        auth=AuthService()
        if auth.users.count()==0: raise SystemExit("Create an administrator first, then run --seed-demo.")
        uid=auth.users.all()[0]["id"]
        print(f"Seeded {seed_demo(uid)} demo items."); return
    run_cli()


if __name__ == "__main__":
    try: main()
    except KeyboardInterrupt: print("\nExiting.")
