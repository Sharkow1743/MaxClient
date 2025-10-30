import keyring
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Callable, Any, List
from MaxBridge import MaxAPI
import requests
import base64
import mimetypes
from ui import AppUI

class App:
    """
    Handles the application's core logic, state management, and API communication.
    This class is now UI-agnostic.
    """

    def __init__(self):
        self._setup_logging()
        self.logger = logging.getLogger(__name__)

        self.token: Optional[str] = keyring.get_password('maxApp', 'token')
        self.api: Optional[MaxAPI] = None
        self.ui: Optional[AppUI] = None # Forward reference to the UI class in ui.py

        self.state: Dict[str, Any] = {
            'chat': None,
            'messages': {},
            'profile': {},
            'chats': {},
            'profiles': {}
        }

        self._initialize_api()
        if self.is_authenticated():
            self.state['profile'] = getattr(self.api, 'user', {}).get('contact', {})

    def run(self):
        """ The UI's run method will be called from main.py """
        if self.ui:
            pass
        else:
            self.logger.error("UI is not initialized. Cannot run the application.")

    def _initialize_api(self):
        """Initializes the MaxAPI instance with the current token."""
        if self.api:
            self.api.close()
        if self.token:
            self.logger.info("Authentication token loaded, initializing API.")
            self.api = MaxAPI(self.token, on_event=self._handle_event)
        else:
            self.logger.info("No token found, initializing API without token.")
            self.api = MaxAPI(on_event=self._handle_event)

    def _handle_event(self, event: Dict):
        """Handles real-time events from the API websocket."""
        opcode = event.get('opcode')
        payload = event.get('payload', {})
        self.logger.info(f"Received event with opcode {opcode}")

        if opcode == 128:
            message_data = payload.get('message')
            chat_id = payload.get('chatId')
            if chat_id and message_data:
                chat_id_str = str(chat_id)
                messages = self.state['messages'].setdefault(chat_id_str, [])
                if not any(msg['id'] == message_data['id'] for msg in messages):
                    messages.append(message_data)
                    self.logger.debug(f"Added new message {message_data.get('id')} to chat {chat_id_str}")
                if self.ui:
                    self.ui.handle_new_message(chat_id=chat_id)
        else:
            self.logger.debug(f"Unhandled event payload: {payload}")

    def _process_msg(self, msgs: List[Dict]) -> List[Dict]:
        """
        This function is now a simple pass-through.
        All attachment processing is deferred until requested by the UI.
        """
        return msgs

    def _fetch_and_cache_profiles_for_messages(self, messages: List[Dict]):
        """
        Scans messages, finds uncached user profiles, and fetches them in a single batch request.
        """
        if not self.api: return

        profile_cache = self.state['profiles']
        uncached_user_ids = {
            str(msg['sender'])
            for msg in messages
            if 'sender' in msg and str(msg['sender']) not in profile_cache
        }

        if not uncached_user_ids:
            return

        self.logger.info(f"Found {len(uncached_user_ids)} new profiles to fetch.")
        try:
            user_ids_to_fetch = [int(uid) for uid in uncached_user_ids]
            response = self.api.get_contact_details(user_ids_to_fetch)
            profiles = response.get('payload', {}).get('contacts', [])

            for profile in profiles:
                profile_id_str = str(profile.get('id'))
                self.state['profiles'][profile_id_str] = profile
            self.logger.info(f"Successfully cached {len(profiles)} new profiles.")

        except Exception as e:
            self.logger.error(f"Failed to batch fetch profiles: {e}", exc_info=True)


    def is_authenticated(self) -> bool:
        return bool(self.token)

    def auth(self, phone_number: str) -> Callable[[str], bool]:
        self.logger.info(f"Initiating authentication for phone: {phone_number}")
        try:
            self.api.send_verify_code(str(phone_number))
            self.logger.debug("Verification code sent successfully.")
        except Exception as e:
            self.logger.error(f"Failed to send verification code: {e}", exc_info=True)
            raise

        def check_code(code: str) -> bool:
            try:
                self.logger.info("Verifying code...")
                new_token = self.api.check_verify_code(str(code))
                if new_token:
                    keyring.set_password('maxApp', 'token', new_token)
                    self.token = new_token
                    self._initialize_api()
                    self.state['profile'] = getattr(self.api, 'user', {})
                    self.logger.info("Authentication successful. Token saved.")
                    return True
                else:
                    self.logger.warning(f"Authentication failed.")
                    return False
            except Exception as e:
                self.logger.error(f"Error during code verification: {e}", exc_info=True)
                return False
        return check_code

    def send(self, text: str) -> Optional[Dict]:
        if not self.state.get('chat') or not self.api: return None
        try:
            chat_id_str = self.state['chat']
            chat_id_int = int(chat_id_str)
            sent_message = self.api.send_message(chat_id=chat_id_int, text=text, wait_for_response=True)
            sent_message = sent_message.get('payload', {}).get('message')
            if sent_message:
                messages = self.state['messages'].setdefault(chat_id_str, [])
                messages.append(sent_message)
                return sent_message
            return None
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}", exc_info=True)
            return None

    def nav_chat(self, chat_id: str) -> bool:
        if not self.api: return False
        try:
            self.logger.info(f"Navigating to chat {chat_id}")
            self.state['chat'] = chat_id

            history = self.api.get_history(chat_id=int(chat_id), count=50)
            new_messages = history.get('payload', {}).get('messages', [])

            self._fetch_and_cache_profiles_for_messages(new_messages)
            new_messages = self._process_msg(new_messages)

            existing_messages = self.state['messages'].get(chat_id, [])
            message_dict = {msg['id']: msg for msg in existing_messages}
            message_dict.update({msg['id']: msg for msg in new_messages})

            self.state['messages'][chat_id] = sorted(message_dict.values(), key=lambda m: m.get('id', 0))

            if new_messages:
                last_msg_id = new_messages[-1].get('id')
                if last_msg_id:
                    self.api.mark_as_read(chat_id=int(chat_id), message_id=str(last_msg_id))

            self.logger.info(f"Loaded {len(new_messages)} new messages for chat {chat_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to navigate to chat {chat_id}: {e}", exc_info=True)
            return False

    def load_more_messages(self, chat_id: str) -> List[Dict]:
        if not self.api: return []
        messages = self.state['messages'].get(chat_id, [])
        if not messages: return []
        try:
            oldest_message_timestamp = messages[0].get('time')
            history = self.api.get_history(chat_id=int(chat_id), count=50, from_timestamp=oldest_message_timestamp)
            older_messages = history.get('payload', {}).get('messages', [])

            if older_messages and older_messages[0].get('time') != oldest_message_timestamp:
                self._fetch_and_cache_profiles_for_messages(older_messages)
                older_messages = self._process_msg(older_messages)

                self.state['messages'][chat_id] = older_messages + messages
                self.logger.info(f"Loaded {len(older_messages)} older messages.")
                return older_messages

            self.logger.info("No more older messages to load.")
            return []
        except Exception as e:
            self.logger.error(f"Failed to load more messages: {e}", exc_info=True)
            return []

    def get_all_chats(self) -> Dict[str, Any]:
        if not self.api: return {}
        try:
            self.logger.info("Fetching all chats...")
            chats = self.api.get_all_chats()
            self.state['chats'] = chats
            for chat_id in chats: self.api.subscribe_to_chat(int(chat_id))
            self.logger.info(f"Fetched and subscribed to {len(chats)} chats.")
            return chats
        except Exception as e:
            self.logger.error(f"Failed to fetch chats: {e}", exc_info=True)
            return {}

    def get_profile(self, user_id: str) -> Optional[Dict]:
        """Retrieves user profile details FROM THE CACHE."""
        return self.state['profiles'].get(user_id)

    def get_attachment_data_uri(self, chat_id: str, message_id: str, attach_info: Dict) -> Optional[Dict]:
        """
        On-demand download and processing for a single attachment, requested by the UI.
        """
        if not self.api: return None
        self.logger.info(f"Lazy loading attachment for msg {message_id}")

        file_content, filename, mime_type = None, 'download', 'application/octet-stream'

        try:
            attach_type = attach_info.get('_type')
            if attach_type == "PHOTO":
                url = attach_info.get('baseUrl')
                file_content = requests.get(url, timeout=15).content
                mime_type = 'image/jpeg'
                filename = url.split('/')[-1] if url else 'photo.jpg'
            elif attach_type == "VIDEO":
                file_content = self.api.get_video(attach_info.get('videoId'))
                mime_type = 'video/mp4'
                filename = f"{attach_info.get('videoId', 'video')}.mp4"
            elif attach_type == "FILE":
                file_content, filename = self.api.get_file(attach_info.get('fileId'), chat_id, message_id)
                mime_type, _ = mimetypes.guess_type(filename)
                if not mime_type: mime_type = 'application/octet-stream'

            if file_content:
                encoded_content = base64.b64encode(file_content).decode('utf-8')
                return {
                    'data_uri': f"data:{mime_type};base64,{encoded_content}",
                    'filename': filename
                }
        except Exception as e:
            self.logger.error(f"Failed to lazy-load attachment: {e}", exc_info=True)

        return None


    def stop(self):
        self.logger.info("Shutting down App...")
        if self.api: self.api.close()
        self.logger.info("App shutdown complete.")

    def _setup_logging(self):
        logger = logging.getLogger()
        if logger.hasHandlers(): return
        logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        try:
            file_handler = RotatingFileHandler("max_app_debug.log", maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (PermissionError, IOError) as e:
            print(f"Warning: Could not open log file: {e}")