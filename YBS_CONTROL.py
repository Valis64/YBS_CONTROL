import customtkinter as ctk

from ui.order_app import OrderScraperApp
from config.endpoints import LOGIN_URL


def main():
    root = ctk.CTk()
    OrderScraperApp(root, login_url=LOGIN_URL)
    root.mainloop()


if __name__ == "__main__":
    main()
