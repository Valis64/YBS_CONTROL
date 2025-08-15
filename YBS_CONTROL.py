import customtkinter as ctk

from ui.order_app import OrderScraperApp


def main():
    root = ctk.CTk()
    OrderScraperApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
