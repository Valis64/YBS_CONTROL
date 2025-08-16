import customtkinter as ctk

# Configure dark appearance and theme before creating any widgets
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

from ui.order_app import OrderScraperApp
from login_dialog import LoginDialog
from config.endpoints import ORDERS_URL


def main():
    dialog = LoginDialog()
    dialog.mainloop()
    if not dialog.authenticated:
        return
    root = ctk.CTk()
    orders_var = getattr(dialog, "orders_url_var", None)
    orders_url = ORDERS_URL
    if orders_var:
        value = orders_var.get()
        if value:
            orders_url = value
    OrderScraperApp(
        root,
        session=dialog.session,
        orders_url=orders_url,
    )
    root.mainloop()


if __name__ == "__main__":
    main()
