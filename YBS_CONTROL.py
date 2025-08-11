import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
import threading
import requests
from bs4 import BeautifulSoup
import time
import os
import sqlite3
import re
from datetime import datetime
import json

from manage_html_report import compute_lead_times, write_report
import time_utils
from time_utils import business_hours_delta, business_hours_breakdown

# Default login endpoint on ybsnow.com. The site currently posts the login form
# to ``index.php`` with fields named "email", "password" and a hidden
# ``action=signin`` value.  Keep this configurable so the user can override it
# if the endpoint changes again in the future.
LOGIN_URL = "https://www.ybsnow.com/index.php"
ORDERS_URL = "https://www.ybsnow.com/manage.html"
CONFIG_FILE = os.path.expanduser("~/.ybs_control_config.json")

class OrderScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Order Scraper")

        self.session = requests.Session()
        self.logged_in = False

        self.config = self.load_config()
        db_path = self.config.get("db_path", "orders.db")
        self.db_path_var = ctk.StringVar(value=db_path)
        self.last_db_dir = os.path.dirname(db_path) or os.getcwd()
        self.connect_db(db_path)

        self.order_rows = []

        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.login_url_var = ctk.StringVar(value=LOGIN_URL)
        self.orders_url_var = ctk.StringVar(value=ORDERS_URL)
        self.refresh_interval_var = ctk.IntVar(value=5)
        self.auto_refresh_job = None

        # Tabs
        self.tab_control = ctk.CTkTabview(root)
        self.settings_tab = self.tab_control.add("Settings")
        self.orders_tab = self.tab_control.add("Orders")
        # new tab for simple database access
        self.database_tab = self.tab_control.add("Database")
        self.tab_control.pack(expand=1, fill="both")

        # Settings Tab
        ctk.CTkLabel(self.settings_tab, text="Username:").grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.username_var).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Password:").grid(row=1, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.password_var, show='*').grid(row=1, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Login URL:").grid(row=2, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.login_url_var).grid(row=2, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Orders URL:").grid(row=3, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.orders_url_var).grid(row=3, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Login", command=self.login).grid(row=4, column=0, columnspan=2, pady=10)

        ctk.CTkLabel(self.settings_tab, text="Refresh interval (min):").grid(row=5, column=0, padx=5, pady=5)
        self.refresh_entry = ctk.CTkEntry(
            self.settings_tab,
            textvariable=self.refresh_interval_var,
            state="disabled",
        )
        self.refresh_entry.grid(row=5, column=1, padx=5, pady=5)
        self.refresh_button = ctk.CTkButton(
            self.settings_tab,
            text="Set Interval",
            command=self.schedule_auto_refresh,
            state="disabled",
        )
        self.refresh_button.grid(row=6, column=0, columnspan=2, pady=10)

        ctk.CTkLabel(self.settings_tab, text="Database File:").grid(row=7, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.db_path_var).grid(row=7, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Browse", command=self.browse_db).grid(row=7, column=2, padx=5, pady=5)

        ctk.CTkLabel(self.settings_tab, text="Business Start (HH:MM):").grid(row=8, column=0, padx=5, pady=5)
        self.business_start_var = ctk.StringVar(value=time_utils.BUSINESS_START.strftime("%H:%M"))
        ctk.CTkEntry(self.settings_tab, textvariable=self.business_start_var, width=80).grid(row=8, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Business End (HH:MM):").grid(row=9, column=0, padx=5, pady=5)
        self.business_end_var = ctk.StringVar(value=time_utils.BUSINESS_END.strftime("%H:%M"))
        ctk.CTkEntry(self.settings_tab, textvariable=self.business_end_var, width=80).grid(row=9, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Set Hours", command=self.update_business_hours).grid(row=10, column=0, columnspan=2, pady=10)

        # Orders Tab
        self.search_var = ctk.StringVar()
        self.start_date_var = ctk.StringVar()
        self.end_date_var = ctk.StringVar()
        search_frame = ctk.CTkFrame(self.orders_tab)
        search_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(search_frame, text="Order Search:").pack(side="left", padx=5)
        ctk.CTkEntry(search_frame, textvariable=self.search_var, width=120).pack(side="left", padx=5)
        ctk.CTkButton(search_frame, text="Search", command=self.search_orders).pack(side="left", padx=5)

        # date range controls
        ctk.CTkLabel(search_frame, text="Start (YYYY-MM-DD):").pack(side="left", padx=5)
        ctk.CTkEntry(search_frame, textvariable=self.start_date_var, width=100).pack(side="left", padx=5)
        ctk.CTkLabel(search_frame, text="End (YYYY-MM-DD):").pack(side="left", padx=5)
        ctk.CTkEntry(search_frame, textvariable=self.end_date_var, width=100).pack(side="left", padx=5)

        self.table_frame = ctk.CTkFrame(self.orders_tab)
        self.table_frame.pack(expand=1, fill="both", padx=10, pady=10)

        self.orders_tree = ttk.Treeview(
            self.table_frame,
            columns=("Order", "Company", "Status", "Priority"),
            show="headings",
        )
        style = ttk.Style()
        style.configure("Treeview", font=("Arial", 14), rowheight=28, borderwidth=1, relief="solid")
        style.configure("Treeview.Heading", font=("Arial", 14, "bold"))
        self.orders_tree.heading("Order", text="Order")
        self.orders_tree.heading("Company", text="Company")
        self.orders_tree.heading("Status", text="Status")
        self.orders_tree.heading("Priority", text="Priority")
        self.orders_tree.pack(side="left", expand=1, fill="both")

        scrollbar = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        # Report frame for lead time information
        self.report_frame = ctk.CTkFrame(self.orders_tab)
        self.report_frame.pack(expand=1, fill="both", padx=10, pady=10)
        ctk.CTkLabel(self.report_frame, text="Realtime Reporting", font=("Arial", 16, "bold")).pack(pady=5)

        self.report_tree = ttk.Treeview(
            self.report_frame,
            columns=("Workstation", "Start", "End", "Hours"),
            show="headings",
        )
        self.report_tree.heading("Workstation", text="Workstation")
        self.report_tree.heading("Start", text="Start")
        self.report_tree.heading("End", text="End")
        self.report_tree.heading("Hours", text="Hours")
        style.configure("Report.Treeview", font=("Arial", 14), rowheight=28, borderwidth=1, relief="solid")
        style.configure("Report.Treeview.Heading", font=("Arial", 14, "bold"))
        self.report_tree.configure(style="Report.Treeview")
        self.report_tree.pack(side="left", expand=1, fill="both")
        rscroll = ttk.Scrollbar(self.report_frame, orient="vertical", command=self.report_tree.yview)
        self.report_tree.configure(yscrollcommand=rscroll.set)
        rscroll.pack(side="right", fill="y")

        ctk.CTkButton(self.orders_tab, text="Export Report", command=self.export_selected).pack(pady=5)
        ctk.CTkButton(self.orders_tab, text="Export Date Range", command=self.export_date_range).pack(pady=5)
        ctk.CTkButton(self.orders_tab, text="Show Breakdown", command=self.show_breakdown).pack(pady=5)
        ctk.CTkButton(self.orders_tab, text="Refresh Orders", command=self.get_orders).pack(pady=5)

        self.orders_tree.bind("<<TreeviewSelect>>", self.show_report)
        self.orders_tree.bind("<Double-1>", self.export_report)

        # Database Tab view
        self.db_tree = ttk.Treeview(
            self.database_tab,
            columns=("Order", "Company"),
            show="headings",
        )
        self.db_tree.heading("Order", text="Order")
        self.db_tree.heading("Company", text="Company")
        self.db_tree.pack(expand=1, fill="both", padx=10, pady=10)
        ctk.CTkButton(
            self.database_tab, text="Refresh", command=self.refresh_database_tab
        ).pack(pady=5)

        self.refresh_database_tab()

        # Relogin timer
        self.relogin_thread = threading.Thread(target=self.relogin_loop, daemon=True)
        self.relogin_thread.start()

    def login(self):
        username = self.username_var.get()
        password = self.password_var.get()
        # The login form uses "email" and a hidden "action" field set to
        # "signin".  Submit those values so the session authenticates
        # correctly.
        data = {
            'email': username,
            'password': password,
            'action': 'signin',
        }
        login_url = self.login_url_var.get() or LOGIN_URL

        def worker():
            try:
                resp = self.session.post(login_url, data=data, timeout=10)
            except requests.RequestException as e:
                if hasattr(self, "root") and self.root:
                    self.root.after(0, lambda: messagebox.showerror("Login", f"Login request failed: {e}"))
                else:
                    messagebox.showerror("Login", f"Login request failed: {e}")
                return
            if hasattr(self, "root") and self.root:
                self.root.after(0, lambda: self._handle_login_response(resp))
            else:
                self._handle_login_response(resp)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        if not hasattr(self, "root") or not self.root:
            thread.join()

    def _handle_login_response(self, resp):
        orders_page = os.path.basename(self.orders_url_var.get() or ORDERS_URL).lower()
        if "logout" in resp.text.lower() or orders_page in resp.text.lower():
            self.logged_in = True
            messagebox.showinfo("Login", "Login successful!")
            try:
                self.tab_control.set("Orders")
            except Exception:
                pass
            self.refresh_entry.configure(state="normal")
            self.refresh_button.configure(state="normal")
            self.schedule_auto_refresh()
        else:
            self.logged_in = False
            messagebox.showerror("Login", "Login failed.")
        self.get_orders()

    def get_orders(self):
        if not self.logged_in:
            messagebox.showerror("Error", "Not logged in!")
            return
        orders_url = self.orders_url_var.get() or ORDERS_URL

        def worker():
            try:
                resp = self.session.get(orders_url, timeout=10)
            except requests.RequestException as e:
                if hasattr(self, "root") and self.root:
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to fetch orders: {e}"))
                else:
                    messagebox.showerror("Error", f"Failed to fetch orders: {e}")
                return
            if hasattr(self, "root") and self.root:
                self.root.after(0, lambda: self._process_orders_html(resp.text))
            else:
                self._process_orders_html(resp.text)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        if not hasattr(self, "root") or not self.root:
            thread.join()

    def _process_orders_html(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        tbody = soup.find('tbody', id='table')
        self.orders_tree.delete(*self.orders_tree.get_children())
        self.order_rows = []
        if tbody:
            for tr in tbody.find_all('tr'):
                tds = tr.find_all('td')
                try:
                    # Some rows place the company name and order number in the
                    # same table cell.  Collect the string fragments from that
                    # cell and split out the first textual fragment as the
                    # company name and the first fragment containing digits as
                    # the order number.  This keeps each value under the
                    # correct heading in the UI.
                    cell_parts = list(tds[0].stripped_strings)
                    order_num = ""
                    company = ""
                    for part in cell_parts:
                        if not order_num and re.search(r"\d", part):
                            match = re.search(r"([A-Za-z0-9_-]+)$", part)
                            order_num = match.group(1) if match else re.sub(r"[^A-Za-z0-9_-]", "", part)
                        elif not company:
                            company = part

                    # Remaining columns contain status and priority, but the
                    # page includes spacer cells.  Use indexes 2 and 4 rather
                    # than 1 and 3 to skip those spacers when present.
                    status = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                    priority = ""
                    if len(tds) > 4:
                        pri_input = tds[4].find("input")
                        priority = pri_input.get("value") if pri_input else tds[4].get_text(strip=True)

                    steps = []
                    for li in tr.select('ul.workplaces li'):
                        step_p = li.find('p')
                        step_name = re.sub(r'^\d+', '', step_p.get_text(strip=True)) if step_p else ''
                        time_p = li.find('p', class_='np')
                        ts = None
                        if time_p:
                            text = time_p.get_text(strip=True).replace('\xa0', '').strip()
                            if text:
                                try:
                                    ts = datetime.strptime(text, "%m/%d/%y %H:%M")
                                except ValueError:
                                    pass
                        steps.append((step_name, ts))

                    self.log_order(order_num, company, steps)
                    row = (order_num, company, status, priority)
                    self.order_rows.append(row)
                    self.orders_tree.insert('', 'end', values=row)
                except Exception as e:
                    print("Error parsing row:", e)
        self.refresh_database_tab()

    def log_order(self, order_number, company, steps):
        cur = self.db.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO orders(order_number, company) VALUES (?, ?)",
            (order_number, company),
        )
        cur.execute("DELETE FROM steps WHERE order_number=?", (order_number,))
        cur.execute("DELETE FROM lead_times WHERE order_number=?", (order_number,))
        for step, ts in steps:
            ts_str = ts.isoformat(sep=" ") if ts else None
            cur.execute(
                "INSERT INTO steps(order_number, step, timestamp) VALUES (?, ?, ?)",
                (order_number, step, ts_str),
            )
        # precompute lead times for storage
        results = compute_lead_times({order_number: steps})
        for item in results.get(order_number, []):
            cur.execute(
                "INSERT INTO lead_times(order_number, workstation, start, end, hours) VALUES (?, ?, ?, ?, ?)",
                (
                    order_number,
                    item["step"],
                    item["start"].isoformat(sep=" "),
                    item["end"].isoformat(sep=" "),
                    item["hours"],
                ),
            )
        self.db.commit()

    def load_steps(self, order_number):
        cur = self.db.cursor()
        cur.execute(
            "SELECT step, timestamp FROM steps WHERE order_number=? ORDER BY rowid",
            (order_number,),
        )
        steps = []
        for step, ts_str in cur.fetchall():
            ts = datetime.fromisoformat(ts_str) if ts_str else None
            steps.append((step, ts))
        return steps

    def load_lead_times(self, order_number, start_date=None, end_date=None):
        """Load precomputed lead times optionally filtered by date range."""
        cur = self.db.cursor()
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
                "step": r[0],
                "start": datetime.fromisoformat(r[1]),
                "end": datetime.fromisoformat(r[2]),
                "hours": r[3],
            }
            for r in cur.fetchall()
        ]
        return rows

    def get_date_range(self):
        """Return (start, end) datetimes from the entry fields or None."""
        start = None
        end = None
        if self.start_date_var.get().strip():
            try:
                start = datetime.strptime(self.start_date_var.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Invalid start date format")
        if self.end_date_var.get().strip():
            try:
                end = datetime.strptime(self.end_date_var.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Invalid end date format")
        return start, end

    def show_report(self, event=None):
        selected = self.orders_tree.focus()
        if not selected:
            return
        order_number = self.orders_tree.item(selected, "values")[0]
        start, end = self.get_date_range()
        steps = self.load_steps(order_number)
        rows = self.load_lead_times(order_number, start, end)
        if not rows:
            rows = compute_lead_times({order_number: steps}, start, end).get(order_number, [])
            # store for future
            cur = self.db.cursor()
            for item in rows:
                cur.execute(
                    "INSERT INTO lead_times(order_number, workstation, start, end, hours) VALUES (?, ?, ?, ?, ?)",
                    (
                        order_number,
                        item["step"],
                        item["start"].isoformat(sep=" "),
                        item["end"].isoformat(sep=" "),
                        item["hours"],
                    ),
                )
            self.db.commit()
        row_map = {r["step"]: r for r in rows}
        self.report_tree.delete(*self.report_tree.get_children())
        total = 0.0
        for idx, (name, ts) in enumerate(steps):
            row = row_map.get(name)
            if row:
                start_ts = row["start"]
                end_ts = row["end"]
                hours = row["hours"]
            else:
                start_ts = steps[idx - 1][1] if idx > 0 else None
                end_ts = ts
                hours = None
                if start_ts and end_ts:
                    delta = business_hours_delta(start_ts, end_ts)
                    hours = delta.total_seconds() / 3600.0
            self.report_tree.insert(
                "",
                "end",
                values=(
                    name,
                    start_ts.strftime("%Y-%m-%d %H:%M") if start_ts else "",
                    end_ts.strftime("%Y-%m-%d %H:%M") if end_ts else "",
                    f"{hours:.2f}" if hours is not None else "",
                ),
            )
            if hours is not None:
                total += hours
        self.report_tree.insert("", "end", values=("TOTAL", "", "", f"{total:.2f}"))

    def export_selected(self):
        self.export_report()

    def search_orders(self):
        term = self.search_var.get().lower()
        self.orders_tree.delete(*self.orders_tree.get_children())
        for row in self.order_rows:
            if not term or term in row[0].lower():
                self.orders_tree.insert('', 'end', values=row)

    def export_report(self, event=None):
        selected = self.orders_tree.focus()
        if not selected:
            return
        order_number = self.orders_tree.item(selected, "values")[0]
        start, end = self.get_date_range()
        rows = self.load_lead_times(order_number, start, end)
        if not rows:
            steps = self.load_steps(order_number)
            rows = compute_lead_times({order_number: steps}, start, end).get(order_number, [])
        results = {order_number: rows}
        safe_order = re.sub(r'[^A-Za-z0-9_-]', '', order_number)
        suffix = ""
        if start or end:
            s = start.strftime("%Y%m%d") if start else "begin"
            e = end.strftime("%Y%m%d") if end else "now"
            suffix = f"_{s}_{e}"
        path = f"lead_time_{safe_order}{suffix}.csv"
        write_report(results, path)
        messagebox.showinfo("Export", f"Report written to {path}")

    def export_date_range(self):
        """Export a report for all jobs within the provided date range."""
        start, end = self.get_date_range()
        if not start and not end:
            messagebox.showerror("Export", "Enter a start or end date")
            return
        cur = self.db.cursor()
        query = "SELECT DISTINCT order_number FROM lead_times WHERE 1=1"
        params = []
        if start:
            query += " AND start >= ?"
            params.append(start.isoformat(sep=" "))
        if end:
            query += " AND end <= ?"
            params.append(end.isoformat(sep=" "))
        cur.execute(query, params)
        orders = [r[0] for r in cur.fetchall()]
        results = {}
        for order in orders:
            rows = self.load_lead_times(order, start, end)
            if not rows:
                steps = self.load_steps(order)
                rows = compute_lead_times({order: steps}, start, end).get(order, [])
            if rows:
                results[order] = rows
        if not results:
            messagebox.showinfo("Export", "No data for range")
            return
        s = start.strftime("%Y%m%d") if start else "begin"
        e = end.strftime("%Y%m%d") if end else "now"
        path = f"lead_time_{s}_{e}.csv"
        write_report(results, path)
        messagebox.showinfo("Export", f"Report written to {path}")

    def schedule_auto_refresh(self):
        if not self.logged_in:
            return
        try:
            interval = int(self.refresh_interval_var.get())
        except (TypeError, ValueError):
            interval = 5
            self.refresh_interval_var.set(interval)
        interval_ms = max(1, interval) * 60 * 1000
        if self.auto_refresh_job is not None:
            try:
                self.root.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
        self.auto_refresh_job = self.root.after(interval_ms, self.auto_refresh)

    def auto_refresh(self):
        if self.logged_in:
            self.get_orders()
        self.schedule_auto_refresh()

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f)
        except Exception:
            pass

    def update_business_hours(self):
        try:
            start = datetime.strptime(self.business_start_var.get().strip(), "%H:%M").time()
            end = datetime.strptime(self.business_end_var.get().strip(), "%H:%M").time()
        except ValueError:
            messagebox.showerror("Business Hours", "Invalid time format")
            return
        if start >= end:
            messagebox.showerror("Business Hours", "Start must be before end")
            return
        time_utils.BUSINESS_START = start
        time_utils.BUSINESS_END = end
        messagebox.showinfo("Business Hours", "Business hours updated")

    def show_breakdown(self):
        selected = self.orders_tree.focus()
        if not selected:
            messagebox.showerror("Breakdown", "No order selected")
            return
        order_number = self.orders_tree.item(selected, "values")[0]
        start, end = self.get_date_range()
        steps = self.load_steps(order_number)
        lines = []
        for (name, s), (next_name, e) in zip(steps, steps[1:]):
            if not s or not e:
                continue
            segments = business_hours_breakdown(s, e)
            if segments:
                lines.append(f"{next_name}:")
                for seg_start, seg_end in segments:
                    hours = (seg_end - seg_start).total_seconds() / 3600.0
                    lines.append(f"  {seg_start} -> {seg_end} ({hours:.2f}h)")
        messagebox.showinfo("Breakdown", "\n".join(lines) if lines else "No breakdown data")

    def browse_db(self):
        path = filedialog.askopenfilename(
            filetypes=[("SQLite DB", "*.db"), ("All Files", "*")],
            initialdir=self.last_db_dir,
        )
        if path:
            self.connect_db(path)

    def connect_db(self, path):
        if hasattr(self, "db") and self.db:
            try:
                self.db.close()
            except Exception:
                pass
        self.db_path_var.set(path)
        self.config["db_path"] = path
        self.last_db_dir = os.path.dirname(path) or os.getcwd()
        self.save_config()
        self.db = sqlite3.connect(path)
        cur = self.db.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS orders (order_number TEXT PRIMARY KEY, company TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS steps (order_number TEXT, step TEXT, timestamp TEXT)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS lead_times (order_number TEXT, workstation TEXT, start TEXT, end TEXT, hours REAL)"
        )
        self.db.commit()

    def refresh_database_tab(self):
        """Populate the Database tab with the Orders table contents."""
        self.db_tree.delete(*self.db_tree.get_children())
        cur = self.db.cursor()
        for order, company in cur.execute("SELECT order_number, company FROM orders ORDER BY order_number"):
            self.db_tree.insert('', 'end', values=(order, company))

    def relogin_loop(self):
        while True:
            time.sleep(2*60*60)  # 2 hours
            if self.logged_in:
                print("Relogging in...")
                self.root.after(0, self.login)

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    root = ctk.CTk()
    app = OrderScraperApp(root)
    root.mainloop()
