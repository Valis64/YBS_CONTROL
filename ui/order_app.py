from __future__ import annotations

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
import threading
import requests  # type: ignore[import-untyped]
import time
import os
import re
from datetime import datetime, timedelta
import csv
import logging
from dataclasses import dataclass
from typing import Any, Optional
from tkcalendar import DateEntry

from config.settings import load_config as load_config_file, save_config as save_config_file
from data import db

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from manage_html_report import (
    compute_lead_times,
    write_report,
    generate_realtime_report,
    write_realtime_report,
)
import time_utils
from time_utils import business_hours_delta, business_hours_breakdown
from services.ybs_client import (
    LOGIN_URL,
    ORDERS_URL,
    QUEUE_URL,
    login as service_login,
    fetch_orders as service_fetch_orders,
)
from parsers.manage_html import parse_orders, parse_queue

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class JobStep:
    """Representation of a single job step."""

    name: str
    timestamp: Optional[datetime]


@dataclass
class OrderRow:
    """Row data for the orders table."""

    number: str
    company: str
    status: str
    priority: str

class OrderScraperApp:
    def __init__(
        self,
        root: Any,
        session: Optional[requests.Session] = None,
        username: str = "",
        password: str = "",
        login_url: str = LOGIN_URL,
        orders_url: str = ORDERS_URL,
    ) -> None:
        self.root = root
        self.root.title("Order Scraper")
        # Make the main window slightly wider so the Date Range Report tab has
        # a bit more horizontal room (about 15% wider than the previous
        # default).
        try:
            self.root.geometry("1200x700")
        except Exception:
            pass

        self.session = session or requests.Session()
        self.logged_in = session is not None

        self.config = self.load_config()

        # Configure database path from config
        db_path = self.config.get("db_path", "orders.db")
        self.db_path_var = ctk.StringVar(value=db_path)
        self.last_db_dir = os.path.dirname(db_path) or os.getcwd()
        self.db: Any = None
        self.db_lock: Any = threading.Lock()
        self.connect_db(db_path)

        # Load business hours from config if available
        start_str = self.config.get("business_start")
        end_str = self.config.get("business_end")
        if start_str and end_str:
            try:
                start = datetime.strptime(start_str, "%H:%M").time()
                end = datetime.strptime(end_str, "%H:%M").time()
                if start < end:
                    time_utils.BUSINESS_START = start
                    time_utils.BUSINESS_END = end
            except ValueError:
                pass

        self.order_rows: list[OrderRow] = []

        self.username_var = ctk.StringVar(value=username)
        self.password_var = ctk.StringVar(value=password)
        self.login_url_var = ctk.StringVar(value=login_url)
        self.orders_url_var = ctk.StringVar(value=orders_url)
        # Refresh every minute by default instead of 5 minutes
        self.refresh_interval_var = ctk.IntVar(value=1)
        self.auto_refresh_job: Any = None
        self.refresh_timer_job: Any = None
        self.next_refresh_time: Optional[datetime] = None
        self.refresh_timer_var = ctk.StringVar(value="")
        # export configuration
        export_path = self.config.get("export_path", os.getcwd())
        self.export_path_var = ctk.StringVar(value=export_path)
        self.export_time_var = ctk.StringVar(value=self.config.get("export_time", ""))
        self.export_job = None
        self.last_export_dir = export_path

        # date range report configuration
        self.range_start_var = ctk.StringVar()
        self.range_end_var = ctk.StringVar()
        self.range_total_jobs_var = ctk.StringVar(value="0")
        self.range_total_hours_var = ctk.StringVar(value="0.00")
        self.date_range_rows: list[dict[str, Any]] = []
        self.filtered_date_range_rows: list[dict[str, Any]] = []
        self.raw_date_range_rows: list[dict[str, Any]] = []
        self.filtered_raw_date_range_rows: list[dict[str, Any]] = []
        self.date_range_filter_var = ctk.StringVar()
        # Track orders currently listed on the print-file queue page so we can
        # detect when they disappear.
        self.queue_orders: set[str] = set()

        # Tabs
        self.tab_control = ctk.CTkTabview(root)
        self.orders_tab = self.tab_control.add("Orders")
        # date range report tab
        self.date_range_tab = self.tab_control.add("Date Range Report")
        # settings tab on far right
        self.settings_tab = self.tab_control.add("Settings")
        self.tab_control.pack(expand=1, fill="both")

        self.refresh_timer_label = ctk.CTkLabel(root, textvariable=self.refresh_timer_var)
        self.refresh_timer_label.place(relx=1.0, rely=1.0, anchor="se", padx=10, pady=5)

        self.analytics_window: Any = None

        # Settings Tab
        ctk.CTkLabel(self.settings_tab, text="Refresh interval (min):").grid(row=0, column=0, padx=5, pady=5)
        self.refresh_entry = ctk.CTkEntry(
            self.settings_tab,
            textvariable=self.refresh_interval_var,
            state="disabled",
        )
        self.refresh_entry.grid(row=0, column=1, padx=5, pady=5)
        self.refresh_button = ctk.CTkButton(
            self.settings_tab,
            text="Set Interval",
            command=self.schedule_auto_refresh,
            state="disabled",
        )
        self.refresh_button.grid(row=1, column=0, columnspan=2, pady=10)

        ctk.CTkLabel(self.settings_tab, text="Database File:").grid(row=2, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.db_path_var).grid(row=2, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Browse", command=self.browse_db).grid(row=2, column=2, padx=5, pady=5)

        ctk.CTkLabel(self.settings_tab, text="Business Start (HH:MM):").grid(row=3, column=0, padx=5, pady=5)
        self.business_start_var = ctk.StringVar(value=time_utils.BUSINESS_START.strftime("%H:%M"))
        ctk.CTkEntry(self.settings_tab, textvariable=self.business_start_var, width=80).grid(row=3, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Business End (HH:MM):").grid(row=4, column=0, padx=5, pady=5)
        self.business_end_var = ctk.StringVar(value=time_utils.BUSINESS_END.strftime("%H:%M"))
        ctk.CTkEntry(self.settings_tab, textvariable=self.business_end_var, width=80).grid(row=4, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Set Hours", command=self.update_business_hours).grid(row=5, column=0, columnspan=2, pady=10)

        ctk.CTkLabel(self.settings_tab, text="Export Path:").grid(row=6, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.export_path_var).grid(row=6, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Browse", command=self.browse_export_path).grid(row=6, column=2, padx=5, pady=5)

        ctk.CTkLabel(self.settings_tab, text="Export Time (HH:MM):").grid(row=7, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.export_time_var, width=80).grid(row=7, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Set Export", command=self.update_export_settings).grid(row=8, column=0, columnspan=2, pady=10)

        # Orders Tab
        self.search_var = ctk.StringVar()
        self.start_date_var = ctk.StringVar()
        self.end_date_var = ctk.StringVar()
        presets = {
            "Today": "today",
            "Yesterday": "yesterday",
            "Last 7 days": "last7",
            "Last 30 days": "last30",
            "This month": "thisMonth",
            "Last month": "lastMonth",
            "Custom": "custom",
        }
        self.preset_labels = presets
        self.preset_codes = {v: k for k, v in presets.items()}
        last_range = self.config.get("last_range", {})
        start_default = last_range.get("start", "")
        end_default = last_range.get("end", "")
        preset_default = self.preset_codes.get(last_range.get("preset", "last7"), "Last 7 days")
        self.start_date_var.set(start_default)
        self.end_date_var.set(end_default)
        self.preset_var = ctk.StringVar(value=preset_default)
        search_frame = ctk.CTkFrame(self.orders_tab)
        search_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(search_frame, text="Order Search:").pack(side="left", padx=5)
        ctk.CTkEntry(search_frame, textvariable=self.search_var, width=120).pack(side="left", padx=5)
        ctk.CTkButton(search_frame, text="Search", command=self.search_orders).pack(side="left", padx=5)

        # date range controls
        ctk.CTkLabel(search_frame, text="Range:").pack(side="left", padx=5)
        self.preset_menu = ctk.CTkOptionMenu(
            search_frame,
            variable=self.preset_var,
            values=list(presets.keys()),
            command=self.update_preset,
            width=120,
        )
        self.preset_menu.pack(side="left", padx=5)
        self.start_entry = DateEntry(search_frame, textvariable=self.start_date_var, width=12, date_pattern="yyyy-mm-dd")
        self.start_entry.pack(side="left", padx=5)
        self.end_entry = DateEntry(search_frame, textvariable=self.end_date_var, width=12, date_pattern="yyyy-mm-dd")
        self.end_entry.pack(side="left", padx=5)
        self.start_entry.bind("<<DateEntrySelected>>", self.save_current_range)
        self.end_entry.bind("<<DateEntrySelected>>", self.save_current_range)
        self.update_preset(self.preset_var.get())

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
        ctk.CTkButton(
            self.orders_tab, text="Realtime Report", command=self.export_realtime_report
        ).pack(pady=5)
        ctk.CTkButton(self.orders_tab, text="Show Breakdown", command=self.show_breakdown).pack(pady=5)
        ctk.CTkButton(self.orders_tab, text="Refresh Orders", command=self.get_orders).pack(pady=5)
        ctk.CTkButton(self.orders_tab, text="Open Analytics", command=self.open_analytics_window).pack(pady=5)

        self.orders_tree.bind("<<TreeviewSelect>>", self.show_report)
        self.orders_tree.bind("<Double-1>", self.export_report)

        # Date Range Report tab view
        control_frame = ctk.CTkFrame(self.date_range_tab)
        control_frame.grid(row=0, column=0, columnspan=7, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(control_frame, text="Start Date:").grid(row=0, column=0, padx=5, pady=5)
        DateEntry(control_frame, textvariable=self.range_start_var, width=12, date_pattern="yyyy-mm-dd").grid(
            row=0, column=1, padx=5, pady=5
        )
        ctk.CTkLabel(control_frame, text="End Date:").grid(row=0, column=2, padx=5, pady=5)
        DateEntry(control_frame, textvariable=self.range_end_var, width=12, date_pattern="yyyy-mm-dd").grid(
            row=0, column=3, padx=5, pady=5
        )
        ctk.CTkButton(control_frame, text="Generate Report", command=self.run_date_range_report).grid(
            row=0, column=4, padx=5, pady=5
        )
        ctk.CTkButton(control_frame, text="Clear", command=self.clear_date_range_report).grid(
            row=0, column=5, padx=5, pady=5
        )
        ctk.CTkButton(control_frame, text="Export CSV", command=self.export_date_range_csv).grid(
            row=0, column=6, padx=5, pady=5
        )
        ctk.CTkLabel(control_frame, text="Search:").grid(row=1, column=0, padx=5, pady=5)
        self.date_range_filter_entry = ctk.CTkEntry(
            control_frame, textvariable=self.date_range_filter_var
        )
        self.date_range_filter_entry.grid(row=1, column=1, padx=5, pady=5)
        self.date_range_filter_entry.bind(
            "<Return>", lambda e: self.filter_date_range_rows()
        )
        ctk.CTkButton(control_frame, text="Filter", command=self.filter_date_range_rows).grid(
            row=1, column=2, padx=5, pady=5
        )
        self.date_rows_expanded = False
        self.expand_collapse_btn = ctk.CTkButton(
            control_frame, text="Expand All", command=self.toggle_date_rows
        )
        self.expand_collapse_btn.grid(row=2, column=1, columnspan=2, padx=5, pady=5)

        self.date_range_tab.grid_rowconfigure(2, weight=1)
        self.date_range_tab.grid_columnconfigure(0, weight=1)
        table_frame = ctk.CTkFrame(self.date_range_tab)
        table_frame.grid(row=2, column=0, columnspan=7, sticky="nsew", padx=10, pady=10)

        columns = (
            "company",
            "workstation",
            "start",
            "end",
            "hours",
            "status",
        )
        self.date_tree = ttk.Treeview(
            table_frame, columns=columns, show="tree headings"
        )
        self.date_tree.heading(
            "#0",
            text="Order",
            anchor="center",
            command=lambda: self.sort_date_range_table("order"),
        )
        self.date_tree.column("#0", anchor="center")
        headings = [
            "Company",
            "Workstation",
            "Start",
            "End",
            "Hours",
            "Status",
        ]
        for col, head in zip(columns, headings):
            self.date_tree.heading(
                col,
                text=head,
                anchor="center",
                command=lambda c=col: self.sort_date_range_table(c),  # type: ignore[call-overload]
            )
            self.date_tree.column(col, anchor="center")
        self.date_tree.pack(side="left", expand=1, fill="both")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.date_tree.yview)
        self.date_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

        self.date_tree.tag_configure("even", background="#ffffff")
        self.date_tree.tag_configure("odd", background="#f0f0ff")
        self.date_tree.tag_configure("total", background="#e0e0e0", font=("Arial", 10, "bold"))
        self.date_tree.tag_configure("inprogress", background="#fff0e6")
        self.date_tree.bind("<Double-1>", self.toggle_order_row)

        summary = ctk.CTkFrame(self.date_range_tab)
        summary.grid(row=3, column=0, columnspan=7, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(summary, text="Total Jobs:").grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkLabel(summary, textvariable=self.range_total_jobs_var).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(summary, text="Total Hours:").grid(row=0, column=2, padx=5, pady=5)
        ctk.CTkLabel(summary, textvariable=self.range_total_hours_var).grid(row=0, column=3, padx=5, pady=5)

        self.schedule_daily_export()

        # Relogin timer
        self.relogin_thread = threading.Thread(target=self.relogin_loop, daemon=True)
        self.relogin_thread.start()

        if self.logged_in:
            self.refresh_entry.configure(state="normal")
            self.refresh_button.configure(state="normal")
            self.schedule_auto_refresh()
            self.get_orders()

        # Ensure the window is sized to show all content
        try:
            self.root.update_idletasks()
            self.root.minsize(self.root.winfo_width(), self.root.winfo_height())
        except Exception:
            pass

    def login(self, silent: bool = False) -> None:
        username = self.username_var.get()
        password = self.password_var.get()
        login_url = self.login_url_var.get() or LOGIN_URL
        orders_url = self.orders_url_var.get() or ORDERS_URL
        credentials = {
            "username": username,
            "password": password,
            "login_url": login_url,
            "orders_url": orders_url,
        }

        def worker():
            try:
                result = service_login(self.session, credentials)
            except requests.RequestException as e:
                if not silent:
                    if hasattr(self, "root") and self.root:
                        self.root.after(0, lambda: messagebox.showerror("Login", f"Login request failed: {e}"))
                    else:
                        messagebox.showerror("Login", f"Login request failed: {e}")
                return
            if hasattr(self, "root") and self.root:
                self.root.after(0, lambda: self._handle_login_result(result, silent))
            else:
                self._handle_login_result(result, silent)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        if not hasattr(self, "root") or not self.root:
            thread.join()

    def _handle_login_result(self, result, silent=False):
        if result.get("success"):
            self.logged_in = True
            if not silent:
                messagebox.showinfo("Login", "Login successful!")
            try:
                self.tab_control.set("Date Range Report")
            except Exception:
                pass
            self.refresh_entry.configure(state="normal")
            self.refresh_button.configure(state="normal")
            self.schedule_auto_refresh()
        else:
            self.logged_in = False
            if not silent:
                messagebox.showerror("Login", "Login failed.")
        if self.logged_in:
            self.get_orders()

    def get_orders(self) -> None:
        if not self.logged_in:
            messagebox.showerror("Error", "Not logged in!")
            return
        orders_url = self.orders_url_var.get() or ORDERS_URL

        def worker():
            try:
                result = service_fetch_orders(self.session, orders_url=orders_url, queue_url=QUEUE_URL)
            except requests.RequestException as e:
                if hasattr(self, "root") and self.root:
                    self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to fetch orders: {e}"))
                else:
                    messagebox.showerror("Error", f"Failed to fetch orders: {e}")
                return
            # Process the queue page first so disappearing orders get logged
            # before we refresh the main orders table.  Both page processors
            # run on the Tkinter thread via ``root.after`` to avoid touching
            # the SQLite connection from this worker thread.
            if hasattr(self, "root") and self.root:
                self.root.after(0, lambda: self._process_queue_html(result["queue_html"]))
                self.root.after(0, lambda: self._process_orders_html(result["orders_html"]))
            else:
                try:
                    self._process_queue_html(result["queue_html"])
                except Exception:
                    pass  # _process_queue_html logs any parsing errors
                self._process_orders_html(result["orders_html"])

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        if not hasattr(self, "root") or not self.root:
            thread.join()

    def _process_orders_html(self, html: str) -> None:
        orders = parse_orders(html)
        self.orders_tree.delete(*self.orders_tree.get_children())
        self.order_rows = []
        for order in orders:
            steps = [JobStep(step.name, step.timestamp) for step in order.steps]
            self.log_order(order.number, order.company, steps)
            row = OrderRow(order.number, order.company, order.status, order.priority)
            self.order_rows.append(row)
            self.orders_tree.insert(
                '', 'end', values=(row.number, row.company, row.status, row.priority)
            )

    def _process_queue_html(self, html: str) -> None:
        """Parse the print-file queue page and record when jobs disappear."""
        try:
            current = parse_queue(html)
        except Exception:
            logger.exception("Error processing queue HTML")
            return
        disappeared = self.queue_orders - current
        for order in disappeared:
            self.record_print_file_start(order)
        self.queue_orders = current

    def record_print_file_start(self, order_number: str) -> None:
        db.record_print_file_start(self.db, self.db_lock, order_number)

    def log_order(self, order_number: str, company: str, steps: list[JobStep]) -> None:
        db_steps = [(s.name, s.timestamp) for s in steps]
        db.log_order(self.db, self.db_lock, order_number, company, db_steps)

    def load_steps(self, order_number: str) -> list[JobStep]:
        raw = db.load_steps(self.db, self.db_lock, order_number)
        return [JobStep(name, ts) for name, ts in raw]

    def load_lead_times(
        self,
        order_number: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        """Load precomputed lead times optionally filtered by date range."""
        return db.load_lead_times(
            self.db, self.db_lock, order_number, start_date, end_date
        )

    def open_analytics_window(self) -> None:
        """Create a pop-out window for analytics charts."""
        if self.analytics_window and self.analytics_window.winfo_exists():
            self.analytics_window.focus()
            return
        self.analytics_window = ctk.CTkToplevel(self.root)
        self.analytics_window.title("Analytics")
        self.analytics_job_var = ctk.StringVar()
        self.analytics_start_var = ctk.StringVar()
        self.analytics_end_var = ctk.StringVar()
        a_controls = ctk.CTkFrame(self.analytics_window)
        a_controls.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(a_controls, text="Job Filter:").pack(side="left", padx=5)
        ctk.CTkEntry(a_controls, textvariable=self.analytics_job_var, width=120).pack(side="left", padx=5)
        ctk.CTkLabel(a_controls, text="Start (YYYY-MM-DD):").pack(side="left", padx=5)
        ctk.CTkEntry(a_controls, textvariable=self.analytics_start_var, width=100).pack(side="left", padx=5)
        ctk.CTkLabel(a_controls, text="End (YYYY-MM-DD):").pack(side="left", padx=5)
        ctk.CTkEntry(a_controls, textvariable=self.analytics_end_var, width=100).pack(side="left", padx=5)
        ctk.CTkButton(
            a_controls, text="Update Chart", command=self.update_analytics_chart
        ).pack(side="left", padx=5)

        self.analytics_fig = Figure(figsize=(5, 4))
        self.analytics_ax = self.analytics_fig.add_subplot(111)
        self.analytics_canvas = FigureCanvasTkAgg(
            self.analytics_fig, master=self.analytics_window
        )
        self.analytics_canvas.get_tk_widget().pack(expand=1, fill="both")
        self.update_analytics_chart()

    def update_analytics_chart(self) -> None:
        """Compute lead times for visible orders and update the bar chart."""
        start = None
        end = None
        if self.analytics_start_var.get().strip():
            try:
                start = datetime.strptime(self.analytics_start_var.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Invalid start date format")
                return
        if self.analytics_end_var.get().strip():
            try:
                end = datetime.strptime(self.analytics_end_var.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Invalid end date format")
                return
        job_filter = self.analytics_job_var.get().strip()
        jobs: dict[str, list[tuple[str, Optional[datetime]]]] = {}
        for row in self.order_rows:
            order_number = row.number
            if job_filter and job_filter not in order_number:
                continue
            steps = self.load_steps(order_number)
            jobs[order_number] = [(s.name, s.timestamp) for s in steps]
        results = compute_lead_times(jobs, start, end)
        self.analytics_ax.clear()
        totals = []
        for job, steps in results.items():
            total = sum(s["hours"] for s in steps)
            totals.append((job, total))
        if totals:
            labels, hours = zip(*totals)
            indices = range(len(labels))
            self.analytics_ax.bar(indices, hours)
            self.analytics_ax.set_xticks(indices)
            self.analytics_ax.set_xticklabels(labels, rotation=90)
            self.analytics_ax.set_ylabel("Hours in queue")
            self.analytics_ax.set_xlabel("Job")
        self.analytics_canvas.draw()

    def apply_preset(self, preset: str) -> tuple[Optional[datetime], Optional[datetime]]:
        now = datetime.now()
        if preset == "today":
            s = e = now
        elif preset == "yesterday":
            y = now - timedelta(days=1)
            s = e = y
        elif preset == "last7":
            s = now - timedelta(days=6)
            e = now
        elif preset == "last30":
            s = now - timedelta(days=29)
            e = now
        elif preset == "thisMonth":
            s = datetime(now.year, now.month, 1)
            e = now
        elif preset == "lastMonth":
            first_this = datetime(now.year, now.month, 1)
            last_month_end = first_this - timedelta(days=1)
            s = datetime(last_month_end.year, last_month_end.month, 1)
            e = last_month_end
        else:  # custom
            return None, None
        self.start_date_var.set(s.strftime("%Y-%m-%d"))
        self.end_date_var.set(e.strftime("%Y-%m-%d"))
        return s, e

    def update_preset(self, label: str) -> None:
        preset = self.preset_labels[label]
        if preset == "custom":
            self.start_entry.configure(state="normal")
            self.end_entry.configure(state="normal")
        else:
            self.start_entry.configure(state="disabled")
            self.end_entry.configure(state="disabled")
            self.apply_preset(preset)
        self.save_current_range()

    def save_current_range(self, event: Any | None = None) -> None:
        label = self.preset_var.get()
        preset = self.preset_labels[label]
        self.config["last_range"] = {
            "preset": preset,
            "start": self.start_date_var.get(),
            "end": self.end_date_var.get(),
        }
        self.save_config()

    def get_date_range(
        self, start_var: Any | None = None, end_var: Any | None = None
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Return (start, end) datetimes from the entry fields or None."""
        start_var = start_var or self.start_date_var
        end_var = end_var or self.end_date_var
        start: Optional[datetime] = None
        end: Optional[datetime] = None
        if start_var.get().strip():
            try:
                start = datetime.strptime(start_var.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Invalid start date format")
        if end_var.get().strip():
            try:
                end = datetime.strptime(end_var.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Date", "Invalid end date format")
        if start and end and end < start:
            messagebox.showerror("Date", "End date must be after start date")
            return None, None
        return start, end

    def show_report(self, event: Any | None = None) -> None:
        selected = self.orders_tree.focus()
        if not selected:
            return
        order_number = self.orders_tree.item(selected, "values")[0]
        start, end = self.get_date_range()
        steps = self.load_steps(order_number)
        rows = self.load_lead_times(order_number, start, end)
        if not rows:
            tuple_steps = [(s.name, s.timestamp) for s in steps]
            rows = compute_lead_times({order_number: tuple_steps}, start, end).get(
                order_number, []
            )
            # store for future
            with self.db_lock:
                cur = self.db.cursor()
                for item in rows:
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
                self.db.commit()
        row_map = {r["workstation"]: r for r in rows}
        self.report_tree.delete(*self.report_tree.get_children())
        total = 0.0
        for idx, step in enumerate(steps):
            name = step.name
            ts = step.timestamp
            row = row_map.get(name)
            if row:
                start_ts = row["start"]
                end_ts = row["end"]
                hours = row["hours"]
            else:
                start_ts = steps[idx - 1].timestamp if idx > 0 else None
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

    def export_selected(self) -> None:
        self.export_report()

    def search_orders(self) -> None:
        term = self.search_var.get().lower()
        self.orders_tree.delete(*self.orders_tree.get_children())
        for row in self.order_rows:
            if not term or term in row.number.lower():
                self.orders_tree.insert(
                    '', 'end', values=(row.number, row.company, row.status, row.priority)
                )

    def export_report(self, event: Any | None = None) -> None:
        selected = self.orders_tree.focus()
        if not selected:
            return
        order_number = self.orders_tree.item(selected, "values")[0]
        start, end = self.get_date_range()
        rows = self.load_lead_times(order_number, start, end)
        if not rows:
            steps = self.load_steps(order_number)
            tuple_steps = [(s.name, s.timestamp) for s in steps]
            rows = compute_lead_times({order_number: tuple_steps}, start, end).get(
                order_number, []
            )
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

    def export_date_range(self) -> None:
        """Export a report for all jobs within the provided date range."""
        start, end = self.get_date_range()
        if not start and not end:
            messagebox.showerror("Export", "Enter a start or end date")
            return
        with self.db_lock:
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
        results: dict[str, list[dict[str, Any]]] = {}
        for order in orders:
            rows = self.load_lead_times(order, start, end)
            if not rows:
                steps = self.load_steps(order)
                tuple_steps = [(s.name, s.timestamp) for s in steps]
                rows = compute_lead_times({order: tuple_steps}, start, end).get(order, [])
            if rows:
                results[order] = rows
        if not results:
            messagebox.showinfo("Export", "No data for range")
            return
        s = start.strftime("%Y%m%d") if start else "begin"
        e = end.strftime("%Y%m%d") if end else "now"
        export_dir = self.export_path_var.get().strip() or os.getcwd()
        os.makedirs(export_dir, exist_ok=True)
        path = os.path.join(export_dir, f"lead_time_{s}_{e}.csv")
        write_report(results, path)
        messagebox.showinfo("Export", f"Report written to {path}")

    def export_realtime_report(self) -> None:
        """Export a realtime lead time report for the selected date range."""
        start, end = self.get_date_range()
        with self.db_lock:
            cur = self.db.cursor()
            cur.execute("SELECT DISTINCT order_number FROM steps")
            orders = [r[0] for r in cur.fetchall()]
        jobs = {
            order: [(s.name, s.timestamp) for s in self.load_steps(order)]
            for order in orders
        }
        report = generate_realtime_report(jobs, start, end)
        if not report:
            messagebox.showinfo("Export", "No data for range")
            return
        export_dir = self.export_path_var.get().strip() or os.getcwd()
        os.makedirs(export_dir, exist_ok=True)
        s = start.strftime("%Y%m%d") if start else "begin"
        e = end.strftime("%Y%m%d") if end else "now"
        csv_path = os.path.join(export_dir, f"realtime_{s}_{e}.csv")
        html_path = os.path.join(export_dir, f"realtime_{s}_{e}.html")
        write_realtime_report(report, csv_path, html_path)
        logger.info("Realtime report written to %s and %s", csv_path, html_path)
        messagebox.showinfo(
            "Export", f"Realtime report written to {csv_path} and {html_path}"
        )

    def schedule_auto_refresh(self) -> None:
        if not self.logged_in:
            self.next_refresh_time = None
            self.refresh_timer_var.set("")
            if self.refresh_timer_job is not None:
                try:
                    self.root.after_cancel(self.refresh_timer_job)
                except Exception:
                    pass
            return
        try:
            interval = int(self.refresh_interval_var.get())
        except (TypeError, ValueError):
            interval = 1
            self.refresh_interval_var.set(interval)
        interval_ms = max(1, interval) * 60 * 1000
        self.next_refresh_time = datetime.now() + timedelta(milliseconds=interval_ms)
        if self.auto_refresh_job is not None:
            try:
                self.root.after_cancel(self.auto_refresh_job)
            except Exception:
                pass
        if self.refresh_timer_job is not None:
            try:
                self.root.after_cancel(self.refresh_timer_job)
            except Exception:
                pass
        self.update_refresh_timer()
        self.auto_refresh_job = self.root.after(interval_ms, self.auto_refresh)

    def auto_refresh(self) -> None:
        if self.logged_in:
            self.refresh_timer_var.set("Refreshing...")
            self.get_orders()
        self.schedule_auto_refresh()

    def update_refresh_timer(self) -> None:
        if self.next_refresh_time is None:
            return
        remaining = self.next_refresh_time - datetime.now()
        if remaining.total_seconds() <= 0:
            self.refresh_timer_var.set("Refreshing...")
        else:
            minutes, seconds = divmod(int(remaining.total_seconds()), 60)
            self.refresh_timer_var.set(
                f"Next refresh in {minutes:02d}:{seconds:02d}"
            )
            self.refresh_timer_job = self.root.after(1000, self.update_refresh_timer)

    def schedule_daily_export(self) -> None:
        """Schedule the daily export based on configured time."""
        t_str = self.export_time_var.get().strip()
        if not t_str:
            return
        try:
            target_time = datetime.strptime(t_str, "%H:%M").time()
        except ValueError:
            return
        now = datetime.now()
        run_dt = datetime.combine(now.date(), target_time)
        if run_dt <= now:
            run_dt += timedelta(days=1)
        delay_ms = int((run_dt - now).total_seconds() * 1000)
        if self.export_job is not None:
            try:
                self.root.after_cancel(self.export_job)
            except Exception:
                pass
        self.export_job = self.root.after(delay_ms, self._run_scheduled_export)

    def _run_scheduled_export(self) -> None:
        self.export_date_range()
        self.schedule_daily_export()

    def load_config(self) -> dict[str, Any]:
        return load_config_file()

    def save_config(self) -> None:
        save_config_file(self.config)

    def update_business_hours(self) -> None:
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
        self.config["business_start"] = start.strftime("%H:%M")
        self.config["business_end"] = end.strftime("%H:%M")
        self.save_config()
        messagebox.showinfo("Business Hours", "Business hours updated")

    def update_export_settings(self) -> None:
        path = self.export_path_var.get().strip() or os.getcwd()
        t_str = self.export_time_var.get().strip()
        try:
            datetime.strptime(t_str, "%H:%M")
        except ValueError:
            messagebox.showerror("Export Settings", "Invalid time format")
            return
        self.config["export_path"] = path
        self.config["export_time"] = t_str
        self.save_config()
        messagebox.showinfo("Export Settings", "Export settings updated")
        self.schedule_daily_export()

    def browse_export_path(self) -> None:
        path = filedialog.askdirectory(initialdir=self.last_export_dir)
        if path:
            self.export_path_var.set(path)
            self.last_export_dir = path
            self.config["export_path"] = path
            self.save_config()


    @staticmethod
    def _sort_key(val):
        try:
            return float(val)
        except (ValueError, TypeError):
            return val

    # Date Range Report helpers
    def load_jobs_by_date_range(
        self, start: Optional[datetime], end: Optional[datetime]
    ) -> list[dict[str, Any]]:
        """Fetch jobs within start/end dates from the database."""
        return db.load_jobs_by_date_range(self.db, self.db_lock, start, end)

    def populate_date_range_table(self, rows: list[dict[str, Any]]) -> None:
        self.date_tree.delete(*self.date_tree.get_children())
        # Highlight orders that are still in progress
        self.date_tree.tag_configure("inprogress", background="#fff0e6")
        total = 0.0
        for idx, r in enumerate(rows):
            tags = ["even" if idx % 2 == 0 else "odd"]
            if r.get("status") == "In Progress":
                tags.append("inprogress")
            parent = self.date_tree.insert(
                "",
                "end",
                text=r["order"],
                values=(
                    r["company"],
                    "",
                    "",
                    "",
                    f"{r['hours']:.2f}",
                    r.get("status", ""),
                ),
                tags=tags,
                open=False,
            )
            for ws in r.get("workstations", []):
                self.date_tree.insert(
                    parent,
                    "end",
                    text="",
                    values=(
                        "",
                        ws["workstation"],
                        ws["start"],
                        ws["end"],
                        f"{ws['hours']:.2f}",
                        "",
                    ),
                )
            total += r["hours"]
        self.date_tree.insert(
            "",
            "end",
            text="TOTAL",
            values=("", "", "", "", f"{total:.2f}", ""),
            tags=("total",),
        )

    def toggle_order_row(self, event: Any) -> None:
        item = self.date_tree.identify_row(event.y)
        if not item:
            return
        if self.date_tree.get_children(item):
            is_open = self.date_tree.item(item, "open")
            self.date_tree.item(item, open=not is_open)

    def _set_all_date_rows_open(self, open_state):
        def recurse(item):
            self.date_tree.item(item, open=open_state)
            for child in self.date_tree.get_children(item):
                recurse(child)

        for child in self.date_tree.get_children():
            recurse(child)

    def expand_all_date_rows(self) -> None:
        self._set_all_date_rows_open(True)

    def collapse_all_date_rows(self) -> None:
        self._set_all_date_rows_open(False)

    def toggle_date_rows(self) -> None:
        if self.date_rows_expanded:
            self.collapse_all_date_rows()
            self.expand_collapse_btn.configure(text="Expand All")
        else:
            self.expand_all_date_rows()
            self.expand_collapse_btn.configure(text="Collapse All")
        self.date_rows_expanded = not self.date_rows_expanded

    def update_date_range_summary(self, rows: list[dict[str, Any]]) -> None:
        total_jobs = len({r["order"] for r in rows})
        total_hours = sum(r["hours"] for r in rows)
        self.range_total_jobs_var.set(str(total_jobs))
        self.range_total_hours_var.set(f"{total_hours:.2f}")

    def run_date_range_report(self) -> None:
        start, end = self.get_date_range(self.range_start_var, self.range_end_var)
        if not start or not end:
            messagebox.showerror("Date Range Report", "Start and end dates are required")
            return
        rows = self.load_jobs_by_date_range(start, end)
        raw_rows = list(rows)
        grouped: dict[str, dict[str, Any]] = {}
        for r in rows:
            order = str(r.get("order"))
            g = grouped.setdefault(
                order,
                {
                    "order": order,
                    "company": r.get("company", ""),
                    "hours": 0.0,
                    "workstations": [],
                    "status": "Completed",
                },
            )
            g["hours"] += r.get("hours") or 0.0
            end_time = r.get("end", "")
            g["workstations"].append(
                {
                    "workstation": r.get("workstation", ""),
                    "hours": r.get("hours") or 0.0,
                    "start": r.get("start", ""),
                    "end": end_time,
                }
            )
            if not end_time:
                g["status"] = "In Progress"

        # Include missing steps for each order and ensure workstation order
        for order, g in grouped.items():
            steps = self.load_steps(order)
            step_order = {s.name.lower(): idx for idx, s in enumerate(steps)}
            existing = {ws["workstation"].lower() for ws in g["workstations"]}
            prev_ts: Optional[datetime] = None
            for step in steps:
                step_name = step.name
                ts = step.timestamp
                step_lower = step_name.lower()
                end_str = ts.strftime("%Y-%m-%d %H:%M") if ts else ""
                if step_lower not in existing:
                    start_str = prev_ts.strftime("%Y-%m-%d %H:%M") if prev_ts else ""
                    delta = (
                        business_hours_delta(prev_ts, ts)
                        if prev_ts and ts
                        else timedelta(0)
                    )
                    hours = delta.total_seconds() / 3600
                    g["workstations"].append(
                        {
                            "workstation": step_name,
                            "hours": hours,
                            "start": start_str,
                            "end": end_str,
                        }
                    )
                    g["hours"] += hours
                    status = "Completed" if end_str else "In Progress"
                    raw_rows.append(
                        {
                            "order": order,
                            "company": g.get("company", ""),
                            "workstation": step_name,
                            "hours": hours,
                            "start": start_str,
                            "end": end_str,
                            "status": status,
                        }
                    )
                    existing.add(step_lower)
                if not end_str:
                    g["status"] = "In Progress"
                prev_ts = ts

            g["workstations"].sort(
                key=lambda ws: step_order.get(ws["workstation"].lower(), len(step_order))
            )

        grouped_rows = list(grouped.values())
        self.raw_date_range_rows = raw_rows
        self.date_range_rows = grouped_rows
        self.filtered_date_range_rows = list(grouped_rows)
        self.filtered_raw_date_range_rows = list(self.raw_date_range_rows)
        self.populate_date_range_table(grouped_rows)
        self.update_date_range_summary(self.filtered_raw_date_range_rows)

    def export_date_range_csv(self) -> None:
        """Export the date range report to a CSV file."""
        if not self.date_range_rows:
            messagebox.showerror("Date Range Report", "Run report before exporting")
            return
        start, end = self.get_date_range(self.range_start_var, self.range_end_var)
        s = start.strftime("%Y%m%d") if start else "begin"
        e = end.strftime("%Y%m%d") if end else "now"
        export_dir = self.export_path_var.get().strip() or os.getcwd()
        os.makedirs(export_dir, exist_ok=True)
        path = os.path.join(export_dir, f"date_range_{s}_{e}.csv")
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Order",
                "Company",
                "Workstation",
                "Start",
                "End",
                "Hours",
                "Status",
            ])
            for r in self.date_range_rows:
                writer.writerow([
                    r["order"],
                    r.get("company", ""),
                    "",
                    "",
                    "",
                    f"{r['hours']:.2f}",
                    r.get("status", ""),
                ])
                for ws in r.get("workstations", []):
                    writer.writerow([
                        "",
                        "",
                        ws.get("workstation", ""),
                        ws.get("start", ""),
                        ws.get("end", ""),
                        f"{ws['hours']:.2f}",
                        "",
                    ])
        messagebox.showinfo("Date Range Report", f"Report written to {path}")

    def filter_date_range_rows(self) -> None:
        term = self.date_range_filter_var.get().lower().strip()
        if not term:
            rows = self.date_range_rows
            raw_rows = self.raw_date_range_rows
        else:
            rows = [
                r
                for r in self.date_range_rows
                if term in str(r.get("order", "")).lower()
                or term in str(r.get("company", "")).lower()
            ]
            raw_rows = [
                r
                for r in self.raw_date_range_rows
                if term in str(r.get("order", "")).lower()
                or term in str(r.get("company", "")).lower()
            ]
        self.filtered_date_range_rows = rows
        self.filtered_raw_date_range_rows = raw_rows
        self.populate_date_range_table(rows)
        self.update_date_range_summary(raw_rows)

    def sort_date_range_table(self, column: str, reverse: bool = False) -> None:
        key_funcs = {
            "order": lambda r: r["order"],
            "company": lambda r: r["company"],
            "hours": lambda r: r["hours"],
        }
        if column not in key_funcs:
            return
        self.filtered_date_range_rows.sort(key=key_funcs[column], reverse=reverse)
        self.populate_date_range_table(self.filtered_date_range_rows)
        self.update_date_range_summary(self.filtered_raw_date_range_rows)
        if column == "order":
            self.date_tree.heading(
                "#0", command=lambda: self.sort_date_range_table(column, not reverse)
            )
        else:
            self.date_tree.heading(
                column, command=lambda: self.sort_date_range_table(column, not reverse)
            )

    def clear_date_range_report(self) -> None:
        self.range_start_var.set("")
        self.range_end_var.set("")
        self.date_range_rows = []
        self.filtered_date_range_rows = []
        self.raw_date_range_rows = []
        self.filtered_raw_date_range_rows = []
        self.date_range_filter_var.set("")
        self.date_tree.delete(*self.date_tree.get_children())
        self.update_date_range_summary([])

    def show_breakdown(self) -> None:
        selected = self.orders_tree.focus()
        if not selected:
            messagebox.showerror("Breakdown", "No order selected")
            return
        order_number = self.orders_tree.item(selected, "values")[0]
        start, end = self.get_date_range()
        steps = self.load_steps(order_number)
        lines: list[str] = []
        for current, next_step in zip(steps, steps[1:]):
            s = current.timestamp
            e = next_step.timestamp
            next_name = next_step.name
            if not s or not e:
                continue
            segments = business_hours_breakdown(s, e)
            if segments:
                lines.append(f"{next_name}:")
                for seg_start, seg_end in segments:
                    hours = (seg_end - seg_start).total_seconds() / 3600.0
                    lines.append(f"  {seg_start} -> {seg_end} ({hours:.2f}h)")
        messagebox.showinfo("Breakdown", "\n".join(lines) if lines else "No breakdown data")

    def browse_db(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("SQLite DB", "*.db"), ("All Files", "*")],
            initialdir=self.last_db_dir,
        )
        if path:
            self.connect_db(path)

    def connect_db(self, path: str) -> None:
        if hasattr(self, "db") and self.db:
            try:
                self.db.close()
            except Exception:
                pass
        self.db_path_var.set(path)
        self.config["db_path"] = path
        self.last_db_dir = os.path.dirname(path) or os.getcwd()
        self.save_config()
        self.db, self.db_lock = db.connect_db(path)

    def relogin_loop(self) -> None:
        while True:
            time.sleep(2*60*60)  # 2 hours
            if self.logged_in:
                print("Relogging in...")
                self.root.after(0, lambda: self.login(silent=True))

