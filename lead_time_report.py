import csv
from datetime import datetime, timedelta
from collections import defaultdict
import argparse

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate lead time report from CSV data")
    parser.add_argument("csv_file", help="Path to job timeline CSV")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", default="lead_time_report.csv", help="Output CSV path")
    return parser.parse_args()


def load_rows(path):
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield {
                "job_number": row.get("job_number"),
                "step": row.get("step"),
                "time_in": datetime.strptime(row.get("time_in"), DATE_FORMAT),
                "time_out": datetime.strptime(row.get("time_out"), DATE_FORMAT),
            }


def business_hours_delta(start, end):
    total = timedelta(0)
    current = start
    while current < end:
        next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        working_end = min(next_day, end)
        # skip weekends
        if current.weekday() < 5:
            total += working_end - current
        current = next_day
    return total


def compute_lead_times(rows, start_date=None, end_date=None):
    results = defaultdict(list)
    for row in rows:
        if start_date and row["time_in"] < start_date:
            continue
        if end_date and row["time_out"] > end_date:
            continue
        delta = business_hours_delta(row["time_in"], row["time_out"])
        hours = delta.total_seconds() / 3600.0
        results[row["job_number"]].append({"step": row["step"], "hours": hours})
    return results


def write_report(results, path):
    with open(path, "w", newline="") as f:
        fieldnames = ["job_number", "step", "hours_in_queue"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for job, steps in results.items():
            for step in steps:
                writer.writerow({"job_number": job, "step": step["step"], "hours_in_queue": f"{step['hours']:.2f}"})


def main():
    args = parse_args()
    start_date = datetime.strptime(args.start, "%Y-%m-%d") if args.start else None
    end_date = datetime.strptime(args.end, "%Y-%m-%d") if args.end else None
    rows = list(load_rows(args.csv_file))
    results = compute_lead_times(rows, start_date, end_date)
    write_report(results, args.output)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
