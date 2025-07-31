YBS Order Scraper
A simple Python GUI tool to log in to ybsnow.com, persist the session, and scrape/display order information from the orders table. The session automatically relogs every 2 hours to ensure your session stays fresh.

Features
Easy-to-use Tkinter GUI with Settings and Orders tabs

Secure login (username & password, stored only for session)

Retrieves tabular order information from the orders page

Refresh orders with a single click

Automatic session relogin every 2 hours

Easily extendable for export (CSV, Excel, etc.)

Requirements
Python 3.8+

requests

beautifulsoup4

Install dependencies with:

bash
Copy
Edit
pip install requests beautifulsoup4
Usage
Run the script

bash
Copy
Edit
python ybs_order_scraper.py
Login

Go to the “Settings” tab

Enter your YBS username and password, then click Login

View Orders

Switch to the “Orders” tab

Click Refresh Orders to fetch and display the current orders table

The tool will keep your session alive by automatically re-logging in every 2 hours in the background.

Project Structure
bash
Copy
Edit
ybs_order_scraper.py     # Main application script
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
