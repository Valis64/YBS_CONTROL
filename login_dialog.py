import customtkinter as ctk
from tkinter import messagebox
import requests
import os

from config.endpoints import LOGIN_URL, ORDERS_URL


class LoginDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Login for YBSnow.com")
        self.session = requests.Session()
        self.authenticated = False

        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        ctk.CTkLabel(self, text="USER").grid(
            row=0, column=0, columnspan=2, padx=5, pady=(5, 0)
        )
        ctk.CTkEntry(
            self,
            textvariable=self.username_var,
        ).grid(row=1, column=0, columnspan=2, padx=5, pady=(0, 5))
        ctk.CTkLabel(self, text="PASSWORD").grid(
            row=2, column=0, columnspan=2, padx=5, pady=(5, 0)
        )
        ctk.CTkEntry(
            self,
            textvariable=self.password_var,
            show="*",
        ).grid(row=3, column=0, columnspan=2, padx=5, pady=(0, 5))
        ctk.CTkButton(self, text="Login", command=self.login).grid(
            row=4, column=0, columnspan=2, pady=10
        )

    def login(self, silent=False):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        if not username or not password:
            if not silent:
                messagebox.showerror("Login", "Username and password cannot be blank.")
            return
        data = {
            "email": username,
            "password": password,
            "action": "signin",
        }
        try:
            resp = self.session.post(LOGIN_URL, data=data, timeout=10)
        except requests.RequestException as e:
            if not silent:
                messagebox.showerror("Login", f"Login request failed: {e}")
            return
        orders_page = os.path.basename(ORDERS_URL).lower()
        if "logout" in resp.text.lower() or orders_page in resp.text.lower():
            self.authenticated = True
            if not silent:
                messagebox.showinfo("Login", "Login successful!")
            self.destroy()
        else:
            if not silent:
                messagebox.showerror("Login", "Login failed.")
