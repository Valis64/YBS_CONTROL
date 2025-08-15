"""HTML parsers for order and queue pages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Set
import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HTML_DATE_FORMAT = "%m/%d/%y %H:%M"


@dataclass
class Step:
    name: str
    timestamp: Optional[datetime]


@dataclass
class Order:
    number: str
    company: str
    status: str
    priority: str
    steps: List[Step]


def parse_orders(html: str) -> List[Order]:
    """Parse an orders HTML page into ``Order`` objects."""
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.find("tbody", id="table")
    orders: List[Order] = []
    if not tbody:
        return orders
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        try:
            cell_parts = list(tds[0].stripped_strings) if tds else []
            order_num = ""
            company = ""
            for part in cell_parts:
                if not order_num and re.search(r"\d", part):
                    match = re.search(r"([A-Za-z0-9_-]+)$", part)
                    order_num = (
                        match.group(1) if match else re.sub(r"[^A-Za-z0-9_-]", "", part)
                    )
                elif not company and re.search(r"[A-Za-z]", part):
                    company = part
            if (not company or company == "?") and len(tds) > 1:
                for text in tds[1].stripped_strings:
                    company = text
                    break
            status = tds[2].get_text(strip=True) if len(tds) > 2 else ""
            priority = ""
            if len(tds) > 4:
                pri_input = tds[4].find("input")
                priority = (
                    pri_input.get("value") if pri_input else tds[4].get_text(strip=True)
                )
            steps: List[Step] = []
            for li in tr.select("ul.workplaces li"):
                step_p = li.find("p")
                step_name = (
                    re.sub(r"^\d+", "", step_p.get_text(strip=True)) if step_p else ""
                )
                time_p = li.find("p", class_="np")
                ts = None
                if time_p:
                    text = time_p.get_text(strip=True).replace("\xa0", "").strip()
                    if text:
                        try:
                            ts = datetime.strptime(text, HTML_DATE_FORMAT)
                        except ValueError:
                            pass
                steps.append(Step(step_name, ts))
            orders.append(Order(order_num, company, status, priority, steps))
        except Exception:
            logger.exception("Error parsing row")
    return orders


def parse_queue(html: str) -> Set[str]:
    """Parse the queue HTML page and return a set of job numbers."""
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.find("tbody")
    current: Set[str] = set()
    if not tbody:
        return current
    for tr in tbody.find_all("tr"):
        td_text = tr.get_text(" ", strip=True)
        match = re.search(r"([A-Za-z0-9_-]*\d+[A-Za-z0-9_-]*)", td_text)
        if match:
            current.add(match.group(1))
    return current
