import csv
from datetime import datetime
from collections import defaultdict
import argparse

from time_utils import business_hours_delta, business_hours_breakdown

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate lead time report from CSV data")
    parser.add_argument("csv_file", help="Path to job timeline CSV")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", default="lead_time_report.csv", help="Output CSV path")
    parser.add_argument(
        "--show-breakdown",
        action="store_true",
        help="Print business hour segments for each row",
    )
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


def compute_lead_times(rows, start_date=None, end_date=None, show_breakdown=False):
    results = defaultdict(list)
    breakdowns = defaultdict(list) if show_breakdown else None
    for row in rows:
        if start_date and row["time_in"] < start_date:
            continue
        if end_date and row["time_out"] > end_date:
            continue

        if show_breakdown:
            segments = business_hours_breakdown(row["time_in"], row["time_out"])
            total_seconds = sum(
                (seg_end - seg_start).total_seconds() for seg_start, seg_end in segments
            )
            breakdowns[row["job_number"]].append(
                {"step": row["step"], "segments": segments}
            )
        else:
            delta = business_hours_delta(row["time_in"], row["time_out"])
            total_seconds = delta.total_seconds()

        hours = total_seconds / 3600.0
        results[row["job_number"]].append({"step": row["step"], "hours": hours})

    if show_breakdown:
        return results, breakdowns
    return results


def format_breakdown(job_number, step_name, segments):
    lines = [f"Breakdown for job {job_number} step {step_name}:"]
    for seg_start, seg_end in segments:
        seg_seconds = (seg_end - seg_start).total_seconds()
        lines.append(
            f"  {seg_start} -> {seg_end} ({seg_seconds / 3600.0:.2f}h)"
        )
    return "\n".join(lines)


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
    if start_date and end_date and end_date < start_date:
        raise argparse.ArgumentTypeError("--end must be on or after --start")
    rows = list(load_rows(args.csv_file))
    res = compute_lead_times(
        rows, start_date, end_date, show_breakdown=args.show_breakdown
    )
    if args.show_breakdown:
        results, breakdowns = res
        for job, entries in breakdowns.items():
            for entry in entries:
                print(format_breakdown(job, entry["step"], entry["segments"]))
    else:
        results = res
    write_report(results, args.output)
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
