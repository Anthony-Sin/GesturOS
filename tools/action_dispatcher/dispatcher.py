import pyautogui
import queue
import time
import threading

class ActionDispatcher:
    def __init__(self, data_queue: queue.Queue):
        self.data_queue = data_queue
        self.running = False

        # Cooldowns to prevent spamming actions
        self.last_blink_time = 0
        self.last_jaw_time = 0
        self.last_smile_time = 0

        self.cooldown_blink = 0.5   # seconds
        self.cooldown_jaw = 0.1     # faster scrolling cooldown
        self.cooldown_smile = 1.0   # seconds

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

                if payload.get('is_locked', False):
                    continue

                blendshapes = payload['blendshapes']

                now = time.time()

                # Check Blink -> Click
                # eyeBlinkLeft or eyeBlinkRight > 0.65
                blink_left = blendshapes.get('eyeBlinkLeft', 0.0)
                blink_right = blendshapes.get('eyeBlinkRight', 0.0)

                if (blink_left > 0.65 or blink_right > 0.65) and (now - self.last_blink_time > self.cooldown_blink):
                    print("Action: Click triggered!")
                    pyautogui.click()
                    self.last_blink_time = now

                # Check Jaw Open -> Scroll Down
                # jawOpen > 0.60
                jaw_open = blendshapes.get('jawOpen', 0.0)
                if jaw_open > 0.60 and (now - self.last_jaw_time > self.cooldown_jaw):
                    print("Action: Scroll Down triggered!")
                    pyautogui.scroll(-50) # Scroll down (negative value usually)
                    self.last_jaw_time = now

                # Check Smile -> Browser Back / Escape
                # mouthSmileLeft and mouthSmileRight often combined, or just one
                # MediaPipe gives mouthSmileLeft / mouthSmileRight
                smile_left = blendshapes.get('mouthSmileLeft', 0.0)
                smile_right = blendshapes.get('mouthSmileRight', 0.0)
                smile_avg = (smile_left + smile_right) / 2.0

                if smile_avg > 0.70 and (now - self.last_smile_time > self.cooldown_smile):
                    print("Action: Smile triggered! (Escape/Browser Back)")
                    # We can use browserback or esc. Let's use 'browserback' which PyAutoGUI supports, or fallback to 'esc'.
                    pyautogui.press('browserback') # Sends the multimedia back key
                    self.last_smile_time = now

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in ActionDispatcher: {e}")
