import webview
import json
from typing import TYPE_CHECKING, Dict, Callable, Any, Optional, List

if TYPE_CHECKING:
    from app import App

class Api:
    """
    A completely decoupled API bridge.
    """
    def __init__(
        self,
        auth_handler: Callable[[str], Callable[[str], bool]],
        send_handler: Callable[[str], Optional[Dict]],
        nav_handler: Callable[[str], bool],
        get_chats_handler: Callable[[], Dict],
        load_more_handler: Callable[[str], List[Dict]],
        # --- NEW HANDLER FOR LAZY LOADING ---
        get_attachment_handler: Callable[[str, str, Dict], Optional[Dict]]
    ):
        self._auth_handler = auth_handler
        self._send_handler = send_handler
        self._nav_handler = nav_handler
        self._get_chats_handler = get_chats_handler
        self._load_more_handler = load_more_handler
        # --- STORE THE NEW HANDLER ---
        self._get_attachment_handler = get_attachment_handler

        self._auth_checker: Optional[Callable[[str], bool]] = None
        self.refresh_ui_callback: Callable[[], None] = lambda: None
        self.load_chats_callback: Callable[[], None] = lambda: None
        self.show_main_view_callback: Callable[[], None] = lambda: None

    def start_auth(self, phone: str) -> Dict:
        try:
            self._auth_checker = self._auth_handler(phone)
            return {'success': True}
        except Exception as e:
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
        self.load_chats_callback()

    def load_more_messages(self, chat_id: str) -> List[Dict]:
        result = self._load_more_handler(chat_id)
        if result: self.refresh_ui_callback(False)
        return result
    
    # --- NEW API METHOD FOR JAVASCRIPT ---
    def get_attachment(self, chatId: str, messageId: str, attachInfo: Dict) -> Optional[Dict]:
        """
        Called from JS to trigger the on-demand download of an attachment.
        """
        return self._get_attachment_handler(chatId, messageId, attachInfo)


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
            load_more_handler=self.app_logic.load_more_messages,
            # --- WIRE UP THE NEW HANDLER ---
            get_attachment_handler=self.app_logic.get_attachment_data_uri
        )

    def run(self):
        self.api.refresh_ui_callback = self.refresh_chat_history
        self.api.load_chats_callback = self._js_load_chats
        self.api.show_main_view_callback = self._js_show_main_view
        self.window = webview.create_window(
            'MAX Messenger',
            'web/index.html',
            js_api=self.api,
            width=900, height=650, min_size=(700, 500)
        )
        webview.start(self.on_shown, debug=True)

    def on_shown(self):
        if self.app_logic.is_authenticated():
            self._js_show_main_view()

    def _js_show_main_view(self):
        if self.window:
            self.window.evaluate_js('showMainView()')
            self.api.load_chats()

    def _js_load_chats(self):
        if self.window:
            chats = self.api._get_chats_handler()
            chats_json = json.dumps(chats)
            self.window.evaluate_js(f'loadChats({chats_json})')

    def refresh_chat_history(self, scroll_to_bottom=True):
        if not self.window: return
        chat_id = self.app_logic.state.get('chat')
        if chat_id:
            messages_in_chat = self.app_logic.state['messages'].get(chat_id, [])
            
            # This is now much faster as get_profile is just a cache lookup.
            profiles_in_chat = {
                uid: self.app_logic.get_profile(str(uid))
                for msg in messages_in_chat
                if (uid := str(msg.get('sender')))
            }
            
            data = {
                'chatId': chat_id,
                'messages': messages_in_chat,
                'profile': self.app_logic.state.get('profile', {}),
                'chats': self.app_logic.state.get('chats', {}),
                'profilesInChat': profiles_in_chat
            }
            data_json = json.dumps(data, default=str) # Use default=str for safety
            self.window.evaluate_js(f'refreshChatHistory({data_json}, {str(scroll_to_bottom).lower()})')

    def handle_new_message(self, **kwargs):
        chat_id = str(kwargs.get('chat_id'))
        current_chat_id = self.app_logic.state.get('chat')
        if chat_id == current_chat_id:
            self.refresh_chat_history()