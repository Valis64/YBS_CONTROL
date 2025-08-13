import argparse
import csv
import re
import logging
from collections import defaultdict
from datetime import datetime

from bs4 import BeautifulSoup

from time_utils import business_hours_delta

HTML_DATE_FORMAT = "%m/%d/%y %H:%M"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate lead time report from manage.html"
    )
    parser.add_argument("html_file", help="Path to manage.html")
    parser.add_argument(
        "--output", default="lead_time_report.csv", help="Output CSV path"
    )
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    return parser.parse_args()


def parse_manage_html(path):
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    jobs = {}
    for tr in soup.select("tbody#table tr"):
        move_td = tr.find("td", class_="move")
        if not move_td:
            continue
        job_text = move_td.get_text(strip=True)
        match = re.search(r"\b(\d+)\b", job_text)
        if not match:
            logging.warning("Could not find job ID in row: %s", job_text)
            continue
        job_number = match.group(1)
        steps = []
        for li in tr.select("ul.workplaces li"):
            step_p = li.find("p")
            if not step_p:
                continue
            step_name = re.sub(r"^\d+", "", step_p.get_text(strip=True))
            time_p = li.find("p", class_="np")
            timestamp = None
            if time_p:
                text = time_p.get_text(strip=True).replace("\xa0", "").strip()
                if text:
                    try:
                        timestamp = datetime.strptime(text, HTML_DATE_FORMAT)
                    except ValueError:
                        pass
            steps.append((step_name.strip(), timestamp))
        jobs[job_number] = steps
    return jobs


def compute_lead_times(jobs, start_date=None, end_date=None):
    """Return hours spent in each workstation including timestamps.

    Only include steps where the start timestamp is on or after ``start_date``
    and the end timestamp is on or before ``end_date``.
    """

    results = defaultdict(list)
    for job, steps in jobs.items():
        for (name, start), (next_name, end) in zip(steps, steps[1:]):
            if not start or not end:
                continue
            if start_date and start < start_date:
                continue
            if end_date and end > end_date:
                continue
            delta = business_hours_delta(start, end)
            hours = delta.total_seconds() / 3600.0
            results[job].append(
                {
                    "workstation": next_name,
                    "hours": hours,
                    "start": start,
                    "end": end,
                }
            )
    return results


def generate_realtime_report(jobs, start_date=None, end_date=None):
    """Generate a realtime style report of lead times.

    The returned value is a list of tuples ordered the same way the jobs appear
    in ``manage.html``. Each tuple contains ``(order, workstation, start, end,
    hours)`` where ``start`` and ``end`` are ``datetime`` objects and ``hours``
    is the number of business hours between them.
    """

    lead_times = compute_lead_times(jobs, start_date, end_date)
    report = []
    for order in jobs:  # preserve realtime ordering
        for step in lead_times.get(order, []):
            report.append(
                (
                    order,
                    step["workstation"],
                    step["start"],
                    step["end"],
                    step["hours"],
                )
            )
    return report


def write_report(results, path):
    """Write lead time data to ``path`` including timestamps."""
    with open(path, "w", newline="") as f:
        fieldnames = ["job_number", "workstation", "hours_in_queue", "start", "end"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for job, steps in results.items():
            for step in steps:
                writer.writerow(
                    {
                        "job_number": job,
                        "workstation": step["workstation"],
                        "hours_in_queue": f"{step['hours']:.2f}",
                        "start": step["start"].isoformat(sep=" "),
                        "end": step["end"].isoformat(sep=" "),
                    }
                )


def main():
    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d") if args.start else None
    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else None
    if start and end and end < start:
        raise argparse.ArgumentTypeError("--end must be on or after --start")
    jobs = parse_manage_html(args.html_file)
    results = compute_lead_times(jobs, start, end)
    write_report(results, args.output)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
