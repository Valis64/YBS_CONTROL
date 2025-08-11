import unittest
from unittest.mock import MagicMock, patch
import requests

from YBS_CONTROL import OrderScraperApp
from datetime import datetime


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


if __name__ == "__main__":
    unittest.main()
