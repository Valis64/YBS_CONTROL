import argparse
import csv
import re
from collections import defaultdict
from datetime import datetime, timedelta

from bs4 import BeautifulSoup

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


def business_hours_delta(start, end):
    total = timedelta(0)
    current = start
    while current < end:
        next_day = (current + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        working_end = min(next_day, end)
        if current.weekday() < 5:
            total += working_end - current
        current = next_day
    return total


def parse_manage_html(path):
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    jobs = {}
    for tr in soup.select("tbody#table tr"):
        move_td = tr.find("td", class_="move")
        if not move_td:
            continue
        job_text = move_td.get_text(strip=True)
        parts = job_text.split()
        job_number = parts[-1] if parts else None
        if not job_number:
            continue
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
        for i in range(len(steps) - 1):
            name, start = steps[i]
            next_name, end = steps[i + 1]
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
                    "step": next_name,
                    "hours": hours,
                    "start": start,
                    "end": end,
                }
            )
    return results


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
                        "workstation": step["step"],
                        "hours_in_queue": f"{step['hours']:.2f}",
                        "start": step["start"].isoformat(sep=" "),
                        "end": step["end"].isoformat(sep=" "),
                    }
                )


def main():
    args = parse_args()
    jobs = parse_manage_html(args.html_file)
    start = datetime.strptime(args.start, "%Y-%m-%d") if args.start else None
    if args.end:
        end = datetime.strptime(args.end, "%Y-%m-%d") + timedelta(days=1) - timedelta(microseconds=1)
    else:
        end = None
    results = compute_lead_times(jobs, start, end)
    write_report(results, args.output)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
