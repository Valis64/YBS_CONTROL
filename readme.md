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

Install dependencies with:

bash
Copy
Edit
pip install requests beautifulsoup4 customtkinter
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

Date range filtering is available directly in the GUI. Enter a start and/or end
date on the Orders tab (in `YYYY-MM-DD` format) and use **Export Date Range** to
save a report for all jobs in that window. Selecting an individual order and
clicking **Export Report** will also honour the entered dates.

You can also parse a saved `manage.html` file with `manage_html_report.py`:

```bash
python manage_html_report.py manage.html --output report.csv \
    --start 2024-01-01 --end 2024-01-31
```

This reads the workstation timestamps from the HTML table and produces the same style report.
