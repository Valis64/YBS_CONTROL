import os
import requests

from config.endpoints import LOGIN_URL, ORDERS_URL, QUEUE_URL

def login(session, credentials):
    """Attempt to log into YBS.

    Args:
        session: requests.Session used for HTTP requests.
        credentials: dict containing 'username', 'password', and optional
            'login_url' and 'orders_url'.

    Returns:
        dict with keys ``success`` and ``response``. ``success`` is ``True``
        if the login appears successful based on the response HTML.

    Raises:
        requests.RequestException: if the request fails.
    """
    login_url = credentials.get("login_url", LOGIN_URL)
    orders_url = credentials.get("orders_url", ORDERS_URL)
    data = {
        "email": credentials.get("username", ""),
        "password": credentials.get("password", ""),
        "action": "signin",
    }
    resp = session.post(login_url, data=data, timeout=10)
    orders_page = os.path.basename(orders_url).lower()
    success = "logout" in resp.text.lower() or orders_page in resp.text.lower()
    return {"success": success, "response": resp}

def fetch_orders(session, orders_url=ORDERS_URL, queue_url=QUEUE_URL):
    """Fetch the orders and queue pages.

    Args:
        session: requests.Session used for HTTP requests.
        orders_url: URL of the orders page.
        queue_url: URL of the queue page.

    Returns:
        dict with ``orders_html`` and ``queue_html`` keys.

    Raises:
        requests.RequestException: if a request fails.
    """
    resp_orders = session.get(orders_url, timeout=10)
    resp_queue = session.get(queue_url, timeout=10)
    return {"orders_html": resp_orders.text, "queue_html": resp_queue.text}
