import customtkinter as ctk

# Configure dark appearance and theme before creating any widgets
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

from ui.order_app import OrderScraperApp
from login_dialog import LoginDialog


def main():
    dialog = LoginDialog()
    dialog.mainloop()
    if not dialog.authenticated:
        return
    root = ctk.CTk()
    OrderScraperApp(
        root,
        session=dialog.session,
        orders_url=dialog.orders_url_var.get(),
    )
    root.mainloop()


if __name__ == "__main__":
    main()
