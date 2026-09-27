from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from pathlib import Path

app = Flask(__name__)
DB = Path(__file__).with_name("chai_shop.db")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        points INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        price REAL NOT NULL,
        available INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        product_id INTEGER,
        quantity INTEGER NOT NULL,
        total REAL NOT NULL,
        status TEXT DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER,
        rating INTEGER,
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    );
    """)
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO products(name, category, price) VALUES (?, ?, ?)",
            [
                ("Masala Chai", "Tea", 30),
                ("Ginger Chai", "Tea", 35),
                ("Elaichi Chai", "Tea", 40),
                ("Samosa", "Snack", 25),
                ("Bun Butter", "Snack", 35),
            ],
        )
    conn.commit()
    conn.close()

@app.route("/")
def dashboard():
    conn = get_db()
    stats = {
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "sales": conn.execute("SELECT COALESCE(SUM(total),0) FROM orders").fetchone()[0],
        "feedback": conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0],
    }
    recent = conn.execute("""
        SELECT orders.id, customers.name AS customer, products.name AS product,
               orders.quantity, orders.total, orders.status, orders.created_at
        FROM orders
        LEFT JOIN customers ON customers.id = orders.customer_id
        LEFT JOIN products ON products.id = orders.product_id
        ORDER BY orders.id DESC LIMIT 8
    """).fetchall()
    conn.close()
    return render_template("dashboard.html", stats=stats, recent=recent)

@app.route("/customers")
def customers():
    conn = get_db()
    rows = conn.execute("SELECT * FROM customers ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("customers.html", customers=rows)

@app.route("/customers/add", methods=["POST"])
def add_customer():
    name = request.form["name"].strip()
    phone = request.form["phone"].strip()
    email = request.form["email"].strip()
    if name:
        conn = get_db()
        conn.execute("INSERT INTO customers(name, phone, email) VALUES (?, ?, ?)",
                     (name, phone, email))
        conn.commit()
        conn.close()
    return redirect(url_for("customers"))

@app.route("/products")
def products():
    conn = get_db()
    rows = conn.execute("SELECT * FROM products ORDER BY category, name").fetchall()
    conn.close()
    return render_template("products.html", products=rows)

@app.route("/orders")
def orders():
    conn = get_db()
    orders = conn.execute("""
        SELECT orders.*, customers.name AS customer, products.name AS product
        FROM orders
        LEFT JOIN customers ON customers.id = orders.customer_id
        LEFT JOIN products ON products.id = orders.product_id
        ORDER BY orders.id DESC
    """).fetchall()
    customers = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
    products = conn.execute("SELECT * FROM products WHERE available=1 ORDER BY name").fetchall()
    conn.close()
    return render_template("orders.html", orders=orders, customers=customers, products=products)

@app.route("/orders/add", methods=["POST"])
def add_order():
    customer_id = request.form.get("customer_id")
    product_id = request.form["product_id"]
    quantity = max(1, int(request.form["quantity"]))
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if product:
        total = product["price"] * quantity
        conn.execute("""INSERT INTO orders(customer_id, product_id, quantity, total)
                        VALUES (?, ?, ?, ?)""",
                     (customer_id or None, product_id, quantity, total))
        if customer_id:
            conn.execute("UPDATE customers SET points = points + ? WHERE id=?",
                         (int(total // 10), customer_id))
        conn.commit()
    conn.close()
    return redirect(url_for("orders"))

@app.route("/feedback")
def feedback():
    conn = get_db()
    rows = conn.execute("""
        SELECT feedback.*, customers.name AS customer
        FROM feedback LEFT JOIN customers ON customers.id=feedback.customer_id
        ORDER BY feedback.id DESC
    """).fetchall()
    customers = conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
    conn.close()
    return render_template("feedback.html", feedback=rows, customers=customers)

@app.route("/feedback/add", methods=["POST"])
def add_feedback():
    conn = get_db()
    conn.execute("""INSERT INTO feedback(customer_id, rating, message)
                    VALUES (?, ?, ?)""",
                 (request.form.get("customer_id") or None,
                  int(request.form["rating"]),
                  request.form["message"].strip()))
    conn.commit()
    conn.close()
    return redirect(url_for("feedback"))

@app.route("/reports")
def reports():
    conn = get_db()
    popular = conn.execute("""
        SELECT products.name, SUM(orders.quantity) quantity, SUM(orders.total) sales
        FROM orders JOIN products ON products.id=orders.product_id
        GROUP BY products.id ORDER BY quantity DESC
    """).fetchall()
    top_customers = conn.execute("""
        SELECT customers.name, COUNT(orders.id) orders, COALESCE(SUM(orders.total),0) spent
        FROM customers LEFT JOIN orders ON orders.customer_id=customers.id
        GROUP BY customers.id ORDER BY spent DESC LIMIT 10
    """).fetchall()
    conn.close()
    return render_template("reports.html", popular=popular, top_customers=top_customers)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
