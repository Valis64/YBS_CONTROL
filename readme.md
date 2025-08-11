YBS Order Scraper
A simple Python GUI tool to log in to ybsnow.com, persist the session, and scrape/display order information from the orders table. The session automatically relogs every 2 hours to ensure your session stays fresh.

Features
Easy-to-use CustomTkinter GUI with Settings, Orders and Database tabs

Secure login (username & password, stored only for session)

Retrieves tabular order information from the orders page

Refresh orders with a single click

Automatic session relogin every 2 hours

Automatically refreshes and stores order data every 5 minutes (configurable after login)

Easily extendable for export (CSV, Excel, etc.)

Specify custom Login and Orders URLs (handles .php or .html pages)

Requirements
Python 3.8+

requests

beautifulsoup4

customtkinter

tkcalendar

Install dependencies with:

```bash
pip install requests beautifulsoup4 customtkinter tkcalendar
```
Usage
Run the script

bash
Copy
Edit
python YBS_CONTROL.py
Login

Go to the “Settings” tab

Enter your YBS username and password.
Optional: adjust the Login URL or Orders URL if your site uses different
endpoints, then click Login

View Orders

Switch to the “Orders” tab

Click Refresh Orders to fetch and display the current orders table

After logging in, the Orders database will refresh automatically every 5 minutes.  You can adjust this interval on the Settings tab once logged in.

The tool will keep your session alive by automatically re-logging in every 2 hours in the background.

Project Structure
bash
Copy
Edit
YBS_CONTROL.py           # Main application script
README.md                # This file
Customization
Table Columns: Add or remove columns in the get_orders() function.

Export: Add CSV/Excel export by extending the Orders tab logic.

Error Handling: Modify login or table parsing logic as site changes.

Troubleshooting
If login fails, double-check your credentials.

If the table isn’t loading, the site structure may have changed (contact the maintainer for updates).

If you encounter captchas or 2FA, the script will need additional logic.

Disclaimer
This project is for educational/internal automation purposes only. Do not distribute or use on unauthorized sites.

Need a feature or help?
Open an issue or contact Valis.

Lead Time Report
----------------
The `lead_time_report.py` script generates a CSV report showing how long jobs spend in each workstation queue using a CSV export. The CSV must contain the columns `job_number`, `step`, `time_in`, and `time_out` where the timestamps are in `YYYY-MM-DD HH:MM:SS` format. Usage:

```bash
python lead_time_report.py data.csv --start 2024-01-01 --end 2024-01-31 --output report.csv
```

The script calculates time spent in each queue using business hours
(8:00–16:30, Monday–Friday) and excludes weekends from the
calculation. A helper `business_hours_breakdown()` function in
`time_utils.py` can be used to inspect the exact segments counted if you
need to verify how business hours were applied.

How Lead-Time Hours Are Calculated
---------------------------------

Lead-time hours are measured only during the 08:00–16:30 window on weekdays.
Time outside this range is ignored, and Saturdays and Sundays are skipped.

1. The `business_hours_breakdown()` function slices each `time_in`/`time_out`
   pair into segments that fall within business hours.
2. Durations of these segments are summed.
3. The total is converted to hours for the final report.

Example:

```python
from datetime import datetime, timedelta
from time_utils import business_hours_breakdown

start = datetime(2024, 1, 5, 16, 0)  # Friday 4pm
end = datetime(2024, 1, 8, 10, 0)    # Monday 10am

segments = business_hours_breakdown(start, end)
for seg_start, seg_end in segments:
    print(f"{seg_start} -> {seg_end}")

total = sum((seg_end - seg_start for seg_start, seg_end in segments), timedelta())
print(total.total_seconds() / 3600)
```

Output:

```
2024-01-05 16:00:00 -> 2024-01-05 16:30:00
2024-01-08 08:00:00 -> 2024-01-08 10:00:00
2.5
```

The example shows a 30-minute segment on Friday and a 2-hour segment on
Monday, totalling 2.5 lead-time hours.

Date range filtering is available directly in the GUI. Use the preset menu (Today,
Last 7 days, etc.) or choose **Custom** to pick start and end dates from
calendar widgets on the Orders tab. The chosen range is validated and reused on
next launch. Use **Export Date Range** to save a report for all jobs in the
window. Selecting an individual order and clicking **Export Report** will also
honour the entered dates.

You can also parse a saved `manage.html` file with `manage_html_report.py`:

```bash
python manage_html_report.py manage.html --output report.csv \
    --start 2024-01-01 --end 2024-01-31
```

This reads the workstation timestamps from the HTML table and produces the same style report.

