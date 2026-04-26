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
            "go_home": ["go home", "show desktop", "minimize everything", "desktop"]
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
