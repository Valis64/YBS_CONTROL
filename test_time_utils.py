import unittest
from datetime import datetime

from time_utils import business_hours_delta


class TimeUtilsTests(unittest.TestCase):
    def test_business_hours_skip_weekend(self):
        start = datetime(2024, 1, 5, 16, 0)  # Friday 4pm
        end = datetime(2024, 1, 8, 10, 0)  # Monday 10am
        delta = business_hours_delta(start, end)
        self.assertEqual(delta.total_seconds() / 3600, 18)  # 18 hours (weekend excluded)


if __name__ == "__main__":
    unittest.main()
