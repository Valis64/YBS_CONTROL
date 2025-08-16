import customtkinter as ctk

# Configure dark appearance and theme before creating any widgets
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

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
