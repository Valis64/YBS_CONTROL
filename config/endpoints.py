import os
from .settings import load_config

_DEFAULT_LOGIN_URL = "https://www.ybsnow.com/index.php"
_DEFAULT_ORDERS_URL = "https://www.ybsnow.com/manage.html"
_DEFAULT_QUEUE_URL = "https://www.ybsnow.com/queue.html"

_config = load_config()

LOGIN_URL = os.getenv("YBS_LOGIN_URL", _config.get("login_url", _DEFAULT_LOGIN_URL))
ORDERS_URL = os.getenv("YBS_ORDERS_URL", _config.get("orders_url", _DEFAULT_ORDERS_URL))
QUEUE_URL = os.getenv("YBS_QUEUE_URL", _config.get("queue_url", _DEFAULT_QUEUE_URL))
