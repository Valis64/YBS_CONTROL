import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
import requests
import os
import sqlite3
import threading

from ui.order_app import OrderScraperApp
from login_dialog import LoginDialog
from datetime import datetime, time
import time_utils


class SimpleVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class LoginDialogTests(unittest.TestCase):
    def setUp(self):
        self.dialog = LoginDialog.__new__(LoginDialog)
        self.dialog.session = MagicMock()
        self.dialog.username_var = SimpleVar("user")
        self.dialog.password_var = SimpleVar("pass")
        self.dialog.login_url_var = SimpleVar("http://example.com/login")
        self.dialog.orders_url_var = SimpleVar("http://example.com/orders")

    @patch("login_dialog.messagebox")
    def test_login_request_exception(self, mock_messagebox):
        self.dialog.session.post.side_effect = requests.Timeout("boom")
        self.dialog.login()
        self.dialog.session.post.assert_called_with(
            "http://example.com/login",
            data={"email": "user", "password": "pass", "action": "signin"},
            timeout=10,
        )
        mock_messagebox.showerror.assert_called_once()

    @patch("login_dialog.messagebox")
    def test_login_request_exception_silent(self, mock_messagebox):
        self.dialog.session.post.side_effect = requests.Timeout("boom")
        self.dialog.login(silent=True)
        mock_messagebox.showerror.assert_not_called()


class YBSControlTests(unittest.TestCase):
    def setUp(self):
        self.app = OrderScraperApp.__new__(OrderScraperApp)
        self.app.session = MagicMock()
        self.app.username_var = SimpleVar("user")
        self.app.password_var = SimpleVar("pass")
        self.app.login_url_var = SimpleVar("http://example.com/login")
        self.app.orders_url_var = SimpleVar("http://example.com/orders")
        self.app.tab_control = MagicMock()
        self.app.logged_in = True
        self.app.orders_tree = MagicMock()
        self.app.orders_tree.get_children.return_value = []
        self.app.log_order = MagicMock()
        self.app.order_rows = []
        self.app.config = {}
        self.app.save_config = MagicMock()
        self.app.last_db_dir = ""
        self.app.export_path_var = SimpleVar("/tmp")
        self.app.export_time_var = SimpleVar("")
        self.app.export_job = None
        self.app.queue_orders = set()
        self.app.db_lock = threading.Lock()
        # bind methods added after object creation
        self.app._run_scheduled_export = OrderScraperApp._run_scheduled_export.__get__(self.app)
        # date range report setup
        self.app.range_start_var = SimpleVar("")
        self.app.range_end_var = SimpleVar("")
        self.app.range_total_jobs_var = SimpleVar("")
        self.app.range_total_hours_var = SimpleVar("")
        self.app.date_tree = MagicMock()
        self.app.date_tree.get_children.return_value = []
        self.app.date_range_filter_var = SimpleVar("")
        self.app.filtered_raw_date_range_rows = []
        self.app.run_date_range_report = OrderScraperApp.run_date_range_report.__get__(self.app)
        self.app.populate_date_range_table = OrderScraperApp.populate_date_range_table.__get__(self.app)
        self.app.update_date_range_summary = OrderScraperApp.update_date_range_summary.__get__(self.app)
        self.app.sort_date_range_table = OrderScraperApp.sort_date_range_table.__get__(self.app)
        self.app.filter_date_range_rows = OrderScraperApp.filter_date_range_rows.__get__(self.app)
        self.app.clear_date_range_report = OrderScraperApp.clear_date_range_report.__get__(self.app)
        self.app.export_realtime_report = OrderScraperApp.export_realtime_report.__get__(self.app)
        self.app.toggle_order_row = OrderScraperApp.toggle_order_row.__get__(self.app)
        self.app.load_jobs_by_date_range = OrderScraperApp.load_jobs_by_date_range.__get__(self.app)
        self.app._process_queue_html = OrderScraperApp._process_queue_html.__get__(self.app)
        self.app.record_print_file_start = OrderScraperApp.record_print_file_start.__get__(self.app)

    @patch("ui.order_app.messagebox")
    def test_get_orders_request_exception(self, mock_messagebox):
        self.app.session.get.side_effect = requests.RequestException("fail")
        self.app.get_orders()
        self.app.session.get.assert_called_with("http://example.com/orders", timeout=10)
        mock_messagebox.showerror.assert_called_once()
        self.app.orders_tree.delete.assert_not_called()

    def test_process_queue_html_records_disappearance(self):
        # Setup in-memory database for steps
        self.app.db = sqlite3.connect(":memory:")
        cur = self.app.db.cursor()
        cur.execute(
            "CREATE TABLE steps (order_number TEXT, step TEXT, timestamp TEXT)"
        )
        self.app.queue_orders = {"100"}
        html_initial = "<table><tbody><tr><td>100</td></tr></tbody></table>"
        self.app._process_queue_html(html_initial)
        # Order 100 disappears on next fetch
        html_empty = "<table><tbody></tbody></table>"
        self.app._process_queue_html(html_empty)
        cur.execute(
            "SELECT step, timestamp FROM steps WHERE order_number='100'"
        )
        row = cur.fetchone()
        self.assertEqual(row[0], "Print File")
        self.assertTrue(row[1])

    def test_process_queue_html_logs_error_on_malformed_html(self):
        with patch("ui.order_app.BeautifulSoup", side_effect=ValueError("boom")):
            with self.assertLogs("ui.order_app", level="ERROR") as cm:
                self.app._process_queue_html("<bad>")
        self.assertTrue(any("Error processing queue HTML" in msg for msg in cm.output))

    @patch("ui.order_app.messagebox")
    def test_parse_company_and_order_from_same_cell(self, mock_messagebox):
        html = (
            "<table><tbody id='table'>"
            "<tr>"
            "<td>ACME Corp<br>Order #12345<ul class='workplaces'></ul></td>"
            "<td></td>"
            "<td>Running</td>"
            "<td></td>"
            "<td><input value='High'/></td>"
            "</tr>"
            "</tbody></table>"
        )
        mock_response = MagicMock()
        mock_response.text = html
        self.app.session.get.return_value = mock_response
        self.app.get_orders()
        self.app.orders_tree.insert.assert_called_once()
        args, kwargs = self.app.orders_tree.insert.call_args
        self.assertEqual(kwargs["values"], ("12345", "ACME Corp", "Running", "High"))

    @patch("ui.order_app.messagebox")
    def test_parse_company_and_order_from_separate_cells(self, mock_messagebox):
        html = (
            "<table><tbody id='table'>"
            "<tr>"
            "<td>YBS 35264<ul class='workplaces'></ul></td>"
            "<td class='details cboxElement'><p>Velocity Production and Packaging</p><p>Hydration Heroes Mini Kit</p></td>"
            "<td></td>"
            "<td></td>"
            "<td><input value=''/></td>"
            "</tr>"
            "</tbody></table>"
        )
        mock_response = MagicMock()
        mock_response.text = html
        self.app.session.get.return_value = mock_response
        self.app.get_orders()
        self.app.orders_tree.insert.assert_called_once()
        args, kwargs = self.app.orders_tree.insert.call_args
        self.assertEqual(
            kwargs["values"],
            ("35264", "Velocity Production and Packaging", "", ""),
        )

    @patch("ui.order_app.messagebox")
    def test_parse_company_skips_placeholder_in_first_cell(self, mock_messagebox):
        html = (
            "<table><tbody id='table'>"
            "<tr>"
            "<td>YBS 35264<p>?</p><ul class='workplaces'></ul></td>"
            "<td class='details cboxElement'><p>Velocity Production and Packaging</p><p>Hydration Heroes Mini Kit</p></td>"
            "<td></td>"
            "<td></td>"
            "<td><input value=''/></td>"
            "</tr>"
            "</tbody></table>"
        )
        mock_response = MagicMock()
        mock_response.text = html
        self.app.session.get.return_value = mock_response
        self.app.get_orders()
        self.app.orders_tree.insert.assert_called_once()
        args, kwargs = self.app.orders_tree.insert.call_args
        self.assertEqual(
            kwargs["values"],
            ("35264", "Velocity Production and Packaging", "", ""),
        )

    def test_show_report_displays_all_workstations(self):
        self.app.start_date_var = SimpleVar("")
        self.app.end_date_var = SimpleVar("")
        # simulate order selection
        self.app.orders_tree.focus.return_value = "item1"
        self.app.orders_tree.item.return_value = ("123",)
        # steps contain a workstation without a timestamp
        t1 = datetime(2024, 1, 1, 8, 0)
        self.app.load_steps = MagicMock(return_value=[("Cutting", t1), ("Welding", None)])
        self.app.load_lead_times = MagicMock(return_value=[])
        self.app.report_tree = MagicMock()
        db_cursor = MagicMock()
        db_cursor.fetchall.return_value = []
        self.app.db = MagicMock()
        self.app.db.cursor.return_value = db_cursor

        self.app.show_report()

        insert_calls = self.app.report_tree.insert.call_args_list
        # Cutting, Welding, TOTAL
        self.assertEqual(len(insert_calls), 3)
        self.assertEqual(insert_calls[0].kwargs["values"][0], "Cutting")
        self.assertEqual(insert_calls[1].kwargs["values"][0], "Welding")

    @patch("ui.order_app.messagebox")
    def test_get_date_range_invalid_order(self, mock_messagebox):
        self.app.start_date_var = SimpleVar("2024-01-02")
        self.app.end_date_var = SimpleVar("2024-01-01")
        start, end = OrderScraperApp.get_date_range(self.app)
        self.assertIsNone(start)
        self.assertIsNone(end)
        mock_messagebox.showerror.assert_called_once()

    @patch("data.db.sqlite3.connect")
    def test_connect_db_allows_network_path(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        self.app.db_path_var = SimpleVar("orders.db")
        self.app.db = MagicMock()
        OrderScraperApp.connect_db(self.app, r"\\server\share\orders.db")
        mock_connect.assert_called_with(r"\\server\share\orders.db", check_same_thread=False)
        self.assertEqual(self.app.config["db_path"], r"\\server\share\orders.db")
        expected_dir = os.path.dirname(r"\\server\share\orders.db") or os.getcwd()
        self.assertEqual(self.app.last_db_dir, expected_dir)
        self.app.save_config.assert_called_once()

    @patch("ui.order_app.messagebox")
    def test_update_business_hours_valid(self, mock_messagebox):
        self.app.business_start_var = SimpleVar("09:00")
        self.app.business_end_var = SimpleVar("17:00")
        self.app.save_config = MagicMock()
        self.app.config = {}
        OrderScraperApp.update_business_hours(self.app)
        self.assertEqual(time_utils.BUSINESS_START, time(9, 0))
        self.assertEqual(time_utils.BUSINESS_END, time(17, 0))
        self.assertEqual(self.app.config["business_start"], "09:00")
        self.assertEqual(self.app.config["business_end"], "17:00")
        self.app.save_config.assert_called_once()
        mock_messagebox.showinfo.assert_called_once()
        # reset defaults
        time_utils.BUSINESS_START = time(8, 0)
        time_utils.BUSINESS_END = time(16, 30)

    @patch("ui.order_app.compute_lead_times")
    def test_update_analytics_chart_calls_compute(self, mock_compute):
        self.app.analytics_ax = MagicMock()
        self.app.analytics_canvas = MagicMock()
        self.app.analytics_start_var = SimpleVar("")
        self.app.analytics_end_var = SimpleVar("")
        self.app.analytics_job_var = SimpleVar("")
        self.app.order_rows = [("123", "ACME", "Running", "High")]
        self.app.load_steps = MagicMock(return_value=[("Cutting", datetime(2024, 1, 1, 8, 0)), ("Welding", datetime(2024, 1, 1, 12, 0))])
        mock_compute.return_value = {"123": [{"hours": 4, "workstation": "Welding"}]}
        OrderScraperApp.update_analytics_chart(self.app)
        mock_compute.assert_called_once()
        self.app.analytics_ax.bar.assert_called_once()
        self.app.analytics_canvas.draw.assert_called_once()

    @patch("ui.order_app.threading.Thread")
    @patch("ui.order_app.OrderScraperApp.connect_db")
    @patch("ui.order_app.OrderScraperApp.load_config", return_value={"business_start": "09:00", "business_end": "17:00", "db_path": "orders.db"})
    @patch("ui.order_app.ttk.Style")
    @patch("ui.order_app.ttk.Scrollbar")
    @patch("ui.order_app.ttk.Treeview")
    @patch("ui.order_app.FigureCanvasTkAgg")
    @patch("ui.order_app.Figure")
    @patch("ui.order_app.ctk.CTkFrame")
    @patch("ui.order_app.ctk.CTkButton")
    @patch("ui.order_app.ctk.CTkEntry")
    @patch("ui.order_app.ctk.CTkLabel")
    @patch("ui.order_app.ctk.CTkTabview")
    @patch("ui.order_app.ctk.IntVar", side_effect=lambda value=0: SimpleVar(value))
    @patch("ui.order_app.ctk.StringVar", side_effect=lambda value="": SimpleVar(value))
    def test_init_uses_config_business_hours(
        self,
        mock_stringvar,
        mock_intvar,
        mock_tabview,
        mock_label,
        mock_entry,
        mock_button,
        mock_frame,
        mock_figure,
        mock_canvas,
        mock_treeview,
        mock_scrollbar,
        mock_style,
        mock_load_config,
        mock_connect_db,
        mock_thread,
    ):
        mock_thread.return_value = MagicMock(start=MagicMock())
        root = MagicMock()
        app = OrderScraperApp(root, session=MagicMock())
        self.assertEqual(app.business_start_var.get(), "09:00")
        self.assertEqual(app.business_end_var.get(), "17:00")
        self.assertEqual(time_utils.BUSINESS_START, time(9, 0))
        self.assertEqual(time_utils.BUSINESS_END, time(17, 0))
        tabs_added = [call.args[0] for call in mock_tabview.return_value.add.call_args_list]
        self.assertNotIn("Analytics", tabs_added)
        # reset defaults
        time_utils.BUSINESS_START = time(8, 0)
        time_utils.BUSINESS_END = time(16, 30)

    @patch("ui.order_app.filedialog.askopenfilename", return_value="/tmp/orders.db")
    def test_browse_db_uses_last_directory(self, mock_dialog):
        self.app.last_db_dir = "/tmp"
        self.app.connect_db = MagicMock()
        OrderScraperApp.browse_db(self.app)
        mock_dialog.assert_called_once()
        args, kwargs = mock_dialog.call_args
        self.assertEqual(kwargs.get("initialdir"), "/tmp")
        self.app.connect_db.assert_called_with("/tmp/orders.db")

    @patch("ui.order_app.filedialog.askdirectory", return_value="/exports")
    def test_browse_export_path_uses_last_directory(self, mock_dialog):
        self.app.last_export_dir = "/tmp"
        self.app.export_path_var = SimpleVar("")
        self.app.config = {}
        OrderScraperApp.browse_export_path(self.app)
        mock_dialog.assert_called_once()
        args, kwargs = mock_dialog.call_args
        self.assertEqual(kwargs.get("initialdir"), "/tmp")
        self.assertEqual(self.app.export_path_var.get(), "/exports")
        self.assertEqual(self.app.last_export_dir, "/exports")
        self.assertEqual(self.app.config["export_path"], "/exports")
        self.app.save_config.assert_called_once()

    @patch("ui.order_app.messagebox")
    def test_handle_login_response_triggers_get_orders_only_on_success(self, mock_messagebox):
        self.app.get_orders = MagicMock()
        self.app.refresh_entry = MagicMock()
        self.app.refresh_button = MagicMock()
        self.app.schedule_auto_refresh = MagicMock()
        mock_resp = MagicMock()

        # simulate login failure
        mock_resp.text = "login failed"
        self.app._handle_login_response(mock_resp)
        self.app.get_orders.assert_not_called()

        # simulate login success
        mock_resp.text = "logout"
        self.app._handle_login_response(mock_resp)
        self.app.get_orders.assert_called_once()

    @patch("ui.order_app.messagebox")
    def test_handle_login_response_silent(self, mock_messagebox):
        self.app.get_orders = MagicMock()
        self.app.refresh_entry = MagicMock()
        self.app.refresh_button = MagicMock()
        self.app.schedule_auto_refresh = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "logout"
        self.app._handle_login_response(mock_resp, silent=True)
        mock_messagebox.showinfo.assert_not_called()
        self.app.get_orders.assert_called_once()

    def test_schedule_daily_export_invokes_export(self):
        self.app.root = MagicMock()
        callbacks = {}

        def fake_after(delay, func):
            callbacks['func'] = func
            return 'job'

        self.app.root.after = MagicMock(side_effect=fake_after)
        self.app.root.after_cancel = MagicMock()
        self.app.export_date_range = MagicMock()
        self.app.export_time_var = SimpleVar("00:00")
        OrderScraperApp.schedule_daily_export(self.app)
        self.assertIn('func', callbacks)
        callbacks['func']()
        self.app.export_date_range.assert_called_once()

    @patch("ui.order_app.write_realtime_report")
    @patch("ui.order_app.generate_realtime_report", return_value=[("123", "Cut", datetime(2024, 1, 1, 8, 0), datetime(2024, 1, 1, 9, 0), 1.0)])
    @patch("ui.order_app.messagebox")
    def test_export_realtime_report(self, mock_messagebox, mock_generate, mock_write):
        self.app.start_date_var = SimpleVar("")
        self.app.end_date_var = SimpleVar("")
        cursor = MagicMock()
        cursor.fetchall.return_value = [("123",)]
        self.app.db = MagicMock()
        self.app.db.cursor.return_value = cursor
        self.app.load_steps = MagicMock(return_value=[])
        self.app.export_realtime_report()
        mock_generate.assert_called_once()
        mock_write.assert_called_once()
        mock_messagebox.showinfo.assert_called()



    @patch("ui.order_app.messagebox")
    def test_run_date_range_report_populates_table_and_summary(self, mock_messagebox):
        self.app.range_start_var = SimpleVar("2024-01-01")
        self.app.range_end_var = SimpleVar("2024-01-02")
        rows = [
            {
                "order": "1",
                "company": "A",
                "workstation": "WS1",
                "hours": 2.0,
                "start": "2024-01-01",
                "end": "2024-01-01",
            },
            {
                "order": "2",
                "company": "B",
                "workstation": "WS2",
                "hours": 3.0,
                "start": "2024-01-02",
                "end": "",
            },
        ]
        self.app.load_jobs_by_date_range = MagicMock(return_value=rows)
        self.app.load_steps = MagicMock(return_value=[])
        self.app.run_date_range_report()
        insert_calls = self.app.date_tree.insert.call_args_list
        self.assertEqual(len(insert_calls), 5)

        # parent row for order 1
        self.assertEqual(insert_calls[0].kwargs["text"], "1")
        self.assertFalse(insert_calls[0].kwargs["open"])
        self.assertEqual(
            insert_calls[0].kwargs["values"],
            ("A", "", "", "", "2.00", "Completed"),
        )

        # child row for order 1
        self.assertEqual(
            insert_calls[1].kwargs["values"],
            ("", "WS1", "2024-01-01", "2024-01-01", "2.00", ""),
        )

        # parent row for order 2 (in progress)
        self.assertEqual(insert_calls[2].kwargs["text"], "2")
        self.assertFalse(insert_calls[2].kwargs["open"])
        self.assertEqual(
            insert_calls[2].kwargs["values"],
            ("B", "", "", "", "3.00", "In Progress"),
        )
        self.assertIn("inprogress", insert_calls[2].kwargs["tags"])

        # child row for order 2
        self.assertEqual(
            insert_calls[3].kwargs["values"],
            ("", "WS2", "2024-01-02", "", "3.00", ""),
        )

        # total row
        self.assertEqual(insert_calls[4].kwargs["text"], "TOTAL")
        self.assertEqual(
            insert_calls[4].kwargs["values"],
            ("", "", "", "", "5.00", ""),
        )

        # tag configured for in-progress orders
        self.app.date_tree.tag_configure.assert_any_call("inprogress", background="#fff0e6")
        self.assertEqual(self.app.range_total_jobs_var.get(), "2")
        self.assertEqual(self.app.range_total_hours_var.get(), "5.00")

    def test_load_jobs_by_date_range_includes_time(self):
        self.app.db = sqlite3.connect(":memory:")
        cur = self.app.db.cursor()
        cur.execute(
            "CREATE TABLE lead_times (order_number TEXT, workstation TEXT, start TEXT, end TEXT, hours REAL)"
        )
        cur.execute(
            "CREATE TABLE orders (order_number TEXT, company TEXT)"
        )
        cur.execute(
            "INSERT INTO lead_times VALUES ('1','Print','2024-01-01 10:30:00','2024-01-01 11:45:00',1.25)"
        )
        rows = self.app.load_jobs_by_date_range(
            datetime(2024, 1, 1), datetime(2024, 1, 2)
        )
        self.assertEqual(rows[0]["start"], "2024-01-01 10:30")
        self.assertEqual(rows[0]["end"], "2024-01-01 11:45")

    def test_run_date_range_report_groups_orders_with_workstations(self):
        self.app.range_start_var = SimpleVar("2024-01-01")
        self.app.range_end_var = SimpleVar("2024-01-02")
        rows = [
            {
                "order": "1",
                "company": "A",
                "workstation": "WS1",
                "hours": 1.0,
                "start": "2024-01-01",
                "end": "2024-01-01",
            },
            {
                "order": "1",
                "company": "A",
                "workstation": "WS2",
                "hours": 2.0,
                "start": "2024-01-01",
                "end": "2024-01-02",
            },
        ]
        self.app.load_jobs_by_date_range = MagicMock(return_value=rows)
        self.app.load_steps = MagicMock(return_value=[])
        self.app.populate_date_range_table = MagicMock()
        self.app.update_date_range_summary = MagicMock()
        self.app.run_date_range_report()
        self.app.populate_date_range_table.assert_called_once()
        grouped_rows = self.app.populate_date_range_table.call_args[0][0]
        self.assertEqual(len(grouped_rows), 1)
        grouped = grouped_rows[0]
        self.assertEqual(grouped["order"], "1")
        self.assertEqual(grouped["hours"], 3.0)
        self.assertEqual(len(grouped["workstations"]), 2)
        self.assertEqual(
            [ws["workstation"] for ws in grouped["workstations"]],
            ["WS1", "WS2"],
        )

    @patch("ui.order_app.messagebox")
    def test_run_date_range_report_adds_missing_steps_and_sets_in_progress(self, mock_messagebox):
        self.app.range_start_var = SimpleVar("2024-01-01")
        self.app.range_end_var = SimpleVar("2024-01-03")
        rows = [
            {
                "order": "1",
                "company": "A",
                "workstation": "Cutting",
                "hours": 1.0,
                "start": "2024-01-01",
                "end": "2024-01-02",
            }
        ]
        self.app.load_jobs_by_date_range = MagicMock(return_value=rows)
        t1 = datetime(2024, 1, 1)
        t2 = datetime(2024, 1, 2)
        steps = [("Print File", t1), ("Cutting", t2), ("Shipping", None)]
        self.app.load_steps = MagicMock(return_value=steps)
        self.app.run_date_range_report()
        insert_calls = self.app.date_tree.insert.call_args_list
        values_list = [call.kwargs["values"] for call in insert_calls]
        self.assertIn(("", "Print File", "", "2024-01-01", "0.00", ""), values_list)
        self.assertIn(("", "Shipping", "2024-01-02", "", "0.00", ""), values_list)
        self.assertEqual(
            insert_calls[0].kwargs["values"],
            ("A", "", "", "", "1.00", "In Progress"),
        )

    def test_run_date_range_report_orders_workstations_like_steps(self):
        self.app.range_start_var = SimpleVar("2024-01-01")
        self.app.range_end_var = SimpleVar("2024-01-03")
        rows = [
            {
                "order": "1",
                "company": "A",
                "workstation": "Shipping",
                "hours": 1.0,
                "start": "2024-01-02",
                "end": "2024-01-02",
            },
            {
                "order": "1",
                "company": "A",
                "workstation": "Cutting",
                "hours": 2.0,
                "start": "2024-01-01",
                "end": "2024-01-01",
            },
        ]
        self.app.load_jobs_by_date_range = MagicMock(return_value=rows)
        t1 = datetime(2024, 1, 1)
        t2 = datetime(2024, 1, 2)
        steps = [("Print Files YBS", t1), ("Cutting", t2), ("Shipping", None)]
        self.app.load_steps = MagicMock(return_value=steps)
        self.app.populate_date_range_table = MagicMock()
        self.app.update_date_range_summary = MagicMock()
        self.app.run_date_range_report()
        grouped_rows = self.app.populate_date_range_table.call_args[0][0]
        ws_names = [ws["workstation"] for ws in grouped_rows[0]["workstations"]]
        self.assertEqual(ws_names, ["Print Files YBS", "Cutting", "Shipping"])

    def test_populate_date_range_table_inserts_parent_and_child_rows(self):
        rows = [
            {
                "order": "1",
                "company": "Cust",
                "hours": 3.0,
                "status": "Completed",
                "workstations": [
                    {
                        "workstation": "WS1",
                        "start": "2024-01-01",
                        "end": "2024-01-01",
                        "hours": 1.0,
                    },
                    {
                        "workstation": "WS2",
                        "start": "2024-01-02",
                        "end": "2024-01-02",
                        "hours": 2.0,
                    },
                ],
            }
        ]
        self.app.date_tree.insert = MagicMock(
            side_effect=["p1", "c1", "c2", "t"]
        )
        self.app.populate_date_range_table(rows)
        calls = self.app.date_tree.insert.call_args_list
        self.assertEqual(calls[0].args[0], "")
        self.assertEqual(calls[0].kwargs["text"], "1")
        self.assertEqual(
            calls[0].kwargs["values"],
            ("Cust", "", "", "", "3.00", "Completed"),
        )
        self.assertEqual(calls[1].args[0], "p1")
        self.assertEqual(
            calls[1].kwargs["values"],
            ("", "WS1", "2024-01-01", "2024-01-01", "1.00", ""),
        )
        self.assertEqual(calls[2].args[0], "p1")
        self.assertEqual(
            calls[2].kwargs["values"],
            ("", "WS2", "2024-01-02", "2024-01-02", "2.00", ""),
        )
        self.assertEqual(calls[3].args[0], "")
        self.assertEqual(calls[3].kwargs["text"], "TOTAL")

    @patch("ui.order_app.messagebox")
    def test_filter_date_range_rows_and_sorting(self, mock_messagebox):
        self.app.range_start_var = SimpleVar("2024-01-01")
        self.app.range_end_var = SimpleVar("2024-01-03")
        rows = [
            {
                "order": "1",
                "company": "Alpha",
                "workstation": "WS1",
                "hours": 1.0,
                "start": "2024-01-01",
                "end": "2024-01-01",
            },
            {
                "order": "2",
                "company": "Beta",
                "workstation": "WS2",
                "hours": 2.0,
                "start": "2024-01-02",
                "end": "2024-01-02",
            },
            {
                "order": "3",
                "company": "AlphaBeta",
                "workstation": "WS3",
                "hours": 3.0,
                "start": "2024-01-03",
                "end": "2024-01-03",
            },
        ]
        self.app.load_jobs_by_date_range = MagicMock(return_value=rows)
        self.app.load_steps = MagicMock(return_value=[])
        self.app.run_date_range_report()
        self.app.date_tree.insert.reset_mock()
        self.app.date_range_filter_var.set("beta")
        self.app.filter_date_range_rows()
        insert_calls = self.app.date_tree.insert.call_args_list
        self.assertEqual(len(insert_calls), 5)
        self.assertEqual(insert_calls[0].kwargs["text"], "2")
        self.assertEqual([r["order"] for r in self.app.filtered_date_range_rows], ["2", "3"])
        self.app.date_tree.insert.reset_mock()
        self.app.sort_date_range_table("order", reverse=True)
        insert_calls = self.app.date_tree.insert.call_args_list
        self.assertEqual(insert_calls[0].kwargs["text"], "3")
        self.assertEqual([r["order"] for r in self.app.filtered_date_range_rows], ["3", "2"])

    def test_toggle_order_row_double_click(self):
        tree = MagicMock()
        self.app.date_tree = tree
        event = SimpleNamespace(y=10)
        tree.identify_row.return_value = "order1"
        tree.get_children.return_value = ["child1"]
        state = {"open": True}

        def item_side_effect(item, option=None, **kw):
            if option is not None:
                return state[option]
            if "open" in kw:
                state["open"] = kw["open"]

        tree.item.side_effect = item_side_effect
        self.app.toggle_order_row(event)
        self.assertFalse(state["open"])
        self.app.toggle_order_row(event)
        self.assertTrue(state["open"])
        tree.identify_row.assert_called_with(10)
        tree.get_children.assert_called_with("order1")


class TestDBConcurrency(unittest.TestCase):
    @patch("ui.order_app.compute_lead_times", return_value={})
    def test_log_order_thread_safety(self, mock_compute):
        app = OrderScraperApp.__new__(OrderScraperApp)
        app.db = sqlite3.connect(":memory:", check_same_thread=False)
        app.db_lock = threading.Lock()
        cur = app.db.cursor()
        cur.execute("CREATE TABLE orders (order_number TEXT PRIMARY KEY, company TEXT)")
        cur.execute("CREATE TABLE steps (order_number TEXT, step TEXT, timestamp TEXT)")
        cur.execute(
            "CREATE TABLE lead_times (order_number TEXT, workstation TEXT, start TEXT, end TEXT, hours REAL)"
        )
        app.db.commit()

        def worker(i):
            app.log_order(str(i), f"Co{i}", [])

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        cur.execute("SELECT order_number FROM orders")
        rows = {r[0] for r in cur.fetchall()}
        self.assertEqual(rows, {str(i) for i in range(10)})


if __name__ == "__main__":
    unittest.main()
