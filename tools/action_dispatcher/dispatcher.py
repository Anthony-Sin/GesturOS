import pyautogui
import queue
import time
import threading
from config import Config
from shared_state import state

class ActionDispatcher:
    def __init__(self, data_queue: queue.Queue):
        self.data_queue = data_queue
        self.running = False

        # Cooldowns to prevent spamming actions
        self.last_blink_time = 0
        self.last_jaw_time = 0
        self.last_smile_time = 0

        self.cooldown_blink = Config.BLINK_COOLDOWN
        self.cooldown_jaw = Config.JAW_COOLDOWN
        self.cooldown_smile = Config.SMILE_COOLDOWN

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run)
        thread.start()
        print("Action Dispatcher started.")
        return thread

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                payload = self.data_queue.get(timeout=0.1)

                # Pause action triggers if dictation is active
                if state.get("dictation_active", False) or payload.get('is_locked', False):
                    continue

                blendshapes = payload['blendshapes']

                now = time.time()

                # Check Blink (Closing Eyes) -> Left Click
                blink_left = blendshapes.get('eyeBlinkLeft', 0.0)
                blink_right = blendshapes.get('eyeBlinkRight', 0.0)

                # If both eyes are closed, trigger a left click
                is_blink = (blink_left > Config.BLINK_THRESHOLD and blink_right > Config.BLINK_THRESHOLD)

                if is_blink and (now - self.last_blink_time > self.cooldown_blink):
                    print("Action: Left Click triggered!")
                    pyautogui.click()
                    self.last_blink_time = now

                # Check Jaw Open -> Scroll Down
                jaw_open = blendshapes.get('jawOpen', 0.0)
                if jaw_open > Config.JAW_THRESHOLD and (now - self.last_jaw_time > self.cooldown_jaw):
                    print("Action: Scroll Down triggered!")
                    pyautogui.scroll(-50) # Scroll down (negative value usually)
                    self.last_jaw_time = now

                # Check Smile -> Enter
                # Very useful for submitting forms, opening files, finishing searches
                smile_left = blendshapes.get('mouthSmileLeft', 0.0)
                smile_right = blendshapes.get('mouthSmileRight', 0.0)
                smile_avg = (smile_left + smile_right) / 2.0

                if smile_avg > Config.SMILE_THRESHOLD and (now - self.last_smile_time > self.cooldown_smile):
                    print("Action: Smile triggered! (Enter)")
                    pyautogui.press('enter')
                    self.last_smile_time = now

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in ActionDispatcher: {e}")
