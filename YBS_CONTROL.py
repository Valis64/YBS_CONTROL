import customtkinter as ctk
from tkinter import ttk, messagebox
import threading
import requests
from bs4 import BeautifulSoup
import time
import os

LOGIN_URL = "https://www.ybsnow.com/login.php"
ORDERS_URL = "https://www.ybsnow.com/manage.html"

class OrderScraperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Order Scraper")

        self.session = requests.Session()
        self.logged_in = False

        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.login_url_var = ctk.StringVar(value=LOGIN_URL)
        self.orders_url_var = ctk.StringVar(value=ORDERS_URL)

        # Tabs
        self.tab_control = ctk.CTkTabview(root)
        self.settings_tab = self.tab_control.add("Settings")
        self.orders_tab = self.tab_control.add("Orders")
        self.tab_control.pack(expand=1, fill="both")

        # Settings Tab
        ctk.CTkLabel(self.settings_tab, text="Username:").grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.username_var).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Password:").grid(row=1, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.password_var, show='*').grid(row=1, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Login URL:").grid(row=2, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.login_url_var).grid(row=2, column=1, padx=5, pady=5)
        ctk.CTkLabel(self.settings_tab, text="Orders URL:").grid(row=3, column=0, padx=5, pady=5)
        ctk.CTkEntry(self.settings_tab, textvariable=self.orders_url_var).grid(row=3, column=1, padx=5, pady=5)
        ctk.CTkButton(self.settings_tab, text="Login", command=self.login).grid(row=4, column=0, columnspan=2, pady=10)

        # Orders Tab
        self.table_frame = ctk.CTkFrame(self.orders_tab)
        self.table_frame.pack(expand=1, fill="both", padx=10, pady=10)

        self.orders_tree = ttk.Treeview(
            self.table_frame,
            columns=("Order", "Details", "Status", "Priority"),
            show="headings",
        )
        self.orders_tree.heading("Order", text="Order")
        self.orders_tree.heading("Details", text="Details")
        self.orders_tree.heading("Status", text="Status")
        self.orders_tree.heading("Priority", text="Priority")
        self.orders_tree.pack(side="left", expand=1, fill="both")

        scrollbar = ttk.Scrollbar(self.table_frame, orient="vertical", command=self.orders_tree.yview)
        self.orders_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        ctk.CTkButton(self.orders_tab, text="Refresh Orders", command=self.get_orders).pack(pady=5)

        # Relogin timer
        self.relogin_thread = threading.Thread(target=self.relogin_loop, daemon=True)
        self.relogin_thread.start()

    def login(self):
        username = self.username_var.get()
        password = self.password_var.get()
        data = {'username': username, 'password': password}
        login_url = self.login_url_var.get() or LOGIN_URL
        resp = self.session.post(login_url, data=data)
        orders_page = os.path.basename(self.orders_url_var.get() or ORDERS_URL).lower()
        if "logout" in resp.text.lower() or orders_page in resp.text.lower():
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
        orders_url = self.orders_url_var.get() or ORDERS_URL
        resp = self.session.get(orders_url)
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
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    root = ctk.CTk()
    app = OrderScraperApp(root)
    root.mainloop()
