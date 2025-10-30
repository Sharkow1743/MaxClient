import flet as ft
from typing import TYPE_CHECKING, Optional, Dict, Callable
import datetime

if TYPE_CHECKING:
    from app import App

class MessageControl(ft.Row):
    def __init__(self, message: Dict, is_me: bool, profile: Optional[Dict]):
        super().__init__()
        self.vertical_alignment = "start"
        self.alignment = ft.MainAxisAlignment.END if is_me else ft.MainAxisAlignment.START

        sender_name = "You" if is_me else profile['names'][0]['name']

        message_text = message.get('text', '')

        try:
            time_value = message.get('time')
            if isinstance(time_value, (int, float)):
                timestamp = datetime.datetime.fromtimestamp(time_value).strftime('%Y-%m-%d %H:%M')
            else:
                timestamp = "No timestamp"
        except (OSError, TypeError, ValueError):
            timestamp = "No timestamp available"

        message_content = ft.Column(
            [
                ft.Text(sender_name, weight=ft.FontWeight.BOLD),
                ft.Text(message_text, selectable=True),
                ft.Text(timestamp, size=10, color=ft.Colors.GREY_500),
            ],
            spacing=2
        )

        avatar = ft.CircleAvatar(
            content=ft.Text(self.get_initials(sender_name)),
            bgcolor=ft.Colors.BLUE_GREY_200 if is_me else ft.Colors.GREEN_200,
        )

        self.controls = [avatar, message_content] if not is_me else [message_content, avatar]

    def get_initials(self, name: str) -> str:
        if not name:
            return "?"
        parts = name.split()
        if len(parts) > 1:
            return (parts[0][0] + parts[-1][0]).upper()
        elif len(parts) == 1 and len(parts[0]) > 0:
            return parts[0][0].upper()
        return "?"


class AppUI:
    """Manages the Flet user interface."""

    def __init__(self, app_logic: 'App', page: ft.Page):
        self.app_logic = app_logic
        self.page = page
        self._auth_checker: Optional[Callable[[str], bool]] = None

        # UI Controls
        self.phone_input = ft.TextField(label="Phone Number", autofocus=True)
        self.code_input = ft.TextField(label="Verification Code", visible=False)
        self.auth_button = ft.ElevatedButton(text="Send Code", on_click=self.start_auth)
        self.auth_view = ft.Column(
            controls=[
                ft.Text("Sign In", size=30),
                self.phone_input,
                self.code_input,
                self.auth_button
            ],
            spacing=20,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )

        self.chat_list = ft.ListView(expand=1, spacing=10, padding=20)
        self.message_list = ft.ListView(expand=1, spacing=10, padding=20, auto_scroll=True)
        self.message_input = ft.TextField(hint_text="Type a message...", expand=True)
        self.send_button = ft.IconButton(icon=ft.Icons.SEND, on_click=self.send_message)

        self.chat_view = ft.Column(
            controls=[
                self.message_list,
                ft.Row(controls=[self.message_input, self.send_button])
            ],
            visible=False,
            expand=True
        )

        self.main_layout = ft.Row(
            controls=[
                ft.Column(controls=[self.chat_list], width=300),
                self.chat_view
            ],
            expand=True,
            visible=False
        )

    def run(self):
        self.page.add(self.auth_view, self.main_layout)
        if self.app_logic.is_authenticated():
            self.show_main_view()
        self.page.update()

    def start_auth(self, e):
        try:
            self._auth_checker = self.app_logic.auth(self.phone_input.value)
            self.phone_input.visible = False
            self.code_input.visible = True
            self.auth_button.text = "Submit Code"
            self.auth_button.on_click = self.submit_code
            self.page.update()
        except Exception as ex:
            self.page.snack_bar = ft.SnackBar(ft.Text(f"Error: {ex}"), open=True)
            self.page.update()

    def submit_code(self, e):
        if self._auth_checker and self._auth_checker(self.code_input.value):
            self.show_main_view()
        else:
            self.page.snack_bar = ft.SnackBar(ft.Text("Authentication failed."), open=True)
            self.page.update()

    def show_main_view(self):
        self.auth_view.visible = False
        self.main_layout.visible = True
        self.chat_view.visible = True
        self.load_chats()
        self.page.update()

    def load_chats(self):
        chats = self.app_logic.get_all_chats()
        for chat_id, chat_data in chats.items():
            def on_chat_click(e, cid=chat_id):
                self.nav_to_chat(cid)

            self.chat_list.controls.append(
                ft.ListTile(
                    title=ft.Text(chat_data.get('title', 'Unknown Chat')),
                    on_click=on_chat_click
                )
            )
        self.page.update()

    def nav_to_chat(self, chat_id: str):
        if self.app_logic.nav_chat(chat_id):
            self.refresh_chat_history()

    def send_message(self, e):
        text = self.message_input.value
        if text:
            if self.app_logic.send(text):
                self.message_input.value = ""
                self.refresh_chat_history()
        self.page.update()

    def refresh_chat_history(self):
        self.message_list.controls.clear()
        chat_id = self.app_logic.state.get('chat')
        if chat_id:
            messages_in_chat = self.app_logic.state['messages'].get(chat_id, [])
            my_profile_id = str(self.app_logic.state.get('profile', {}).get('id'))

            for msg in messages_in_chat:
                sender_id = str(msg.get('sender'))
                is_me = sender_id == my_profile_id
                profile = self.app_logic.get_profile(sender_id)
                self.message_list.controls.append(MessageControl(msg, is_me, profile))

        self.page.update()

    def handle_new_message(self, chat_id: str):
        current_chat_id = self.app_logic.state.get('chat')
        if str(chat_id) == current_chat_id:
            self.refresh_chat_history()