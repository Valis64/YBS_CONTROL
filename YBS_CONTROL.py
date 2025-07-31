import tkinter as tk
from tkinter import ttk, messagebox
import threading
import requests
from bs4 import BeautifulSoup
import time

LOGIN_URL = "https://www.ybsnow.com/login.php"
ORDERS_URL = "https://www.ybsnow.com/manage.html"

class OrderScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Order Scraper")

        self.session = requests.Session()
        self.logged_in = False

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()

        # Tabs
        self.tab_control = ttk.Notebook(root)
        self.settings_tab = ttk.Frame(self.tab_control)
        self.orders_tab = ttk.Frame(self.tab_control)
        self.tab_control.add(self.settings_tab, text="Settings")
        self.tab_control.add(self.orders_tab, text="Orders")
        self.tab_control.pack(expand=1, fill="both")

        # Settings Tab
        ttk.Label(self.settings_tab, text="Username:").grid(row=0, column=0)
        ttk.Entry(self.settings_tab, textvariable=self.username_var).grid(row=0, column=1)
        ttk.Label(self.settings_tab, text="Password:").grid(row=1, column=0)
        ttk.Entry(self.settings_tab, textvariable=self.password_var, show='*').grid(row=1, column=1)
        ttk.Button(self.settings_tab, text="Login", command=self.login).grid(row=2, column=0, columnspan=2)

        # Orders Tab
        self.orders_tree = ttk.Treeview(self.orders_tab, columns=("Order", "Details", "Status", "Priority"), show='headings')
        self.orders_tree.heading("Order", text="Order")
        self.orders_tree.heading("Details", text="Details")
        self.orders_tree.heading("Status", text="Status")
        self.orders_tree.heading("Priority", text="Priority")
        self.orders_tree.pack(expand=1, fill="both")
        ttk.Button(self.orders_tab, text="Refresh Orders", command=self.get_orders).pack()

        # Relogin timer
        self.relogin_thread = threading.Thread(target=self.relogin_loop, daemon=True)
        self.relogin_thread.start()

    def login(self):
        username = self.username_var.get()
        password = self.password_var.get()
        data = {'username': username, 'password': password}
        resp = self.session.post(LOGIN_URL, data=data)
        if "logout" in resp.text.lower() or "manage.html" in resp.text.lower():
            self.logged_in = True
            messagebox.showinfo("Login", "Login successful!")
        else:
            self.logged_in = False
            messagebox.showerror("Login", "Login failed.")
        self.get_orders()

    def get_orders(self):
        if not self.logged_in:
            messagebox.showerror("Error", "Not logged in!")
            return
        resp = self.session.get(ORDERS_URL)
        soup = BeautifulSoup(resp.text, 'html.parser')
        tbody = soup.find('tbody', id='table')
        self.orders_tree.delete(*self.orders_tree.get_children())
        if tbody:
            for tr in tbody.find_all('tr'):
                tds = tr.find_all('td')
                try:
                    order = tds[0].text.strip().replace("\n", " ")
                    details = tds[1].text.strip().replace("\n", " ")
                    status = tds[3].text.strip().replace("\n", " ")
                    priority = tds[5].find('input').get('value') if tds[5].find('input') else ''
                    self.orders_tree.insert('', 'end', values=(order, details, status, priority))
                except Exception as e:
                    print("Error parsing row:", e)

    def relogin_loop(self):
        while True:
            time.sleep(2*60*60)  # 2 hours
            if self.logged_in:
                print("Relogging in...")
                self.login()

if __name__ == "__main__":
    root = tk.Tk()
    app = OrderScraperApp(root)
    root.mainloop()
