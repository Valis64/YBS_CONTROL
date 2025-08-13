import unittest
from datetime import datetime
from io import StringIO
from contextlib import redirect_stdout
import sys
import argparse

import lead_time_report
from lead_time_report import compute_lead_times, format_breakdown


class LeadTimeTests(unittest.TestCase):
    def test_compute_lead_times(self):
        rows = [
            {
                "job_number": "1001",
                "step": "print",
                "time_in": datetime(2024, 1, 2, 8, 0),
                "time_out": datetime(2024, 1, 2, 12, 0),
            },
            {
                "job_number": "1001",
                "step": "laminate",
                "time_in": datetime(2024, 1, 3, 8, 0),
                "time_out": datetime(2024, 1, 3, 10, 0),
            },
        ]
        res = compute_lead_times(rows)
        self.assertEqual(len(res["1001"]), 2)
        self.assertAlmostEqual(res["1001"][0]["hours"], 4)
        self.assertAlmostEqual(res["1001"][1]["hours"], 2)

    def test_compute_lead_times_show_breakdown_prints(self):
        rows = [
            {
                "job_number": "1001",
                "step": "print",
                "time_in": datetime(2024, 1, 2, 8, 0),
                "time_out": datetime(2024, 1, 2, 12, 0),
            }
        ]
        buf = StringIO()
        with redirect_stdout(buf):
            res, breakdowns = compute_lead_times(rows, show_breakdown=True)
            for job, entries in breakdowns.items():
                for entry in entries:
                    print(format_breakdown(job, entry["step"], entry["segments"]))
        output = buf.getvalue()
        self.assertIn("Breakdown for job 1001 step print:", output)
        self.assertAlmostEqual(res["1001"][0]["hours"], 4)

    def test_main_invalid_date_range(self):
        argv = [
            "lead_time_report.py",
            "dummy.csv",
            "--start",
            "2024-01-02",
            "--end",
            "2024-01-01",
        ]
        old_argv = sys.argv
        try:
            sys.argv = argv
            with self.assertRaises(argparse.ArgumentTypeError):
                lead_time_report.main()
        finally:
            sys.argv = old_argv

if __name__ == "__main__":
    unittest.main()
