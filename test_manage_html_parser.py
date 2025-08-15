import pytest
from datetime import datetime

from parsers.manage_html import parse_orders, parse_queue, Order, Step


def test_parse_orders_basic():
    html = (
        "<table><tbody id='table'>"
        "<tr>"
        "<td>ACME Corp<br>Order #12345<ul class='workplaces'>"
        "<li><p>1Cut</p><p class='np'>01/01/24 10:00</p></li>"
        "</ul></td>"
        "<td></td>"
        "<td>Running</td>"
        "<td></td>"
        "<td><input value='High'/></td>"
        "</tr>"
        "</tbody></table>"
    )
    orders = parse_orders(html)
    assert len(orders) == 1
    order = orders[0]
    assert order.number == "12345"
    assert order.company == "ACME Corp"
    assert order.status == "Running"
    assert order.priority == "High"
    assert order.steps == [Step(name="Cut", timestamp=datetime(2024, 1, 1, 10, 0))]


def test_parse_queue_extracts_orders():
    html = "<table><tbody><tr><td>Order 100</td></tr><tr><td>Job-200</td></tr></tbody></table>"
    assert parse_queue(html) == {"100", "Job-200"}
