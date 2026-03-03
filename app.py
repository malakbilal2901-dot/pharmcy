from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "pharmacy.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"


def make_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.config["DATABASE_PATH"] = str(DB_PATH)

    @app.after_request
    def cors(resp):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return resp

    @app.route("/api/<path:_path>", methods=["OPTIONS"])
    def options_handler(_path: str):
        return ("", 204)

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            db = sqlite3.connect(app.config["DATABASE_PATH"])
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            g.db = db
        return g.db

    @app.teardown_appcontext
    def close_db(_err):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @contextmanager
    def txn():
        db = get_db()
        try:
            db.execute("BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    def jbody(required: list[str] | None = None) -> dict[str, Any]:
        data = request.get_json(silent=True) or {}
        if required:
            miss = [k for k in required if data.get(k) in (None, "")]
            if miss:
                raise ValueError(f"Missing: {', '.join(miss)}")
        return data

    def as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def as_list(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    def next_code(prefix: str, table: str) -> str:
        row = get_db().execute(f"SELECT COUNT(*) c FROM {table}").fetchone()  # noqa: S608
        n = (row["c"] if row else 0) + 1
        return f"{prefix}-{datetime.utcnow().year}-{n:05d}"

    def debt_status(due_date: str, remaining: float) -> str:
        if remaining <= 0:
            return "paid"
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if due_date < today:
            return "overdue"
        if due_date == today:
            return "due-today"
        return "pending"

    def refresh_stock(db: sqlite3.Connection, product_id: int):
        row = db.execute(
            "SELECT COALESCE(SUM(remaining_quantity),0) s FROM product_batches WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        db.execute(
            "UPDATE products SET stock = ?, updated_at = datetime('now') WHERE id = ?",
            (int(row["s"] if row else 0), product_id),
        )

    def fifo_alloc(db: sqlite3.Connection, product_id: int, qty: int) -> list[tuple[int, int, float]]:
        rows = db.execute(
            """
            SELECT id, remaining_quantity, cost_price
            FROM product_batches
            WHERE product_id = ? AND remaining_quantity > 0 AND status = 'active'
            ORDER BY date(expiry_date) ASC, id ASC
            """,
            (product_id,),
        ).fetchall()
        need = qty
        out: list[tuple[int, int, float]] = []
        for r in rows:
            if need <= 0:
                break
            take = min(need, int(r["remaining_quantity"]))
            if take > 0:
                out.append((int(r["id"]), take, float(r["cost_price"])))
                need -= take
        if need > 0:
            raise ValueError("Insufficient FIFO stock")
        return out

    def init_db(seed: bool = False):
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with txn() as db:
            db.executescript(sql)
            if not seed:
                db.execute("DELETE FROM users WHERE username IN ('admin','pharma')")

    @app.errorhandler(ValueError)
    def bad_input(err: ValueError):
        return jsonify({"ok": False, "error": str(err)}), 400

    @app.errorhandler(Exception)
    def boom(err: Exception):
        return jsonify({"ok": False, "error": str(err)}), 500

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "time": datetime.utcnow().isoformat()})

    @app.post("/api/setup/init-db")
    def setup():
        data = request.get_json(silent=True) or {}
        init_db(seed=bool(data.get("seed", False)))
        return jsonify({"ok": True})

    @app.post("/api/auth/login")
    def login():
        data = jbody(["username", "password"])
        row = get_db().execute(
            "SELECT id, username, password_hash, full_name, role, avatar, is_active FROM users WHERE username = ?",
            (data["username"],),
        ).fetchone()
        if not row or int(row["is_active"]) != 1 or row["password_hash"] != data["password"]:
            return jsonify({"ok": False, "error": "Invalid credentials"}), 401
        get_db().execute("UPDATE users SET last_login_at = datetime('now') WHERE id = ?", (row["id"],))
        get_db().commit()
        user = dict(row)
        user.pop("password_hash", None)
        return jsonify({"ok": True, "user": user})

    @app.get("/api/users")
    def users_list():
        rows = get_db().execute(
            "SELECT id, username, full_name, role, avatar, phone, email, is_active, created_at, updated_at FROM users ORDER BY id DESC"
        ).fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/users")
    def users_create():
        d = jbody(["username", "password", "full_name", "role"])
        with txn() as db:
            cur = db.execute(
                """
                INSERT INTO users (username, password_hash, full_name, role, avatar, phone, email, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d["username"],
                    d["password"],
                    d["full_name"],
                    d["role"],
                    d.get("avatar"),
                    d.get("phone"),
                    d.get("email"),
                    1 if d.get("is_active", True) else 0,
                ),
            )
            uid = cur.lastrowid
        row = get_db().execute(
            "SELECT id, username, full_name, role, avatar, phone, email, is_active, created_at, updated_at FROM users WHERE id = ?",
            (uid,),
        ).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.patch("/api/users/<int:user_id>")
    def users_update(user_id: int):
        d = jbody()
        map_cols = {
            "username": "username",
            "password": "password_hash",
            "full_name": "full_name",
            "role": "role",
            "avatar": "avatar",
            "phone": "phone",
            "email": "email",
            "is_active": "is_active",
        }
        sets, vals = [], []
        for k, c in map_cols.items():
            if k in d:
                sets.append(f"{c} = ?")
                vals.append(d[k])
        if not sets:
            raise ValueError("No fields to update")
        with txn() as db:
            res = db.execute(
                f"UPDATE users SET {', '.join(sets)}, updated_at = datetime('now') WHERE id = ?",  # noqa: S608
                (*vals, user_id),
            )
            if res.rowcount == 0:
                return jsonify({"ok": False, "error": "User not found"}), 404
        row = get_db().execute(
            "SELECT id, username, full_name, role, avatar, phone, email, is_active, created_at, updated_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)})

    @app.delete("/api/users/<int:user_id>")
    def users_delete(user_id: int):
        with txn() as db:
            res = db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            if res.rowcount == 0:
                return jsonify({"ok": False, "error": "User not found"}), 404
        return jsonify({"ok": True})

    @app.get("/api/products")
    def products_list():
        search = request.args.get("search", "").strip()
        category = request.args.get("category", "").strip()
        status = request.args.get("status", "").strip()
        sql = "SELECT * FROM products WHERE 1=1"
        params: list[Any] = []
        if search:
            like = f"%{search}%"
            sql += " AND (name LIKE ? OR barcode LIKE ?)"
            params += [like, like]
        if category:
            sql += " AND category = ?"
            params.append(category)
        if status == "low":
            sql += " AND stock <= min_stock"
        elif status == "active":
            sql += " AND is_active = 1"
        elif status == "inactive":
            sql += " AND is_active = 0"
        sql += " ORDER BY id DESC"
        rows = get_db().execute(sql, params).fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/products")
    def products_create():
        d = jbody(["name", "barcode", "category", "price", "cost"])
        with txn() as db:
            cur = db.execute(
                """
                INSERT INTO products (name, barcode, category, description, price, cost, vat_rate, stock, min_stock, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d["name"],
                    d["barcode"],
                    d["category"],
                    d.get("description"),
                    float(d["price"]),
                    float(d["cost"]),
                    float(d.get("vat_rate", 0.15)),
                    int(d.get("stock", 0)),
                    int(d.get("min_stock", 10)),
                    1 if d.get("is_active", True) else 0,
                ),
            )
            pid = cur.lastrowid
        row = get_db().execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.patch("/api/products/<int:product_id>")
    def products_update(product_id: int):
        d = jbody()
        allowed = ["name", "barcode", "category", "description", "price", "cost", "vat_rate", "min_stock", "is_active"]
        sets, vals = [], []
        for k in allowed:
            if k in d:
                sets.append(f"{k} = ?")
                vals.append(d[k])
        if not sets:
            raise ValueError("No fields to update")
        with txn() as db:
            res = db.execute(
                f"UPDATE products SET {', '.join(sets)}, updated_at = datetime('now') WHERE id = ?",  # noqa: S608
                (*vals, product_id),
            )
            if res.rowcount == 0:
                return jsonify({"ok": False, "error": "Product not found"}), 404
        row = get_db().execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)})

    @app.delete("/api/products/<int:product_id>")
    def products_delete(product_id: int):
        with txn() as db:
            res = db.execute("DELETE FROM products WHERE id = ?", (product_id,))
            if res.rowcount == 0:
                return jsonify({"ok": False, "error": "Product not found"}), 404
        return jsonify({"ok": True})

    @app.get("/api/products/<int:product_id>/batches")
    def batches_list(product_id: int):
        rows = get_db().execute(
            "SELECT * FROM product_batches WHERE product_id = ? ORDER BY date(expiry_date) ASC, id ASC",
            (product_id,),
        ).fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/products/<int:product_id>/batches")
    def batches_create(product_id: int):
        d = jbody(["batch_number", "quantity", "cost_price", "expiry_date"])
        qty = int(d["quantity"])
        with txn() as db:
            ok = db.execute("SELECT id FROM products WHERE id = ?", (product_id,)).fetchone()
            if not ok:
                return jsonify({"ok": False, "error": "Product not found"}), 404
            cur = db.execute(
                """
                INSERT INTO product_batches (product_id, batch_number, quantity, remaining_quantity, cost_price, purchase_date, expiry_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (
                    product_id,
                    d["batch_number"],
                    qty,
                    qty,
                    float(d["cost_price"]),
                    d.get("purchase_date") or datetime.utcnow().strftime("%Y-%m-%d"),
                    d["expiry_date"],
                ),
            )
            bid = cur.lastrowid
            db.execute(
                """
                INSERT INTO inventory_movements (product_id, batch_id, movement_type, quantity, unit_cost, reference_type, reference_id, notes)
                VALUES (?, ?, 'purchase_in', ?, ?, 'manual_batch', ?, ?)
                """,
                (product_id, bid, qty, float(d["cost_price"]), bid, d.get("notes")),
            )
            refresh_stock(db, product_id)
        row = get_db().execute("SELECT * FROM product_batches WHERE id = ?", (bid,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.get("/api/suppliers")
    def suppliers_list():
        rows = get_db().execute("SELECT * FROM suppliers ORDER BY id DESC").fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/suppliers")
    def suppliers_create():
        d = jbody(["name"])
        with txn() as db:
            cur = db.execute(
                "INSERT INTO suppliers (name, phone, email, address, balance, status) VALUES (?, ?, ?, ?, ?, ?)",
                (d["name"], d.get("phone"), d.get("email"), d.get("address"), float(d.get("balance", 0)), d.get("status", "active")),
            )
            sid = cur.lastrowid
        row = get_db().execute("SELECT * FROM suppliers WHERE id = ?", (sid,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.get("/api/purchase-invoices")
    def purchases_list():
        rows = get_db().execute(
            """
            SELECT pi.*, s.name supplier_name
            FROM purchase_invoices pi
            JOIN suppliers s ON s.id = pi.supplier_id
            ORDER BY pi.id DESC
            """
        ).fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/purchase-invoices")
    def purchases_create():
        d = jbody(["supplier_id", "invoice_date", "items"])
        items = d.get("items") or []
        if not items:
            raise ValueError("items required")
        subtotal = 0.0
        for it in items:
            q = int(it.get("quantity", 0))
            p = float(it.get("unit_price", 0))
            if q <= 0 or p < 0:
                raise ValueError("Invalid purchase item")
            subtotal += q * p
        discount = float(d.get("discount", 0))
        tax = float(d.get("tax", 0))
        total = subtotal - discount + tax
        paid = float(d.get("paid", 0))
        remaining = max(0.0, total - paid)
        status = "paid" if remaining == 0 else ("partial" if paid > 0 else "unpaid")

        with txn() as db:
            sup = db.execute("SELECT id FROM suppliers WHERE id = ?", (int(d["supplier_id"]),)).fetchone()
            if not sup:
                return jsonify({"ok": False, "error": "Supplier not found"}), 404
            inv_no = d.get("invoice_number") or next_code("PINV", "purchase_invoices")
            cur = db.execute(
                """
                INSERT INTO purchase_invoices
                (invoice_number, supplier_id, invoice_date, subtotal, discount, tax, total, paid, remaining, status, notes, created_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (inv_no, int(d["supplier_id"]), d["invoice_date"], subtotal, discount, tax, total, paid, remaining, status, d.get("notes"), d.get("created_by_user_id")),
            )
            inv_id = cur.lastrowid
            for it in items:
                pid = int(it.get("product_id", 0))
                qty = int(it["quantity"])
                unit = float(it["unit_price"])
                line = qty * unit
                prod = db.execute("SELECT id, name, barcode FROM products WHERE id = ?", (pid,)).fetchone()
                if not prod:
                    raise ValueError(f"Product {pid} not found")
                db.execute(
                    """
                    INSERT INTO purchase_invoice_items
                    (purchase_invoice_id, product_id, product_name_snapshot, barcode_snapshot, quantity, unit_price, line_total, batch_number, expiry_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (inv_id, pid, prod["name"], prod["barcode"], qty, unit, line, it.get("batch_number"), it.get("expiry_date") or "2099-12-31"),
                )
                bnum = it.get("batch_number") or f"PINV-{inv_id}-{pid}"
                db.execute(
                    """
                    INSERT INTO product_batches (product_id, batch_number, quantity, remaining_quantity, cost_price, purchase_date, expiry_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                    """,
                    (pid, bnum, qty, qty, unit, d["invoice_date"], it.get("expiry_date") or "2099-12-31"),
                )
                bid = db.execute("SELECT last_insert_rowid() id").fetchone()["id"]
                db.execute(
                    """
                    INSERT INTO inventory_movements (product_id, batch_id, movement_type, quantity, unit_cost, reference_type, reference_id, notes, moved_by_user_id)
                    VALUES (?, ?, 'purchase_in', ?, ?, 'purchase_invoice', ?, ?, ?)
                    """,
                    (pid, bid, qty, unit, inv_id, f"Purchase {inv_no}", d.get("created_by_user_id")),
                )
                refresh_stock(db, pid)
            db.execute("UPDATE suppliers SET balance = balance + ?, updated_at = datetime('now') WHERE id = ?", (remaining, int(d["supplier_id"])))
        row = get_db().execute("SELECT * FROM purchase_invoices WHERE id = ?", (inv_id,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.post("/api/purchase-invoices/<int:invoice_id>/payments")
    def purchases_pay(invoice_id: int):
        d = jbody(["amount", "payment_date", "method"])
        amount = float(d["amount"])
        if amount <= 0:
            raise ValueError("amount must be > 0")
        with txn() as db:
            inv = db.execute("SELECT * FROM purchase_invoices WHERE id = ?", (invoice_id,)).fetchone()
            if not inv:
                return jsonify({"ok": False, "error": "Invoice not found"}), 404
            if amount > float(inv["remaining"]):
                raise ValueError("Payment exceeds remaining")
            db.execute(
                """
                INSERT INTO purchase_payments (purchase_invoice_id, payment_date, amount, method, reference_no, note, created_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (invoice_id, d["payment_date"], amount, d["method"], d.get("reference_no"), d.get("note"), d.get("created_by_user_id")),
            )
            new_paid = float(inv["paid"]) + amount
            new_rem = max(0.0, float(inv["total"]) - new_paid)
            new_status = "paid" if new_rem == 0 else "partial"
            db.execute(
                "UPDATE purchase_invoices SET paid = ?, remaining = ?, status = ?, updated_at = datetime('now') WHERE id = ?",
                (new_paid, new_rem, new_status, invoice_id),
            )
            db.execute("UPDATE suppliers SET balance = balance - ?, updated_at = datetime('now') WHERE id = ?", (amount, int(inv["supplier_id"])))
        return jsonify({"ok": True})

    @app.get("/api/sales")
    def sales_list():
        rows = get_db().execute("SELECT * FROM sales ORDER BY id DESC").fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/sales/checkout")
    def sales_checkout():
        d = jbody(["items", "payment_method"])
        items = d.get("items") or []
        if not items:
            raise ValueError("items required")
        if d["payment_method"] not in ("cash", "card", "insurance", "debt", "mixed"):
            raise ValueError("Invalid payment_method")

        with txn() as db:
            subtotal = 0.0
            tax = 0.0
            total_cost = 0.0
            lines = []
            for it in items:
                pid = int(it.get("product_id", 0))
                qty = int(it.get("quantity", 0))
                if pid <= 0 or qty <= 0:
                    raise ValueError("Invalid item")
                p = db.execute(
                    "SELECT id, name, barcode, price, cost, vat_rate, stock FROM products WHERE id = ? AND is_active = 1",
                    (pid,),
                ).fetchone()
                if not p:
                    raise ValueError(f"Product {pid} not found")
                if int(p["stock"]) < qty:
                    raise ValueError(f"Insufficient stock for product {pid}")
                alloc = fifo_alloc(db, pid, qty)
                line_sub = float(p["price"]) * qty
                line_tax = line_sub * float(p["vat_rate"])
                subtotal += line_sub
                tax += line_tax
                total_cost += sum(aq * ac for _, aq, ac in alloc)
                lines.append((p, qty, alloc, line_sub, line_tax, line_sub + line_tax))

            total = subtotal + tax
            discount = float(d.get("discount", 0))
            final_total = max(0.0, total - discount)
            insurance_id = None
            if d["payment_method"] == "insurance":
                insurance_id = int(d.get("insurance_company_id", 0))
                ins = db.execute("SELECT discount_rate FROM insurance_companies WHERE id = ? AND status = 'active'", (insurance_id,)).fetchone()
                if not ins:
                    raise ValueError("Valid insurance_company_id required")
                final_total = max(0.0, total - (total * (float(ins["discount_rate"]) / 100.0)))

            inv_no = d.get("invoice_number") or next_code("SINV", "sales")
            cur = db.execute(
                """
                INSERT INTO sales
                (invoice_number, sale_date, pharmacist_user_id, pharmacist_name_snapshot, customer_name, customer_phone,
                 payment_method, insurance_company_id, subtotal, tax, total, discount, final_total, amount_received, change_amount, status, note)
                VALUES (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)
                """,
                (
                    inv_no,
                    d.get("pharmacist_user_id"),
                    d.get("pharmacist_name_snapshot"),
                    d.get("customer_name"),
                    d.get("customer_phone"),
                    d["payment_method"],
                    insurance_id,
                    subtotal,
                    tax,
                    total,
                    discount,
                    final_total,
                    d.get("amount_received"),
                    d.get("change_amount"),
                    d.get("note"),
                ),
            )
            sale_id = cur.lastrowid

            for p, qty, alloc, line_sub, line_tax, line_total in lines:
                db.execute(
                    """
                    INSERT INTO sale_items
                    (sale_id, product_id, batch_id, product_name_snapshot, barcode_snapshot, quantity, unit_price, unit_cost, vat_rate, line_subtotal, line_tax, line_total)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (sale_id, int(p["id"]), alloc[0][0], p["name"], p["barcode"], qty, float(p["price"]), float(p["cost"]), float(p["vat_rate"]), line_sub, line_tax, line_total),
                )
                for bid, aq, ac in alloc:
                    db.execute("UPDATE product_batches SET remaining_quantity = remaining_quantity - ? WHERE id = ?", (aq, bid))
                    db.execute(
                        """
                        INSERT INTO inventory_movements
                        (product_id, batch_id, movement_type, quantity, unit_cost, unit_price, reference_type, reference_id, notes, moved_by_user_id)
                        VALUES (?, ?, 'sale_out', ?, ?, ?, 'sale', ?, ?, ?)
                        """,
                        (int(p["id"]), bid, aq, ac, float(p["price"]), sale_id, f"Sale {inv_no}", d.get("pharmacist_user_id")),
                    )
                refresh_stock(db, int(p["id"]))

            if d["payment_method"] == "debt":
                due = d.get("due_date")
                cname = d.get("customer_name")
                if not due or not cname:
                    raise ValueError("due_date and customer_name required for debt sales")
                st = debt_status(due, final_total)
                db.execute(
                    """
                    INSERT INTO customer_debts
                    (customer_name, phone, source_sale_id, amount, paid, remaining, due_date, status, notes, created_by_user_id)
                    VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                    """,
                    (cname, d.get("customer_phone"), sale_id, final_total, final_total, due, st, d.get("debt_note"), d.get("pharmacist_user_id")),
                )

            if d["payment_method"] == "insurance":
                db.execute(
                    """
                    INSERT INTO insurance_claims
                    (sale_id, insurance_company_id, claim_number, claim_date, approved_amount, patient_share, status, notes)
                    VALUES (?, ?, ?, date('now'), ?, ?, 'submitted', ?)
                    """,
                    (sale_id, insurance_id, f"CLM-{sale_id}", max(0.0, total - final_total), final_total, d.get("insurance_note")),
                )

            db.execute(
                """
                INSERT INTO notifications (type, title, message, severity, related_table, related_id, is_read, created_at)
                VALUES ('sale', 'New sale', ?, 'info', 'sales', ?, 0, datetime('now'))
                """,
                (f"Sale {inv_no} completed. Profit estimate: {final_total - total_cost:.2f}", sale_id),
            )

        row = get_db().execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.get("/api/customer-debts")
    def debts_list():
        status = request.args.get("status")
        search = request.args.get("search", "").strip()
        sql = "SELECT * FROM customer_debts WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if search:
            like = f"%{search}%"
            sql += " AND (customer_name LIKE ? OR phone LIKE ?)"
            params += [like, like]
        sql += " ORDER BY id DESC"
        rows = get_db().execute(sql, params).fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/customer-debts")
    def debts_create():
        d = jbody(["customer_name", "amount", "due_date"])
        amount = float(d["amount"])
        if amount <= 0:
            raise ValueError("amount must be > 0")
        st = debt_status(d["due_date"], amount)
        with txn() as db:
            cur = db.execute(
                """
                INSERT INTO customer_debts
                (customer_name, phone, source_sale_id, amount, paid, remaining, due_date, status, notes, created_by_user_id)
                VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                """,
                (d["customer_name"], d.get("phone"), d.get("source_sale_id"), amount, amount, d["due_date"], st, d.get("notes"), d.get("created_by_user_id")),
            )
            did = cur.lastrowid
        row = get_db().execute("SELECT * FROM customer_debts WHERE id = ?", (did,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.post("/api/customer-debts/<int:debt_id>/payments")
    def debts_pay(debt_id: int):
        d = jbody(["amount", "payment_date", "method"])
        amount = float(d["amount"])
        if amount <= 0:
            raise ValueError("amount must be > 0")
        with txn() as db:
            debt = db.execute("SELECT * FROM customer_debts WHERE id = ?", (debt_id,)).fetchone()
            if not debt:
                return jsonify({"ok": False, "error": "Debt not found"}), 404
            if amount > float(debt["remaining"]):
                raise ValueError("Payment exceeds remaining")
            db.execute(
                """
                INSERT INTO debt_payments (debt_id, payment_date, amount, method, reference_no, note, collected_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (debt_id, d["payment_date"], amount, d["method"], d.get("reference_no"), d.get("note"), d.get("collected_by_user_id")),
            )
            new_paid = float(debt["paid"]) + amount
            new_rem = max(0.0, float(debt["amount"]) - new_paid)
            st = debt_status(str(debt["due_date"]), new_rem)
            db.execute(
                """
                UPDATE customer_debts
                SET paid = ?, remaining = ?, status = ?, closed_at = CASE WHEN ? = 'paid' THEN datetime('now') ELSE closed_at END
                WHERE id = ?
                """,
                (new_paid, new_rem, st, st, debt_id),
            )
        row = get_db().execute("SELECT * FROM customer_debts WHERE id = ?", (debt_id,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)})

    @app.get("/api/insurance-companies")
    def ins_list():
        rows = get_db().execute("SELECT * FROM insurance_companies ORDER BY id DESC").fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/insurance-companies")
    def ins_create():
        d = jbody(["name"])
        with txn() as db:
            cur = db.execute(
                "INSERT INTO insurance_companies (name, phone, email, contract_number, discount_rate, status) VALUES (?, ?, ?, ?, ?, ?)",
                (d["name"], d.get("phone"), d.get("email"), d.get("contract_number"), float(d.get("discount_rate", 0)), d.get("status", "active")),
            )
            cid = cur.lastrowid
        row = get_db().execute("SELECT * FROM insurance_companies WHERE id = ?", (cid,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.get("/api/damaged-items")
    def damaged_list():
        rows = get_db().execute(
            """
            SELECT di.*, p.name product_name
            FROM damaged_items di
            JOIN products p ON p.id = di.product_id
            ORDER BY di.id DESC
            """
        ).fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.post("/api/damaged-items")
    def damaged_create():
        d = jbody(["product_id", "quantity", "reason"])
        pid = int(d["product_id"])
        qty = int(d["quantity"])
        if qty <= 0:
            raise ValueError("quantity must be > 0")
        with txn() as db:
            p = db.execute("SELECT id, cost, stock FROM products WHERE id = ?", (pid,)).fetchone()
            if not p:
                return jsonify({"ok": False, "error": "Product not found"}), 404
            if qty > int(p["stock"]):
                raise ValueError("Damaged quantity exceeds stock")
            alloc = fifo_alloc(db, pid, qty)
            for bid, aq, _ in alloc:
                db.execute("UPDATE product_batches SET remaining_quantity = remaining_quantity - ? WHERE id = ?", (aq, bid))
            unit_cost = float(p["cost"])
            cur = db.execute(
                """
                INSERT INTO damaged_items (product_id, batch_id, quantity, reason, unit_cost, total_value, note, reported_by_user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (pid, alloc[0][0], qty, d["reason"], unit_cost, unit_cost * qty, d.get("note"), d.get("reported_by_user_id")),
            )
            did = cur.lastrowid
            db.execute(
                """
                INSERT INTO inventory_movements
                (product_id, batch_id, movement_type, quantity, unit_cost, reference_type, reference_id, notes, moved_by_user_id)
                VALUES (?, ?, 'damaged_out', ?, ?, 'damaged_items', ?, ?, ?)
                """,
                (pid, alloc[0][0], qty, unit_cost, did, d.get("note"), d.get("reported_by_user_id")),
            )
            refresh_stock(db, pid)
        row = get_db().execute("SELECT * FROM damaged_items WHERE id = ?", (did,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)}), 201

    @app.get("/api/notifications")
    def notif_list():
        rows = get_db().execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 100").fetchall()
        return jsonify({"ok": True, "items": as_list(rows)})

    @app.patch("/api/notifications/<int:nid>")
    def notif_mark(nid: int):
        d = jbody()
        with txn() as db:
            res = db.execute("UPDATE notifications SET is_read = ? WHERE id = ?", (1 if d.get("is_read", True) else 0, nid))
            if res.rowcount == 0:
                return jsonify({"ok": False, "error": "Notification not found"}), 404
        row = get_db().execute("SELECT * FROM notifications WHERE id = ?", (nid,)).fetchone()
        return jsonify({"ok": True, "item": as_dict(row)})

    @app.get("/api/dashboard/summary")
    def dashboard():
        db = get_db()
        sales_today = db.execute("SELECT COALESCE(SUM(final_total),0) v FROM sales WHERE date(sale_date)=date('now') AND status='completed'").fetchone()["v"]
        sales_month = db.execute(
            "SELECT COALESCE(SUM(final_total),0) v FROM sales WHERE strftime('%Y-%m', sale_date)=strftime('%Y-%m','now') AND status='completed'"
        ).fetchone()["v"]
        customer_due = db.execute("SELECT COALESCE(SUM(remaining),0) v FROM customer_debts WHERE status IN ('pending','due-today','overdue')").fetchone()["v"]
        supplier_due = db.execute("SELECT COALESCE(SUM(remaining),0) v FROM purchase_invoices WHERE status IN ('partial','unpaid')").fetchone()["v"]
        low_stock = db.execute("SELECT COUNT(*) c FROM products WHERE is_active=1 AND stock<=min_stock").fetchone()["c"]
        expiring = db.execute(
            """
            SELECT COUNT(*) c
            FROM product_batches
            WHERE remaining_quantity > 0
              AND date(expiry_date) >= date('now')
              AND date(expiry_date) <= date('now', '+30 day')
            """
        ).fetchone()["c"]
        return jsonify(
            {
                "ok": True,
                "data": {
                    "sales_today": sales_today,
                    "sales_month": sales_month,
                    "customer_debts_due": customer_due,
                    "supplier_dues": supplier_due,
                    "low_stock_count": low_stock,
                    "expiring_batches_count": expiring,
                },
            }
        )

    return app


app = make_app()


if __name__ == "__main__":
    app.run(
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
    )
