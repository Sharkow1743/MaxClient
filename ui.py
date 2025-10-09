import dearpygui.dearpygui as dpg
import threading
import time
from typing import TYPE_CHECKING, List, Dict

if TYPE_CHECKING:
    from app import App

class AppUI:
    """
    Manages the Dear PyGui user interface, including windows, widgets, and callbacks.
    """

    def __init__(self, app_logic: 'App'):
        self.app_logic = app_logic
        self._auth_checker = None
        self._is_loading_more = False # Flag to prevent multiple load requests
        self._next_frame_calls = [] # A queue for functions to run on the next frame

    def _queue_next_frame(self, func):
        """Adds a function to be called at the start of the next frame."""
        self._next_frame_calls.append(func)

    def run(self):
        """
        Initializes DPG, creates the UI, and starts the main render loop.
        """
        self._setup_dpg()
        self._create_windows()

        if self.app_logic.is_authenticated():
            dpg.show_item("Main")
            self.load_chats()
        else:
            dpg.show_item("AuthWindow")

        dpg.create_viewport(title='MAX Messenger', width=900, height=650, min_width=700, min_height=500)
        dpg.setup_dearpygui()
        dpg.show_viewport()
        dpg.set_primary_window("Main", True)

        while dpg.is_dearpygui_running():
            # Process any queued calls for this frame
            for call in self._next_frame_calls:
                call()
            self._next_frame_calls.clear()

            if dpg.get_y_scroll("History") < 10 and not self._is_loading_more:
                self._trigger_load_more()

            self._resize_handler()
            dpg.render_dearpygui_frame()

        self.app_logic.stop()
        dpg.destroy_context()

    def _setup_dpg(self):
        dpg.create_context()
        with dpg.font_registry():
            with dpg.font("ubuntu.otf", 20, tag='ubuntu') as ubuntu:
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Default)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Cyrillic)
        dpg.bind_font("ubuntu")

    def _create_windows(self):
        with dpg.window(tag="AuthWindow", label="Login to Max", no_collapse=True, modal=True, show=False):
            dpg.add_input_text(tag="AuthPhone", default_value="+", callback=self.start_auth, on_enter=True)
            dpg.add_button(label="Send Code", callback=self.start_auth, width=-1)
            dpg.add_text("", tag="AuthStatus")
            with dpg.group(tag="AuthCodeGroup", show=False):
                dpg.add_input_text(tag="AuthCode", decimal=True, callback=self.submit_code, on_enter=True)
                dpg.add_button(label="Submit Code", callback=self.submit_code, width=-1)

        with dpg.window(tag="Main", no_scrollbar=True, no_scroll_with_mouse=True, show=False):
            with dpg.group(horizontal=True):
                with dpg.child_window(tag="Nav", width=180):
                    with dpg.child_window(tag="NavContent", width=-1, height=-1): pass
                with dpg.child_window(tag="Chat", width=-1, height=-1):
                    dpg.add_text("Select a chat", tag="ChatTitle")
                    with dpg.child_window(tag="History", height=-60, border=False):
                        with dpg.group(tag="HistoryContent"): pass
                    with dpg.child_window(tag="Input", height=60, no_scrollbar=True):
                        with dpg.group(horizontal=True):
                            dpg.add_input_text(multiline=True, height=-1, tag="InputText", on_enter=True,
                                               ctrl_enter_for_new_line=True, callback=self.send, width=-100)
                            dpg.add_button(label="Send", width=-1, height=-1, callback=self.send)

    def send(self, sender, app_data, user_data):
        text = dpg.get_value("InputText")
        if text.strip() and self.app_logic.state.get('chat'):
            if self.app_logic.send(text):
                dpg.set_value("InputText", "")
                self.refresh_chat_history(self.app_logic.state['chat'], scroll_to_bottom=True)

    def nav_to_chat(self, sender, app_data, user_data):
        chat_id = user_data
        if self.app_logic.nav_chat(chat_id):
            # Prevent "load more" from triggering while we refresh the chat view
            self._is_loading_more = True
            title = self.app_logic.state['chats'].get(chat_id, {}).get('title', f"Chat {chat_id}")
            dpg.set_value("ChatTitle", title)
            self.refresh_chat_history(chat_id, scroll_to_bottom=True)
        else:
            dpg.set_value("ChatTitle", "Failed to load chat")

    def refresh_chat_history(self, chat_id: str, scroll_to_bottom: bool = False):
        dpg.delete_item("HistoryContent", children_only=True)
        messages = self.app_logic.state['messages'].get(chat_id, [])
        my_id = self.app_logic.state['profile'].get('id')
        
        for msg in messages:
            sender_id = str(msg.get('sender'))
            sender_name = 'You' if str(my_id) == sender_id else 'Unknown'
            if str(my_id) != sender_id:
                profile = self.app_logic.get_profile(sender_id)
                sender_name = profile.get('names', [{}])[0].get('name', 'Error') if profile else 'Unknown'
            
            text = msg.get('text') or '[NO_TEXT]'
            dpg.add_text(f"[{sender_name}] {text}", parent="HistoryContent", wrap=500)

        if scroll_to_bottom:
            def scroll_and_unlock_loading():
                dpg.set_y_scroll('History', dpg.get_y_scroll_max('History'))
                self._is_loading_more = False
            
            self._queue_next_frame(scroll_and_unlock_loading)

    def load_chats(self):
        dpg.delete_item("NavContent", children_only=True)
        chats = self.app_logic.get_all_chats()
        for chat_id, chat_info in chats.items():
            title = chat_info.get('title', f"Chat {chat_id}")
            label = title[:25] + "..." if len(title) > 25 else title
            dpg.add_button(label=label, callback=self.nav_to_chat, user_data=chat_id,
                           parent="NavContent", width=-1)

    def start_auth(self):
        phone = dpg.get_value("AuthPhone")
        dpg.set_value("AuthStatus", "Sending code...")
        threading.Thread(target=self._start_auth_thread, args=(phone,), daemon=True).start()

    def _start_auth_thread(self, phone: str):
        try:
            self._auth_checker = self.app_logic.auth(phone)
            dpg.set_value("AuthStatus", "Code sent! Enter it below.")
            dpg.show_item("AuthCodeGroup")
        except Exception as e:
            dpg.set_value("AuthStatus", f"Error: {e}")

    def submit_code(self):
        code = dpg.get_value("AuthCode")
        dpg.set_value("AuthStatus", "Verifying code...")
        threading.Thread(target=self._submit_code_thread, args=(code,), daemon=True).start()

    def _submit_code_thread(self, code: str):
        if self._auth_checker(code):
            dpg.set_value("AuthStatus", "Login successful!")
            time.sleep(1)
            dpg.hide_item("AuthWindow")
            dpg.show_item("Main")
            self.load_chats()
        else:
            dpg.set_value("AuthStatus", "Invalid code. Please try again.")

    def handle_new_message(self, sender, app_data, user_data):
        chat_id = str(user_data['chat_id'])
        current_chat_id = self.app_logic.state.get('chat')
        if chat_id == current_chat_id:
            # We don't need to lock the loading flag here as the user is already at the bottom
            self.refresh_chat_history(chat_id, scroll_to_bottom=True)
            
    def _trigger_load_more(self):
        self._is_loading_more = True
        chat_id = self.app_logic.state.get('chat')
        if not chat_id:
            self._is_loading_more = False
            return
        
        scroll_max_before = dpg.get_y_scroll_max("History")
        threading.Thread(target=self._load_more_thread, args=(chat_id, scroll_max_before), daemon=True).start()

    def _load_more_thread(self, chat_id: str, scroll_max_before: float):
        older_messages = self.app_logic.load_more_messages(chat_id)
        if older_messages:
            self._on_more_messages_loaded(user_data={
                'chat_id': chat_id,
            }, sender = None, app_data = None)
        else:
            self._is_loading_more = False

    def _on_more_messages_loaded(self, sender, app_data, user_data):
        chat_id = user_data['chat_id']
        
        self.refresh_chat_history(chat_id, scroll_to_bottom=False)

    def _resize_handler(self):
        if not dpg.is_item_shown("Main"): return

        vp_width, vp_height = dpg.get_viewport_width(), dpg.get_viewport_height()
        nav_width = 180
        chat_width = max(0, vp_width - nav_width - 30)
        dpg.configure_item("Nav", width=nav_width)
        dpg.configure_item("Chat", width=chat_width)
        
        overhead = 100
        chat_total_height = max(0, vp_height - overhead)
        if chat_total_height > 0:
            input_height = 60
            history_height = chat_total_height - input_height
            dpg.configure_item("History", height=history_height)
            dpg.configure_item("Input", height=input_height)