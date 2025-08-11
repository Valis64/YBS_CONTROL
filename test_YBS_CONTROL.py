import unittest
from unittest.mock import MagicMock, patch
import requests
import os

from YBS_CONTROL import OrderScraperApp
from datetime import datetime, time
import time_utils


class SimpleVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


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
        self.app.refresh_database_tab = MagicMock()
        self.app.order_rows = []
        self.app.config = {}
        self.app.save_config = MagicMock()
        self.app.last_db_dir = ""

    @patch("YBS_CONTROL.messagebox")
    def test_login_request_exception(self, mock_messagebox):
        self.app.get_orders = MagicMock()
        self.app.session.post.side_effect = requests.Timeout("boom")
        self.app.login()
        self.app.session.post.assert_called_with(
            "http://example.com/login",
            data={"email": "user", "password": "pass", "action": "signin"},
            timeout=10,
        )
        mock_messagebox.showerror.assert_called_once()
        self.app.get_orders.assert_not_called()

    @patch("YBS_CONTROL.messagebox")
    def test_get_orders_request_exception(self, mock_messagebox):
        self.app.session.get.side_effect = requests.RequestException("fail")
        self.app.get_orders()
        self.app.session.get.assert_called_with("http://example.com/orders", timeout=10)
        mock_messagebox.showerror.assert_called_once()
        self.app.orders_tree.delete.assert_not_called()

    @patch("YBS_CONTROL.messagebox")
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

    @patch("YBS_CONTROL.sqlite3.connect")
    def test_connect_db_allows_network_path(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        self.app.db_path_var = SimpleVar("orders.db")
        self.app.db = MagicMock()
        OrderScraperApp.connect_db(self.app, r"\\server\share\orders.db")
        mock_connect.assert_called_with(r"\\server\share\orders.db")
        self.assertEqual(self.app.config["db_path"], r"\\server\share\orders.db")
        expected_dir = os.path.dirname(r"\\server\share\orders.db") or os.getcwd()
        self.assertEqual(self.app.last_db_dir, expected_dir)
        self.app.save_config.assert_called_once()

    @patch("YBS_CONTROL.messagebox")
    def test_update_business_hours_valid(self, mock_messagebox):
        self.app.business_start_var = SimpleVar("09:00")
        self.app.business_end_var = SimpleVar("17:00")
        OrderScraperApp.update_business_hours(self.app)
        self.assertEqual(time_utils.BUSINESS_START, time(9, 0))
        self.assertEqual(time_utils.BUSINESS_END, time(17, 0))
        mock_messagebox.showinfo.assert_called_once()
        # reset defaults
        time_utils.BUSINESS_START = time(8, 0)
        time_utils.BUSINESS_END = time(16, 30)

    @patch("YBS_CONTROL.filedialog.askopenfilename", return_value="/tmp/orders.db")
    def test_browse_db_uses_last_directory(self, mock_dialog):
        self.app.last_db_dir = "/tmp"
        self.app.connect_db = MagicMock()
        OrderScraperApp.browse_db(self.app)
        mock_dialog.assert_called_once()
        args, kwargs = mock_dialog.call_args
        self.assertEqual(kwargs.get("initialdir"), "/tmp")
        self.app.connect_db.assert_called_with("/tmp/orders.db")


if __name__ == "__main__":
    unittest.main()
