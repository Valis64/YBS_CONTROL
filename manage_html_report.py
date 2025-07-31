import csv
import re
from datetime import datetime, timedelta
from collections import defaultdict
from bs4 import BeautifulSoup
import argparse

HTML_DATE_FORMAT = "%m/%d/%y %H:%M"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate lead time report from manage.html")
    parser.add_argument("html_file", help="Path to manage.html")
    parser.add_argument("--output", default="lead_time_report.csv", help="Output CSV path")
    return parser.parse_args()


def business_hours_delta(start, end):
    total = timedelta(0)
    current = start
    while current < end:
        next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
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


def compute_lead_times(jobs):
    """Return hours spent in each workstation including timestamps."""
    results = defaultdict(list)
    for job, steps in jobs.items():
        for i in range(len(steps) - 1):
            name, start = steps[i]
            next_name, end = steps[i + 1]
            if start and end:
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
    results = compute_lead_times(jobs)
    write_report(results, args.output)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
