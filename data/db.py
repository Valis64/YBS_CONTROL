import sqlite3
import threading
from datetime import datetime, timedelta

from manage_html_report import compute_lead_times


def connect_db(path):
    """Connect to SQLite database and ensure required tables exist."""
    db_lock = threading.Lock()
    db = sqlite3.connect(path, check_same_thread=False)
    cur = db.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS orders (order_number TEXT PRIMARY KEY, company TEXT)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS steps (order_number TEXT, step TEXT, timestamp TEXT)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS lead_times (order_number TEXT, workstation TEXT, start TEXT, end TEXT, hours REAL)"
    )
    db.commit()
    return db, db_lock


def record_print_file_start(db, db_lock, order_number):
    with db_lock:
        cur = db.cursor()
        cur.execute(
            "SELECT 1 FROM steps WHERE order_number=? AND step=?",
            (order_number, "Print File"),
        )
        if cur.fetchone():
            return
        ts = datetime.now().isoformat(sep=" ")
        cur.execute(
            "INSERT INTO steps(order_number, step, timestamp) VALUES (?, ?, ?)",
            (order_number, "Print File", ts),
        )
        db.commit()


def log_order(db, db_lock, order_number, company, steps):
    with db_lock:
        cur = db.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO orders(order_number, company) VALUES (?, ?)",
            (order_number, company),
        )
        cur.execute(
            "SELECT timestamp FROM steps WHERE order_number=? AND step=?",
            (order_number, "Print File"),
        )
        existing_pf = cur.fetchone()
        cur.execute("DELETE FROM steps WHERE order_number=?", (order_number,))
        cur.execute("DELETE FROM lead_times WHERE order_number=?", (order_number,))
        if existing_pf and not any(s[0] == "Print File" for s in steps):
            ts_pf = datetime.fromisoformat(existing_pf[0]) if existing_pf[0] else None
            steps = [("Print File", ts_pf)] + steps
        for step, ts in steps:
            ts_str = ts.isoformat(sep=" ") if ts else None
            cur.execute(
                "INSERT INTO steps(order_number, step, timestamp) VALUES (?, ?, ?)",
                (order_number, step, ts_str),
            )
        results = compute_lead_times({order_number: steps})
        for item in results.get(order_number, []):
            cur.execute(
                "INSERT INTO lead_times(order_number, workstation, start, end, hours) VALUES (?, ?, ?, ?, ?)",
                (
                    order_number,
                    item["workstation"],
                    item["start"].isoformat(sep=" "),
                    item["end"].isoformat(sep=" "),
                    item["hours"],
                ),
            )
        db.commit()


def load_steps(db, db_lock, order_number):
    with db_lock:
        cur = db.cursor()
        cur.execute(
            "SELECT step, timestamp FROM steps WHERE order_number=? ORDER BY rowid",
            (order_number,),
        )
        steps = []
        for step, ts_str in cur.fetchall():
            ts = datetime.fromisoformat(ts_str) if ts_str else None
            steps.append((step, ts))
    return steps


def load_lead_times(db, db_lock, order_number, start_date=None, end_date=None):
    """Load precomputed lead times optionally filtered by date range."""
    with db_lock:
        cur = db.cursor()
        query = "SELECT workstation, start, end, hours FROM lead_times WHERE order_number=?"
        params = [order_number]
        if start_date:
            query += " AND start >= ?"
            params.append(start_date.isoformat(sep=" "))
        if end_date:
            query += " AND end <= ?"
            params.append(end_date.isoformat(sep=" "))
        query += " ORDER BY start"
        cur.execute(query, params)
        rows = [
            {
                "workstation": r[0],
                "start": datetime.fromisoformat(r[1]),
                "end": datetime.fromisoformat(r[2]),
                "hours": r[3],
            }
            for r in cur.fetchall()
        ]
    return rows


def load_jobs_by_date_range(db, db_lock, start, end):
    """Fetch jobs within start/end dates from the database."""
    with db_lock:
        cur = db.cursor()
        query = (
            "SELECT lt.order_number, COALESCE(o.company,''), lt.workstation, lt.hours, lt.start, lt.end "
            "FROM lead_times lt LEFT JOIN orders o ON o.order_number = lt.order_number WHERE 1=1"
        )
        params = []
        if start:
            query += " AND lt.start >= ?"
            params.append(start.isoformat(sep=" "))
        if end:
            end_excl = end + timedelta(days=1)
            query += " AND lt.start < ?"
            params.append(end_excl.isoformat(sep=" "))
        cur.execute(query, params)
        rows = []
        for order, company, ws, hours, s, e in cur.fetchall():
            status = "Completed" if e else "In Progress"
            rows.append(
                {
                    "order": order,
                    "company": company,
                    "workstation": ws,
                    "hours": hours or 0.0,
                    "status": status,
                    "start": s[:16] if s else "",
                    "end": e[:16] if e else "",
                }
            )
    return rows
