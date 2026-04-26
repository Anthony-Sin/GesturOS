import time
import platform
import pyautogui
import pyperclip

class IntentRouter:
    def __init__(self, agent):
        self.agent = agent

        # Map intents to lists of natural language variations
        self.intent_patterns = {
            "go_back": ["go back", "previous page", "navigate back", "go to previous"],
            "scroll_down": ["scroll down", "page down", "go down"],
            "scroll_up": ["scroll up", "page up", "go up"],
            "close_this": ["close this", "close window", "exit this", "shut this"],
            "press_tab": ["press tab", "hit tab", "tab over", "next field"],
            "go_home": ["go home", "show desktop", "minimize everything", "desktop"],
            "whats_focused": ["what's focused", "what is focused", "where am i", "what window"],
            "read_this": ["read this", "what does this say", "read it to me", "summarize this page", "what is this page about"]
        }

    def process(self, command: str) -> bool:
        """
        Evaluates the command against hardcoded fast-path intents.
        Returns True if an intent matched and executed, False otherwise.
        """
        command_lower = command.lower()
        matched_intent = None

        for intent_name, patterns in self.intent_patterns.items():
            if any(p in command_lower for p in patterns):
                matched_intent = intent_name
                break

        if not matched_intent:
            return False

        print(f"[Fast-Path Router] Matched intent: {matched_intent}")
        self._execute_intent(matched_intent)
        return True

    def _execute_intent(self, intent: str):
        if intent == "go_back":
            pyautogui.hotkey('alt', 'left')
            self.agent.speak("Going back.")

        elif intent == "scroll_down":
            pyautogui.scroll(-500)
            self.agent.speak("Scrolling down.")

        elif intent == "scroll_up":
            pyautogui.scroll(500)
            self.agent.speak("Scrolling up.")

        elif intent == "close_this":
            pyautogui.hotkey('alt', 'f4')
            self.agent.speak("Closing.")

        elif intent == "press_tab":
            pyautogui.press('tab')

        elif intent == "go_home":
            pyautogui.hotkey('win', 'd')
            self.agent.speak("Going to desktop.")

        elif intent == "whats_focused":
            self._handle_whats_focused()

        elif intent == "read_this":
            self._handle_read_this()

    def _handle_whats_focused(self):
        try:
            title = "Unknown"
            if platform.system() == "Windows":
                import pygetwindow as gw
                active_window = gw.getActiveWindow()
                title = active_window.title if active_window else "Unknown"
            elif platform.system() == "Linux":
                try:
                    from ewmh import EWMH
                    ewmh = EWMH()
                    active_window = ewmh.getActiveWindow()
                    if active_window:
                        title_bytes = ewmh.getWmName(active_window)
                        title = title_bytes.decode('utf-8') if isinstance(title_bytes, bytes) else str(title_bytes)
                except ImportError:
                    pass

            self.agent.speak(f"The currently focused window is: {title}")
        except Exception as e:
            self.agent.speak("I could not determine the focused window.")

    def _handle_read_this(self):
        self.agent.speak("Reading...")
        try:
            # Copy all text from the active window to the clipboard
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.1)
            pyautogui.hotkey('ctrl', 'c')
            time.sleep(0.1)

            copied_text = pyperclip.paste()

            if copied_text and copied_text.strip():
                if len(copied_text) > 1000 and self.agent.client: # Summarize if long
                    prompt = f"Briefly summarize the following text for a blind user:\n\n{copied_text[:5000]}"
                    try:
                        response = self.agent.client.models.generate_content(
                            model='gemini-1.5-flash',
                            contents=prompt
                        )
                        self.agent.speak(response.text)
                    except Exception as e:
                        print(f"Summarization error: {e}")
                        self.agent.speak("I copied the text, but encountered an error summarizing it.")
                else:
                    self.agent.speak(copied_text)
            else:
                self.agent.speak("I could not find any text to read.")
        except Exception as e:
            print(f"Read intent error: {e}")
            self.agent.speak("Sorry, I could not read the text.")
