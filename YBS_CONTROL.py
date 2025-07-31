import customtkinter as ctk
from tkinter import ttk, messagebox
import threading
import requests
from bs4 import BeautifulSoup
import time
import os
import sqlite3
import re
from datetime import datetime
from manage_html_report import compute_lead_times, write_report

# Default login endpoint on ybsnow.com. The site currently posts the login form
# to ``index.php`` with fields named "email", "password" and a hidden
# ``action=signin`` value.  Keep this configurable so the user can override it
# if the endpoint changes again in the future.
LOGIN_URL = "https://www.ybsnow.com/index.php"
ORDERS_URL = "https://www.ybsnow.com/manage.html"

class OrderScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Order Scraper")

        self.session = requests.Session()
        self.logged_in = False

        self.db = sqlite3.connect("orders.db")
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

        self.order_rows = []

        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.login_url_var = ctk.StringVar(value=LOGIN_URL)
        self.orders_url_var = ctk.StringVar(value=ORDERS_URL)

        # Tabs
        self.tab_control = ctk.CTkTabview(root)
        self.settings_tab = self.tab_control.add("Settings")
        self.orders_tab = self.tab_control.add("Orders")
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

        # Orders Tab
        self.search_var = ctk.StringVar()
        search_frame = ctk.CTkFrame(self.orders_tab)
        search_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(search_frame, text="Order Search:").pack(side="left", padx=5)
        ctk.CTkEntry(search_frame, textvariable=self.search_var, width=120).pack(side="left", padx=5)
        ctk.CTkButton(search_frame, text="Search", command=self.search_orders).pack(side="left", padx=5)

        # Date range controls
        self.start_var = ctk.StringVar()
        self.end_var = ctk.StringVar()
        date_frame = ctk.CTkFrame(self.orders_tab)
        date_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(date_frame, text="Start (YYYY-MM-DD):").pack(side="left", padx=5)
        ctk.CTkEntry(date_frame, textvariable=self.start_var, width=120).pack(side="left", padx=5)
        ctk.CTkLabel(date_frame, text="End (YYYY-MM-DD):").pack(side="left", padx=5)
        ctk.CTkEntry(date_frame, textvariable=self.end_var, width=120).pack(side="left", padx=5)
        ctk.CTkButton(date_frame, text="Apply", command=self.show_report).pack(side="left", padx=5)

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
        ctk.CTkButton(self.orders_tab, text="Refresh Orders", command=self.get_orders).pack(pady=5)

        self.orders_tree.bind("<<TreeviewSelect>>", self.show_report)
        self.orders_tree.bind("<Double-1>", self.export_report)

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
        resp = self.session.post(login_url, data=data)
        orders_page = os.path.basename(self.orders_url_var.get() or ORDERS_URL).lower()
        if "logout" in resp.text.lower() or orders_page in resp.text.lower():
            self.logged_in = True
            messagebox.showinfo("Login", "Login successful!")
            try:
                self.tab_control.set("Orders")
            except Exception:
                pass
        else:
            self.logged_in = False
            messagebox.showerror("Login", "Login failed.")
        self.get_orders()

    def get_orders(self):
        if not self.logged_in:
            messagebox.showerror("Error", "Not logged in!")
            return
        orders_url = self.orders_url_var.get() or ORDERS_URL
        resp = self.session.get(orders_url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        tbody = soup.find('tbody', id='table')
        self.orders_tree.delete(*self.orders_tree.get_children())
        self.order_rows = []
        if tbody:
            for tr in tbody.find_all('tr'):
                tds = tr.find_all('td')
                try:
                    order_text = tds[0].get_text(strip=True)
                    order_num = order_text.split()[-1]
                    order_num = re.sub(r'[^A-Za-z0-9_-]', '', order_num)
                    company = tds[1].get_text(strip=True)
                    status = tds[3].get_text(strip=True)
                    priority = tds[5].find('input').get('value') if tds[5].find('input') else ''

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

    def load_lead_times(self, order_number):
        cur = self.db.cursor()
        cur.execute(
            "SELECT workstation, start, end, hours FROM lead_times WHERE order_number=? ORDER BY start",
            (order_number,),
        )
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
        """Return selected start and end datetimes or ``None``."""
        start_str = self.start_var.get().strip()
        end_str = self.end_var.get().strip()
        start = datetime.strptime(start_str, "%Y-%m-%d") if start_str else None
        if end_str:
            end = (
                datetime.strptime(end_str, "%Y-%m-%d")
                + timedelta(days=1)
                - timedelta(microseconds=1)
            )
        else:
            end = None
        return start, end

    def show_report(self, event=None):
        selected = self.orders_tree.focus()
        if not selected:
            return
        order_number = self.orders_tree.item(selected, "values")[0]
        steps = self.load_steps(order_number)
        start, end = self.get_date_range()
        rows = compute_lead_times({order_number: steps}, start, end).get(order_number, [])
        self.report_tree.delete(*self.report_tree.get_children())
        total = 0.0
        for item in rows:
            self.report_tree.insert(
                "",
                "end",
                values=(
                    item["step"],
                    item["start"].strftime("%Y-%m-%d %H:%M"),
                    item["end"].strftime("%Y-%m-%d %H:%M"),
                    f"{item['hours']:.2f}",
                ),
            )
            total += item["hours"]
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
        steps = self.load_steps(order_number)
        start, end = self.get_date_range()
        rows = compute_lead_times({order_number: steps}, start, end).get(order_number, [])
        results = {order_number: rows}
        safe_order = re.sub(r'[^A-Za-z0-9_-]', '', order_number)
        path = f"lead_time_{safe_order}.csv"
        write_report(results, path)
        messagebox.showinfo("Export", f"Report written to {path}")

    def relogin_loop(self):
        while True:
            time.sleep(2*60*60)  # 2 hours
            if self.logged_in:
                print("Relogging in...")
                self.login()

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    root = ctk.CTk()
    app = OrderScraperApp(root)
    root.mainloop()
