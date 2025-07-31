import os
import tempfile
import unittest
from datetime import datetime, timedelta

from manage_html_report import compute_lead_times, parse_manage_html

SAMPLE_HTML = """
<tbody id="table">
<tr data-id="1">
<td class="move"><p>YBS 1001</p></td>
<td></td>
<td></td>
<td>
<ul class="workplaces">
<li><p><span class="circle green-step">0</span>Print Files YBS</p><p class="np">07/22/25 10:00</p></li>
<li><p><span class="circle green-step">0</span>Indigo</p><p class="np">07/23/25 15:00</p></li>
<li class="active_ws"><p><span class="circle"></span>Laminate</p><p class="np">&nbsp;</p></li>
</ul>
</td>
</tr>
</tbody>
"""


class ManageHTMLTests(unittest.TestCase):
    def test_parse_manage_html(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html") as tmp:
            tmp.write(SAMPLE_HTML)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        self.assertIn("1001", jobs)
        steps = jobs["1001"]
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0][0], "Print Files YBS")
        self.assertIsInstance(steps[0][1], datetime)
        self.assertIsNone(steps[2][1])
        os.remove(tmp_path)

    def test_compute_lead_times(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html") as tmp:
            tmp.write(SAMPLE_HTML)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        results = compute_lead_times(jobs)
        entry = results["1001"][0]
        self.assertAlmostEqual(entry["hours"], 29.0)
        self.assertIsInstance(entry["start"], datetime)
        self.assertIsInstance(entry["end"], datetime)
        os.remove(tmp_path)

    def test_compute_lead_times_date_range(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html") as tmp:
            tmp.write(SAMPLE_HTML)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        start = datetime(2025, 7, 23)
        results = compute_lead_times(jobs, start_date=start)
        self.assertEqual(len(results["1001"]), 0)
        os.remove(tmp_path)

    def test_compute_lead_times_end_date_inclusive(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html") as tmp:
            tmp.write(SAMPLE_HTML)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        end = datetime(2025, 7, 23) + timedelta(days=1) - timedelta(microseconds=1)
        results = compute_lead_times(jobs, end_date=end)
        self.assertEqual(len(results["1001"]), 1)
        os.remove(tmp_path)


if __name__ == "__main__":
    unittest.main()
