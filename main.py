from app import App
from ui import AppUI
import flet as ft

def main(page: ft.Page):
    """
    Main entry point for the application.
    Initializes and runs the app with a Flet UI.
    """
    page.title = "MAX Messenger"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # Create the main application logic object
    app_logic = App()

    # Create the UI, passing the app logic and the Flet page
    app_ui = AppUI(app_logic, page)

    # Set the app_logic's UI reference
    app_logic.ui = app_ui

    # Start the UI
    app_ui.run()

if __name__ == "__main__":
    ft.app(target=main)