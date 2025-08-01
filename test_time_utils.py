import unittest
from datetime import datetime

from time_utils import business_hours_delta, business_hours_breakdown


class TimeUtilsTests(unittest.TestCase):
    def test_business_hours_skip_weekend(self):
        start = datetime(2024, 1, 5, 16, 0)  # Friday 4pm
        end = datetime(2024, 1, 8, 10, 0)  # Monday 10am
        delta = business_hours_delta(start, end)
        self.assertEqual(delta.total_seconds() / 3600, 2.5)  # 2.5 hours within business hours

        segments = business_hours_breakdown(start, end)
        expected = [
            (datetime(2024, 1, 5, 16, 0), datetime(2024, 1, 5, 16, 30)),
            (datetime(2024, 1, 8, 8, 0), datetime(2024, 1, 8, 10, 0)),
        ]
        self.assertEqual(segments, expected)


if __name__ == "__main__":
    unittest.main()
