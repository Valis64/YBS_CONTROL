import customtkinter as ctk
from tkinter import messagebox
import requests
import os

# Configure dark appearance and theme before creating any widgets
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

from config.endpoints import LOGIN_URL, ORDERS_URL


class LoginDialog(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Login")
        self.session = requests.Session()
        self.authenticated = False

        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.login_url_var = ctk.StringVar(value=LOGIN_URL)
        self.orders_url_var = ctk.StringVar(value=ORDERS_URL)

        ctk.CTkLabel(self, text="Username:").grid(row=0, column=0, padx=5, pady=5)
        ctk.CTkEntry(self, textvariable=self.username_var).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(self, text="Password:").grid(row=1, column=0, padx=5, pady=5)
        ctk.CTkEntry(self, textvariable=self.password_var, show="*").grid(row=1, column=1, padx=5, pady=5)
        ctk.CTkLabel(self, text="Login URL:").grid(row=2, column=0, padx=5, pady=5)
        ctk.CTkEntry(self, textvariable=self.login_url_var).grid(row=2, column=1, padx=5, pady=5)
        ctk.CTkLabel(self, text="Orders URL:").grid(row=3, column=0, padx=5, pady=5)
        ctk.CTkEntry(self, textvariable=self.orders_url_var).grid(row=3, column=1, padx=5, pady=5)
        ctk.CTkButton(self, text="Login", command=self.login).grid(row=4, column=0, columnspan=2, pady=10)

    def login(self, silent=False):
        username = self.username_var.get()
        password = self.password_var.get()
        data = {
            "email": username,
            "password": password,
            "action": "signin",
        }
        login_url = self.login_url_var.get() or LOGIN_URL
        try:
            resp = self.session.post(login_url, data=data, timeout=10)
        except requests.RequestException as e:
            if not silent:
                messagebox.showerror("Login", f"Login request failed: {e}")
            return
        orders_page = os.path.basename(self.orders_url_var.get() or ORDERS_URL).lower()
        if "logout" in resp.text.lower() or orders_page in resp.text.lower():
            self.authenticated = True
            if not silent:
                messagebox.showinfo("Login", "Login successful!")
            self.destroy()
        else:
            if not silent:
                messagebox.showerror("Login", "Login failed.")
