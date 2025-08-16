import customtkinter as ctk

from ui import theme

theme.configure()

from ui.order_app import OrderScraperApp
from login_dialog import LoginDialog


def main():
    root = ctk.CTk()
    dialog = LoginDialog(root)
    dialog.grab_set()
    root.wait_window(dialog)
    if not dialog.authenticated:
        return
    OrderScraperApp(
        root,
        session=dialog.session,
        orders_url=dialog.orders_url_var.get(),
    )
    root.mainloop()


if __name__ == "__main__":
    main()
