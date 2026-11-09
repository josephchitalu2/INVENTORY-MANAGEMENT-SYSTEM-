"""Regression tests for the CLI's security and inventory invariants.

Run with: python3 -m unittest discover -s tests -v
Uses a temporary SQLite database and never touches real shop data.
"""
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path

import ims


class InventoryGuardsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = ims.DATABASE_PATH
        ims.DATABASE_PATH = Path(self.temp.name) / "test.db"
        ims.init_database()
        self.auth = ims.AuthService()
        self.admin = self.auth.create_first_admin("tester", "test-password-123")
        self.inventory = ims.InventoryService()

    def tearDown(self):
        ims.DATABASE_PATH = self.original_db
        self.temp.cleanup()

    def item(self, **overrides):
        fields = dict(name="Fresh fish", category="Food", unit_type="kg",
                      quantity=2.5, cost_price=20.0, selling_price=30.0,
                      supplier="Test", reorder_level=1.0)
        fields.update(overrides)
        return self.inventory.add_item(self.admin, **fields)

    def test_successful_login_is_audited(self):
        self.auth.authenticate("tester", "test-password-123")
        with ims.db() as conn:
            count = conn.execute("SELECT count(*) FROM audit_log WHERE action='login'").fetchone()[0]
        self.assertEqual(count, 1)

    def test_inactive_account_cannot_write(self):
        with ims.transaction() as conn:
            conn.execute("UPDATE users SET active=0 WHERE id=?", (self.admin,))
        with self.assertRaises(ims.AuthorizationError):
            self.item()

    def test_rejects_nonfinite_prices_and_quantities(self):
        for value in (math.inf, -math.inf, math.nan):
            with self.subTest(value=value):
                with self.assertRaises(ims.ValidationError):
                    ims.validate_price(value, "Price")
                with self.assertRaises(ims.ValidationError):
                    ims.validate_quantity(value, "kg")
                with self.assertRaises(ims.ValidationError):
                    self.item(quantity=value)
                with self.assertRaises(ims.ValidationError):
                    self.item(cost_price=value)
                with self.assertRaises(ims.ValidationError):
                    self.item(reorder_level=value)

    def test_negative_and_fractional_discrete_quantities_rejected(self):
        for value in (-1, 1.5):
            with self.subTest(value=value):
                with self.assertRaises(ims.ValidationError):
                    self.item(unit_type="piece", quantity=value)

    def test_stock_rejection_does_not_change_db(self):
        iid = self.item()
        with self.assertRaises(ims.InsufficientStockError):
            self.inventory.adjust_stock(self.admin, iid, 3, "remove")
        self.assertEqual(ims.ItemRepository().find(iid)["quantity"], 2.5)

    def test_unit_cannot_be_changed_with_fractional_stock(self):
        iid = self.item()
        with self.assertRaises(ims.ValidationError):
            self.inventory.update_item(self.admin, iid, unit_type="piece")
        self.assertEqual(ims.ItemRepository().find(iid)["unit_type"], "kg")

    def test_update_cannot_clear_name(self):
        iid = self.item()
        with self.assertRaises(ims.ValidationError):
            self.inventory.update_item(self.admin, iid, name="  ")
        self.assertEqual(ims.ItemRepository().find(iid)["name"], "Fresh fish")

    def test_update_rejects_nonfinite_reorder(self):
        iid = self.item()
        with self.assertRaises(ims.ValidationError):
            self.inventory.update_item(self.admin, iid, reorder_level=math.inf)


if __name__ == "__main__":
    unittest.main()
