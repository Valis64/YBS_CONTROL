import unittest
import tempfile
import os
from datetime import datetime
from manage_html_report import parse_manage_html, compute_lead_times

SAMPLE_HTML = '''
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
'''

class ManageHTMLTests(unittest.TestCase):
    def test_parse_manage_html(self):
        with tempfile.NamedTemporaryFile('w+', delete=False, suffix='.html') as tmp:
            tmp.write(SAMPLE_HTML)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        self.assertIn('1001', jobs)
        steps = jobs['1001']
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0][0], 'Print Files YBS')
        self.assertIsInstance(steps[0][1], datetime)
        self.assertIsNone(steps[2][1])
        os.remove(tmp_path)

    def test_compute_lead_times(self):
        with tempfile.NamedTemporaryFile('w+', delete=False, suffix='.html') as tmp:
            tmp.write(SAMPLE_HTML)
            tmp_path = tmp.name
        jobs = parse_manage_html(tmp_path)
        results = compute_lead_times(jobs)
        entry = results['1001'][0]
        self.assertAlmostEqual(entry['hours'], 29.0)
        self.assertIsInstance(entry['start'], datetime)
        self.assertIsInstance(entry['end'], datetime)
        os.remove(tmp_path)

if __name__ == '__main__':
    unittest.main()
