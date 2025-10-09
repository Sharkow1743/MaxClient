# ui.py - The rest of the file is correct, only these methods need updating

import webview
import json
from typing import TYPE_CHECKING, Dict, Callable, Any, Optional, List

if TYPE_CHECKING:
    from app import App

# The Api class from the previous turn is correct and does not need changes.
class Api:
    """
    A completely decoupled API bridge. 
    It holds no complex objects, only the functions it needs to call.
    """
    def __init__(
        self,
        auth_handler: Callable[[str], Callable[[str], bool]],
        send_handler: Callable[[str], Optional[Dict]],
        nav_handler: Callable[[str], bool],
        get_chats_handler: Callable[[], Dict],
        load_more_handler: Callable[[str], List[Dict]]  # Add this line
    ):
        # Store the functions passed in from AppUI
        self._auth_handler = auth_handler
        self._send_handler = send_handler
        self._nav_handler = nav_handler
        self._get_chats_handler = get_chats_handler
        self._load_more_handler = load_more_handler  # Add this line

        self._auth_checker: Optional[Callable[[str], bool]] = None
        
        # Callbacks to be set by AppUI for triggering UI updates
        self.refresh_ui_callback: Callable[[], None] = lambda: None
        self.load_chats_callback: Callable[[], None] = lambda: None
        self.show_main_view_callback: Callable[[], None] = lambda: None

    def start_auth(self, phone: str) -> Dict:
        try:
            self._auth_checker = self._auth_handler(phone)
            return {'success': True}
        except Exception as e:
            print(f"ERROR in start_auth: {e}") 
            return {'success': False, 'error': str(e)}

    def submit_code(self, code: str) -> Dict:
        if self._auth_checker and self._auth_checker(code):
            self.show_main_view_callback()
            return {'success': True}
        return {'success': False}

    def send_message(self, text: str):
        if self._send_handler(text):
            self.refresh_ui_callback()

    def nav_to_chat(self, chat_id: str):
        if self._nav_handler(chat_id):
            self.refresh_ui_callback()

    def load_chats(self):
        """Called from JavaScript to load the initial chat list."""
        self.load_chats_callback()
    
    # --- NEW METHOD ---
    def load_more_messages(self, chat_id: str) -> List[Dict]:
        """
        Calls the app logic to fetch older messages and add them to the state.
        Returns the list of messages that were fetched.
        """
        result = self._load_more_handler(chat_id)
        if result: self.refresh_ui_callback(False)
        return result


class AppUI:
    """Manages the pywebview user interface."""

    def __init__(self, app_logic: 'App'):
        self.app_logic = app_logic
        self.window = None
        self.api = Api(
            auth_handler=self.app_logic.auth,
            send_handler=self.app_logic.send,
            nav_handler=self.app_logic.nav_chat,
            get_chats_handler=self.app_logic.get_all_chats,
            load_more_handler=self.app_logic.load_more_messages # Add this line
        )

    def run(self):
        self.api.refresh_ui_callback = self.refresh_chat_history
        self.api.load_chats_callback = self._js_load_chats
        self.api.show_main_view_callback = self._js_show_main_view
        self.window = webview.create_window(
            'MAX Messenger',
            'web/index.html',
            js_api=self.api,
            width=900,
            height=650,
            min_size=(700, 500)
        )
        webview.start(self.on_shown, debug=True)

    def on_shown(self):
        if self.app_logic.is_authenticated():
            self._js_show_main_view()

    def _js_show_main_view(self):
        """Tells the JavaScript to show the main chat interface AND loads the chats."""
        if self.window:
            # Step 1: Tell JavaScript to switch which view is visible.
            self.window.evaluate_js('showMainView()')
            # Step 2: Immediately tell the API to load the chats. This keeps control in Python.
            self.api.load_chats()

    def _js_load_chats(self):
        if self.window:
            chats = self.api._get_chats_handler()
            chats_json = json.dumps(chats)
            self.window.evaluate_js(f'loadChats({chats_json})')

    def refresh_chat_history(self, scroll_to_bottom = True):
        """
        Gathers all necessary data for the current chat view (messages, chats,
        and all relevant profiles) and sends it to the JavaScript UI.
        """
        if not self.window: return
        chat_id = self.app_logic.state.get('chat')
        if chat_id:
            messages_in_chat = self.app_logic.state['messages'].get(chat_id, [])
            
            # Create a dictionary of only the profiles relevant to this chat view.
            # This is far more efficient than JS calling back for each profile.
            profiles_in_chat = {
                uid: self.app_logic.get_profile(str(uid))
                for msg in messages_in_chat
                # Using the walrus operator (:=) for cleaner code
                if (uid := str(msg.get('sender')))
            }
            
            data = {
                'chatId': chat_id,
                'messages': messages_in_chat,
                'profile': self.app_logic.state.get('profile', {}),
                'chats': self.app_logic.state.get('chats', {}),
                'profilesInChat': profiles_in_chat  # Pass the batch of profiles
            }
            data_json = json.dumps(data)
            self.window.evaluate_js(f'refreshChatHistory({data_json}, {'true' if scroll_to_bottom else 'false'})')

    def handle_new_message(self, **kwargs):
        chat_id = str(kwargs.get('chat_id'))
        current_chat_id = self.app_logic.state.get('chat')
        if chat_id == current_chat_id:
            self.refresh_chat_history()