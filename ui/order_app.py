from __future__ import annotations

import customtkinter as ctk
from tkinter import ttk, messagebox, filedialog
import threading
import requests  # type: ignore[import-untyped]
import os
from datetime import datetime, timedelta
import csv
import logging
from dataclasses import dataclass
from typing import Any, Optional
from tkcalendar import DateEntry

from config.settings import load_config as load_config_file, save_config as save_config_file
from data import db

from manage_html_report import (
    compute_lead_times,
    write_report,
)
import time_utils
from time_utils import business_hours_delta
from config.endpoints import ORDERS_URL

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class JobStep:
    """Representation of a single job step."""

    name: str
    timestamp: Optional[datetime]


class OrderScraperApp:
    def __init__(
        self,
        root: Any,
        session: Optional[requests.Session] = None,
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
        self.orders_url = orders_url

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

        # Tabs
        self.tab_control = ctk.CTkTabview(root)
        # date range report tab
        self.date_range_tab = self.tab_control.add("Date Range Report")
        # settings tab on far right
        self.settings_tab = self.tab_control.add("Settings")
        self.tab_control.pack(expand=1, fill="both")

        # Settings Tab
        ctk.CTkLabel(self.settings_tab, text="Database File:").grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.db_path_var).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Browse", command=self.browse_db).grid(row=0, column=2, padx=5, pady=5)

        ctk.CTkLabel(self.settings_tab, text="Business Start (HH:MM):").grid(row=1, column=0, padx=5, pady=5)
        self.business_start_var = ctk.StringVar(value=time_utils.BUSINESS_START.strftime("%H:%M"))
        ctk.CTkEntry(self.settings_tab, textvariable=self.business_start_var, width=80).grid(row=1, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Business End (HH:MM):").grid(row=2, column=0, padx=5, pady=5)
        self.business_end_var = ctk.StringVar(value=time_utils.BUSINESS_END.strftime("%H:%M"))
        ctk.CTkEntry(self.settings_tab, textvariable=self.business_end_var, width=80).grid(row=2, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Set Hours", command=self.update_business_hours).grid(row=3, column=0, columnspan=2, pady=10)

        ctk.CTkLabel(self.settings_tab, text="Export Path:").grid(row=4, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.export_path_var).grid(row=4, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Browse", command=self.browse_export_path).grid(row=4, column=2, padx=5, pady=5)

        ctk.CTkLabel(self.settings_tab, text="Export Time (HH:MM):").grid(row=5, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.export_time_var, width=80).grid(row=5, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Set Export", command=self.update_export_settings).grid(row=6, column=0, columnspan=2, pady=10)

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

        # Style to enlarge each row for better readability
        style = ttk.Style(self.root)
        # ``ttk`` style names require a component class suffix (e.g. ``Treeview``)
        # so give the custom style a ``.Treeview`` suffix.  Without it, Tk raises
        # ``Layout <style> not found`` when the style is referenced.
        style.configure("Date.Treeview", rowheight=28, padding=(0, 4))

        columns = (
            "company",
            "workstation",
            "start",
            "end",
            "hours",
            "status",
        )
        self.date_tree = ttk.Treeview(
            table_frame, columns=columns, show="tree headings", style="Date.Treeview"
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
        column_widths = {
            "company": 180,
            "workstation": 150,
            "start": 160,
            "end": 160,
            "hours": 80,
            "status": 120,
        }
        for col, head in zip(columns, headings):
            self.date_tree.heading(
                col,
                text=head,
                anchor="center",
                command=lambda c=col: self.sort_date_range_table(c),  # type: ignore[call-overload]
            )
            self.date_tree.column(
                col,
                anchor="center",
                width=column_widths.get(col, 100),
                stretch=True,
            )
        self.date_tree.pack(side="left", expand=1, fill="both")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.date_tree.yview)
        self.date_tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")

        self.date_tree.tag_configure("even", background="#f9f9f9")
        self.date_tree.tag_configure("odd", background="#ececec")
        self.date_tree.tag_configure(
            "total", background="#e0e0e0", font=("Arial", 10, "bold")
        )
        self.date_tree.tag_configure("inprogress", background="#fff0e6")
        self.date_tree.tag_configure("focus", background="#d0e0ff")
        self.hovered_item: Optional[str] = None
        self.date_tree.bind("<Double-1>", self.toggle_order_row)
        self.date_tree.bind("<Motion>", self.on_tree_hover)
        self.date_tree.bind("<Leave>", self.on_tree_leave)

        summary = ctk.CTkFrame(self.date_range_tab)
        summary.grid(row=3, column=0, columnspan=7, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(summary, text="Total Jobs:").grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkLabel(summary, textvariable=self.range_total_jobs_var).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(summary, text="Total Hours:").grid(row=0, column=2, padx=5, pady=5)
        ctk.CTkLabel(summary, textvariable=self.range_total_hours_var).grid(row=0, column=3, padx=5, pady=5)

        self.refresh_seconds_var = ctk.StringVar(value="")
        self.refresh_label = ctk.CTkLabel(
            root, textvariable=self.refresh_seconds_var
        )
        self.refresh_label.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)

        self.scrape_interval = 60
        self.scrape_job: Optional[str] = None
        self.countdown_job: Optional[str] = None
        self.next_scrape_time: Optional[datetime] = None
        self.schedule_order_scrape()

        self.schedule_daily_export()

        # Ensure the window is sized to show all content
        try:
            self.root.update_idletasks()
            self.root.minsize(self.root.winfo_width(), self.root.winfo_height())
        except Exception:
            pass

    def schedule_order_scrape(self, interval: Optional[int] = None) -> None:
        if interval is not None:
            self.scrape_interval = interval
        if self.scrape_job is not None:
            try:
                self.root.after_cancel(self.scrape_job)
            except Exception:
                pass
        if self.countdown_job is not None:
            try:
                self.root.after_cancel(self.countdown_job)
            except Exception:
                pass
        self.next_scrape_time = datetime.now() + timedelta(seconds=self.scrape_interval)
        self.scrape_job = self.root.after(
            int(self.scrape_interval * 1000), self.refresh_orders
        )
        self._update_refresh_timer()

    def _update_refresh_timer(self) -> None:
        if not self.next_scrape_time:
            return
        remaining = int((self.next_scrape_time - datetime.now()).total_seconds())
        if remaining < 0:
            remaining = 0
        self.refresh_seconds_var.set(f"Refresh in {remaining}s")
        self.countdown_job = self.root.after(1000, self._update_refresh_timer)

    def refresh_orders(self) -> None:
        """Refresh the orders and reschedule the next scrape."""
        # Placeholder for actual scraping logic
        self.schedule_order_scrape()

    def manual_refresh(self) -> None:
        if self.scrape_job is not None:
            try:
                self.root.after_cancel(self.scrape_job)
            except Exception:
                pass
        self.refresh_orders()

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


    def get_date_range(
        self, start_var: Any | None = None, end_var: Any | None = None
    ) -> tuple[Optional[datetime], Optional[datetime]]:
        """Return (start, end) datetimes from the entry fields or None."""
        start_var = start_var or self.range_start_var
        end_var = end_var or self.range_end_var
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

    def on_tree_hover(self, event: Any) -> None:
        item = self.date_tree.identify_row(event.y)
        if item != self.hovered_item:
            if self.hovered_item:
                tags = set(self.date_tree.item(self.hovered_item, "tags"))
                tags.discard("focus")
                self.date_tree.item(self.hovered_item, tags=tuple(tags))
            if item:
                tags = set(self.date_tree.item(item, "tags"))
                tags.add("focus")
                self.date_tree.item(item, tags=tuple(tags))
            self.hovered_item = item

    def on_tree_leave(self, event: Any) -> None:
        if self.hovered_item:
            tags = set(self.date_tree.item(self.hovered_item, "tags"))
            tags.discard("focus")
            self.date_tree.item(self.hovered_item, tags=tuple(tags))
            self.hovered_item = None

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

