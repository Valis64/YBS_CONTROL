import os
import tempfile
import unittest
from datetime import datetime
import sys
import argparse
import csv

from bs4 import BeautifulSoup

import manage_html_report
from manage_html_report import (
    compute_lead_times,
    parse_manage_html,
    generate_realtime_report,
    write_realtime_report,
)

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

SAMPLE_HTML_TEMPLATE = """
<tbody id="table">
<tr data-id="1">
<td class="move"><p>{job_text}</p></td>
<td></td>
<td></td>
<td>
<ul class="workplaces">
<li><p><span class="circle"></span>Step1</p><p class="np">07/22/25 10:00</p></li>
<li class="active_ws"><p><span class="circle"></span>Step2</p><p class="np">&nbsp;</p></li>
</ul>
</td>
</tr>
</tbody>
"""

SAMPLE_HTML_MULTI = """
<tbody id="table">
<tr data-id="1">
<td class="move"><p>YBS 1001</p></td>
<td></td>
<td></td>
<td>
<ul class="workplaces">
<li><p><span class="circle"></span>Prep</p><p class="np">07/22/25 10:00</p></li>
<li><p><span class="circle"></span>Print</p><p class="np">07/22/25 11:00</p></li>
</ul>
</td>
</tr>
<tr data-id="2">
<td class="move"><p>YBS 1002</p></td>
<td></td>
<td></td>
<td>
<ul class="workplaces">
<li><p><span class="circle"></span>Prep</p><p class="np">07/21/25 09:00</p></li>
<li><p><span class="circle"></span>Print</p><p class="np">07/21/25 10:00</p></li>
</ul>
</td>
</tr>
</tbody>
"""


class ManageHTMLTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html")
        tmp.write(SAMPLE_HTML)
        tmp.flush()
        self.tmp_path = tmp.name
        tmp.close()

    def tearDown(self):
        os.remove(self.tmp_path)

    def test_parse_manage_html(self):
        jobs = parse_manage_html(self.tmp_path)
        self.assertIn("1001", jobs)
        steps = jobs["1001"]
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0][0], "Print Files YBS")
        self.assertIsInstance(steps[0][1], datetime)
        self.assertIsNone(steps[2][1])

    def test_parse_manage_html_trailing_punctuation(self):
        html = SAMPLE_HTML_TEMPLATE.format(job_text="YBS 1002.")
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html") as tmp:
            tmp.write(html)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        self.assertIn("1002", jobs)
        os.remove(tmp_path)

    def test_parse_manage_html_additional_text(self):
        html = SAMPLE_HTML_TEMPLATE.format(job_text="Order 1003 extra")
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html") as tmp:
            tmp.write(html)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        self.assertIn("1003", jobs)
        os.remove(tmp_path)

    def test_parse_manage_html_skips_non_numeric(self):
        html = SAMPLE_HTML_TEMPLATE.format(job_text="No digits here")
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html") as tmp:
            tmp.write(html)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        self.assertEqual(jobs, {})
        os.remove(tmp_path)

    def test_compute_lead_times(self):
        jobs = parse_manage_html(self.tmp_path)
        results = compute_lead_times(jobs)
        entry = results["1001"][0]
        self.assertAlmostEqual(entry["hours"], 13.5)
        self.assertEqual(entry["start"], datetime(2025, 7, 22, 10, 0))
        self.assertEqual(entry["end"], datetime(2025, 7, 23, 15, 0))

    def test_generate_realtime_report(self):
        jobs = parse_manage_html(self.tmp_path)
        report = generate_realtime_report(jobs)
        self.assertEqual(len(report), 1)
        order, workstation, start, end, hours = report[0]
        self.assertEqual(order, "1001")
        self.assertEqual(workstation, "Indigo")
        self.assertEqual(start, datetime(2025, 7, 22, 10, 0))
        self.assertEqual(end, datetime(2025, 7, 23, 15, 0))
        self.assertAlmostEqual(hours, 13.5)

    def test_write_realtime_report(self):
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".html") as tmp:
            tmp.write(SAMPLE_HTML_MULTI)
            html_path = tmp.name

        jobs = parse_manage_html(html_path)
        report = generate_realtime_report(jobs)
        csv_fd, csv_path = tempfile.mkstemp(suffix=".csv")
        html_fd, out_html_path = tempfile.mkstemp(suffix=".html")
        os.close(csv_fd)
        os.close(html_fd)

        try:
            write_realtime_report(report, csv_path, out_html_path)

            # verify CSV output
            with open(csv_path, newline="") as f:
                rows = list(csv.reader(f))
            self.assertEqual(
                rows[0],
                ["job_number", "workstation", "start", "end", "hours_in_queue"],
            )
            # chronological order (job 1002 starts earlier than 1001)
            self.assertEqual(rows[1][0], "1002")
            self.assertEqual(rows[2][0], "1001")
            # date formatting
            datetime.strptime(rows[1][2], manage_html_report.HTML_DATE_FORMAT)
            datetime.strptime(rows[1][3], manage_html_report.HTML_DATE_FORMAT)

            # verify HTML output
            with open(out_html_path, encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
            headers = [th.get_text() for th in soup.select("thead tr th")]
            self.assertEqual(
                headers,
                ["job_number", "workstation", "start", "end", "hours_in_queue"],
            )
            first_row = [td.get_text() for td in soup.select("tbody tr")[0].find_all("td")]
            self.assertEqual(first_row[0], "1002")
        finally:
            os.remove(html_path)
            os.remove(csv_path)
            os.remove(out_html_path)

    def test_compute_lead_times_date_range(self):
        jobs = parse_manage_html(self.tmp_path)
        start = datetime(2025, 7, 23)
        results = compute_lead_times(jobs, start_date=start)
        self.assertEqual(len(results["1001"]), 0)

    def test_main_invalid_date_range(self):
        argv = [
            "manage_html_report.py",
            "dummy.html",
            "--start",
            "2025-07-24",
            "--end",
            "2025-07-23",
        ]
        old_argv = sys.argv
        try:
            sys.argv = argv
            with self.assertRaises(argparse.ArgumentTypeError):
                manage_html_report.main()
        finally:
            sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
