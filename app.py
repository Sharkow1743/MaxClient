import keyring
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Callable, Any, List

from MaxBridge import MaxAPI
from ui import AppUI

class App:
    """
    Handles the application's core logic, state management, and API communication.
    """

    def __init__(self):
        self._setup_logging()
        self.logger = logging.getLogger(__name__)

        self.token: Optional[str] = keyring.get_password('maxApp', 'token')
        self.api: Optional[MaxAPI] = None
        # The UI is now an instance of AppUI
        self.ui: Optional[AppUI] = None

        self.state: Dict[str, Any] = {
            'chat': None,          # Current active chat ID
            'messages': {},        # {chat_id: [message_dict, ...]}
            'profile': {},         # User profile info
            'chats': {},           # Cached chats: {chat_id: chat_info}
            'profiles': {}         # Cached contact profiles: {user_id: profile_info}
        }

        self._initialize_api()
        if self.is_authenticated():
            self.state['profile'] = getattr(self.api, 'user', {})['contact']

        # The App creates the UI, passing a reference to itself.
        self.ui = AppUI(self)

    def run(self):
        """Starts the user interface and the application's main loop."""
        if self.ui:
            self.ui.run()
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
            self.logger.info("No token found. API not initialized.")
            self.api = None

    def _handle_event(self, event: Dict):
        """Handles real-time events from the API websocket."""
        opcode = event.get('opcode')
        payload = event.get('payload', {})
        self.logger.info(f"Received event with opcode {opcode}")

        if opcode == 128:  # New message event
            message_data = payload.get('message')
            chat_id = payload.get('chatId')

            if chat_id and message_data:
                chat_id_str = str(chat_id)
                messages = self.state['messages'].setdefault(chat_id_str, [])
                if not any(msg['id'] == message_data['id'] for msg in messages):
                    messages.append(message_data)
                    self.logger.debug(f"Added new message {message_data.get('id')} to chat {chat_id_str}")

                # Instead of using dpg.queue_main_callback, we directly call the UI handler method.
                # pywebview's evaluate_js is thread-safe, so this is safe to do.
                if self.ui:
                    self.ui.handle_new_message(chat_id=chat_id)
        else:
            self.logger.debug(f"Unhandled event payload: {payload}")

    def is_authenticated(self) -> bool:
        """Checks if a user token exists."""
        return self.token is not None

    def auth(self, phone_number: str) -> Callable[[str], bool]:
        """
        Starts the authentication flow.
        Returns a 'checker' function that the UI can call to verify the code.
        """
        self.logger.info(f"Initiating authentication for phone: {phone_number}")
        try:
            # A temporary API instance is used for the auth flow
            with MaxAPI() as temp_api:
                temp_api.send_vertify_code(str(phone_number))
            self.logger.debug("Verification code sent successfully.")
        except Exception as e:
            self.logger.error(f"Failed to send verification code: {e}", exc_info=True)
            raise

        def check_code(code: str) -> bool:
            try:
                self.logger.info("Verifying code...")
                with MaxAPI() as temp_api:
                    result = temp_api.check_vertify_code(str(code))

                self.logger.debug(f"Auth response: {result}")
                new_token = result.get('token') or result.get('payload', {}).get('token')

                if new_token:
                    keyring.set_password('maxApp', 'token', new_token)
                    self.token = new_token
                    self._initialize_api()
                    self.state['profile'] = getattr(self.api, 'user', {})
                    self.logger.info("Authentication successful. Token saved.")
                    return True
                else:
                    self.logger.warning(f"Authentication failed. Response: {result}")
                    return False
            except Exception as e:
                self.logger.error(f"Error during code verification: {e}", exc_info=True)
                return False

        return check_code

    def send(self, text: str) -> Optional[Dict]:
        """Sends a message and updates local state immediately."""
        if not self.state.get('chat') or not self.api:
            self.logger.warning("Cannot send message: no active chat or not authenticated.")
            return None
        try:
            chat_id_str = self.state['chat']
            chat_id_int = int(chat_id_str)
            self.logger.debug(f"Sending message to chat {chat_id_int}")
            
            # The API call returns the sent message object
            sent_message = self.api.send_message(chat_id=chat_id_int, text=text, wait_for_response=True)
            sent_message = sent_message.get('payload', {}).get('message')
            
            # Immediately add the new message to our state for instant UI update
            if sent_message:
                messages = self.state['messages'].setdefault(chat_id_str, [])
                messages.append(sent_message)
                self.logger.info(f"Message {sent_message.get('id')} sent and added to state.")
                return sent_message
            return None
        except Exception as e:
            self.logger.error(f"Failed to send message: {e}", exc_info=True)
            return None

    def nav_chat(self, chat_id: str) -> bool:
        """Loads message history for a given chat and sets it as active."""
        if not self.api:
            return False
        try:
            self.logger.info(f"Navigating to chat {chat_id}")
            self.state['chat'] = chat_id
            
            history = self.api.get_history(chat_id=int(chat_id), count=50)
            new_messages = history.get('payload', {}).get('messages', [])
            
            existing_messages = self.state['messages'].get(chat_id, [])
            message_dict = {msg['id']: msg for msg in existing_messages}
            message_dict.update({msg['id']: msg for msg in new_messages})
            
            # Sort messages by ID to ensure correct order
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
        """Fetches older messages for a chat to enable infinite scrolling."""
        if not self.api:
            return []

        messages = self.state['messages'].get(chat_id, [])
        if not messages:
            return [] # Nothing to load before

        try:
            oldest_message_timestamp = messages[0].get('time')
            self.logger.info(f"Loading messages for chat {chat_id} before message timestamp {oldest_message_timestamp}")

            history = self.api.get_history(chat_id=int(chat_id), count=50, from_timestamp=oldest_message_timestamp)
            older_messages = history.get('payload', {}).get('messages', [])

            if older_messages and not older_messages[0].get('time') == oldest_message_timestamp:
                # Prepend older messages to the existing list
                self.state['messages'][chat_id] = older_messages + messages
                self.logger.info(f"Loaded {len(older_messages)} older messages.")
                return older_messages
            
            self.logger.info("No more older messages to load.")
            return False
        except Exception as e:
            self.logger.error(f"Failed to load more messages: {e}", exc_info=True)
            return []

    def get_all_chats(self) -> Dict[str, Any]:
        """Fetches and caches all user chats."""
        if not self.api:
            return {}
        try:
            self.logger.info("Fetching all chats...")
            chats = self.api.get_all_chats()
            self.state['chats'] = chats
            
            for chat_id in chats:
                self.api.subscribe_to_chat(int(chat_id))
                
            self.logger.info(f"Fetched and subscribed to {len(chats)} chats.")
            return chats
        except Exception as e:
            self.logger.error(f"Failed to fetch chats: {e}", exc_info=True)
            return {}

    def get_profile(self, user_id: str) -> Optional[Dict]:
        """Retrieves user profile details, using a cache."""
        if user_id in self.state['profiles']:
            return self.state['profiles'][user_id]
        if not self.api:
            return None
        
        try:
            response = self.api.get_contact_details([int(user_id)])
            profile = response.get('payload', {}).get('contacts', [None])[0]
            if profile:
                self.state['profiles'][user_id] = profile
            return profile
        except Exception as e:
            self.logger.error(f"Failed to get profile for ID {user_id}: {e}")
            return None

    def stop(self):
        """Cleans up resources upon application exit."""
        self.logger.info("Shutting down App...")
        if self.api:
            self.api.close()
        self.logger.info("App shutdown complete.")
        
    def _setup_logging(self):
        """Configures logging to file and console."""
        logger = logging.getLogger()
        if logger.hasHandlers():
            # Avoid adding duplicate handlers if this is called more than once
            return
        logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        try:
            file_handler = RotatingFileHandler(
                "max_app_debug.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (PermissionError, IOError) as e:
            # Log to console if file logging fails
            print(f"Warning: Could not open log file due to an error: {e}")