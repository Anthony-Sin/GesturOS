import pyautogui
import queue
import time
import threading
from tools.interfaces import BaseActionDispatcher

class ActionDispatcher(BaseActionDispatcher):
    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict, audio_player):
        self.data_queue = data_queue
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player
        self.running = False

        # Cooldowns to prevent spamming actions
        self.last_blink_time = 0

        self.blink_start_time = None
        self.blink_duration_threshold = self.config.get("BLINK_DURATION_THRESHOLD", 0.4)

        self.cooldown_blink = self.config.get("BLINK_COOLDOWN", 2.0)
        self.blink_threshold = self.config.get("BLINK_THRESHOLD", 0.35)

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
                if self.shared_state.get("dictation_active", False) or payload.get('is_locked', False):
                    continue

                blendshapes = payload['blendshapes']

                now = time.time()

                # Check Blink (Closing Eyes) -> Left Click
                blink_left = blendshapes.get('eyeBlinkLeft', 0.0)
                blink_right = blendshapes.get('eyeBlinkRight', 0.0)

                # If both eyes are closed, track duration to prevent false positives from natural blinks
                is_blink = (blink_left > self.blink_threshold and blink_right > self.blink_threshold)

                if is_blink:
                    if self.blink_start_time is None:
                        self.blink_start_time = now
                    else:
                        duration = now - self.blink_start_time
                        if duration >= self.blink_duration_threshold and (now - self.last_blink_time > self.cooldown_blink):
                            print("Action: Left Click triggered!")
                            if self.audio_player:
                                self.audio_player.play('click')
                            pyautogui.click()
                            self.last_blink_time = now
                            self.blink_start_time = None # Reset after click
                else:
                    # Eyes are open, reset the blink duration tracker
                    self.blink_start_time = None

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in ActionDispatcher: {e}")
