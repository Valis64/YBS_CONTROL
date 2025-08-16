import customtkinter as ctk

# Configure dark appearance and theme before creating any widgets
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

from ui.order_app import OrderScraperApp
from config.endpoints import LOGIN_URL


def main():
    root = ctk.CTk()
    OrderScraperApp(root, login_url=LOGIN_URL)
    root.mainloop()


if __name__ == "__main__":
    main()
