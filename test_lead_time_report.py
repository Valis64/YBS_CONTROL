import unittest
from datetime import datetime
from lead_time_report import compute_lead_times, business_hours_delta

class LeadTimeTests(unittest.TestCase):
    def test_business_hours_skip_weekend(self):
        start = datetime(2024, 1, 5, 16, 0)  # Friday 4pm
        end = datetime(2024, 1, 8, 10, 0)    # Monday 10am
        delta = business_hours_delta(start, end)
        self.assertEqual(delta.total_seconds() / 3600, 18)  # 18 hours (weekend excluded)

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

if __name__ == "__main__":
    unittest.main()
