from unittest.mock import MagicMock, patch
import requests
import os
import threading
import unittest
from datetime import time

from ui.order_app import OrderScraperApp
from login_dialog import LoginDialog
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

    @patch("login_dialog.messagebox")
    def test_login_request_exception(self, mock_messagebox):
        self.dialog.session.post.side_effect = requests.Timeout("boom")
        with patch("login_dialog.LOGIN_URL", "http://example.com/login"):
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
        self.app.tab_control = MagicMock()
        self.app.config = {}
        self.app.save_config = MagicMock()
        self.app.last_db_dir = ""
        self.app.export_path_var = SimpleVar("/tmp")
        self.app.export_time_var = SimpleVar("")
        self.app.export_job = None
        self.app.db_lock = threading.Lock()
        self.app.range_start_var = SimpleVar("")
        self.app.range_end_var = SimpleVar("")
        self.app.range_total_jobs_var = SimpleVar("")
        self.app.range_total_hours_var = SimpleVar("")
        self.app.date_tree = MagicMock()
        self.app.date_tree.get_children.return_value = []
        self.app.date_range_filter_var = SimpleVar("")
        self.app.filtered_raw_date_range_rows = []
        self.app._run_scheduled_export = OrderScraperApp._run_scheduled_export.__get__(self.app)
        self.app.run_date_range_report = OrderScraperApp.run_date_range_report.__get__(self.app)
        self.app.populate_date_range_table = OrderScraperApp.populate_date_range_table.__get__(self.app)
        self.app.update_date_range_summary = OrderScraperApp.update_date_range_summary.__get__(self.app)
        self.app.sort_date_range_table = OrderScraperApp.sort_date_range_table.__get__(self.app)
        self.app.filter_date_range_rows = OrderScraperApp.filter_date_range_rows.__get__(self.app)
        self.app.clear_date_range_report = OrderScraperApp.clear_date_range_report.__get__(self.app)

    @patch("ui.order_app.messagebox")
    def test_get_date_range_invalid_order(self, mock_messagebox):
        self.app.range_start_var = SimpleVar("2024-01-02")
        self.app.range_end_var = SimpleVar("2024-01-01")
        start, end = OrderScraperApp.get_date_range(
            self.app, self.app.range_start_var, self.app.range_end_var
        )
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
        OrderScraperApp.connect_db(self.app, r"\\\\server\\share\\orders.db")
        mock_connect.assert_called_with(r"\\\\server\\share\\orders.db", check_same_thread=False)
        self.assertEqual(self.app.config["db_path"], r"\\\\server\\share\\orders.db")
        expected_dir = os.path.dirname(r"\\\\server\\share\\orders.db") or os.getcwd()
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


if __name__ == "__main__":
    unittest.main()

