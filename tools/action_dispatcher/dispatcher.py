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

        self.last_blink_time = 0
        self.blink_start_time = None
        self.blink_duration_threshold = self.config.get("BLINK_DURATION_THRESHOLD", 0.25)
        self.cooldown_blink = self.config.get("BLINK_COOLDOWN", 2.0)
        self.blink_threshold = self.config.get("BLINK_THRESHOLD", 0.26)

        # Scrolling thresholds
        self.scroll_brow_threshold = self.config.get("SCROLL_BROW_THRESHOLD", 0.4)
        self.scroll_hold_duration = self.config.get("SCROLL_HOLD_DURATION", 5.0)

        self.scroll_start_time = None
        self.scroll_intent = None # "up" or "down"

        # We will need a thread to handle continuous scrolling when active
        self.scroll_thread = None

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run)
        thread.start()

        self.scroll_thread = threading.Thread(target=self._continuous_scroll_loop, daemon=True)
        self.scroll_thread.start()

        print("Action Dispatcher started.")
        return thread

    def stop(self):
        self.running = False

    def _continuous_scroll_loop(self):
        while self.running:
            scroll_dir = self.shared_state.get("continuous_scroll_active")
            if scroll_dir:
                # Smooth continuous scroll
                if scroll_dir == "up":
                    pyautogui.scroll(100)
                elif scroll_dir == "down":
                    pyautogui.scroll(-100)
                time.sleep(0.05)
            else:
                time.sleep(0.1)

    def _run(self):
        while self.running:
            try:
                payload = self.data_queue.get(timeout=0.1)

                if self.shared_state.get("dictation_active", False):
                    continue

                blendshapes = payload['blendshapes']
                now = time.time()

                # --- Blink Check ---
                blink_left = blendshapes.get('eyeBlinkLeft', 0.0)
                blink_right = blendshapes.get('eyeBlinkRight', 0.0)
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
                            self.blink_start_time = None
                else:
                    self.blink_start_time = None

                # --- Scroll Intent Check ---
                brow_inner_up = blendshapes.get('browInnerUp', 0.0)
                brow_outer_up_l = blendshapes.get('browOuterUpLeft', 0.0)
                brow_outer_up_r = blendshapes.get('browOuterUpRight', 0.0)
                brow_down_l = blendshapes.get('browDownLeft', 0.0)
                brow_down_r = blendshapes.get('browDownRight', 0.0)

                intent_up = (brow_inner_up > self.scroll_brow_threshold or brow_outer_up_l > self.scroll_brow_threshold or brow_outer_up_r > self.scroll_brow_threshold)
                intent_down = (brow_down_l > self.scroll_brow_threshold and brow_down_r > self.scroll_brow_threshold)

                current_intent = None
                if intent_up:
                    current_intent = "up"
                elif intent_down:
                    current_intent = "down"

                if current_intent:
                    if self.scroll_start_time is None or self.scroll_intent != current_intent:
                        self.scroll_start_time = now
                        self.scroll_intent = current_intent
                    else:
                        elapsed = now - self.scroll_start_time
                        if elapsed >= self.scroll_hold_duration:
                            self.shared_state["continuous_scroll_active"] = current_intent
                            self.shared_state["currently_doing"] = f"SCROLLING {current_intent.upper()} (RELAX TO STOP)"
                        else:
                            # Still holding, show countdown
                            remaining = self.scroll_hold_duration - elapsed
                            self.shared_state["currently_doing"] = f"SCROLL {current_intent.upper()} IN {remaining:.1f}s"
                else:
                    # Relaxed
                    if self.shared_state.get("continuous_scroll_active"):
                        # We were scrolling, now stop
                        self.shared_state["continuous_scroll_active"] = None
                        self.shared_state["currently_doing"] = "AWAITING COMMAND"

                    self.scroll_start_time = None
                    self.scroll_intent = None

                    # If we aren't doing anything else important and relaxed,
                    # we could reset "currently_doing", but it might overwrite other states.
                    # Let's only clear it if we were actively counting down
                    if self.scroll_start_time and not self.shared_state.get("continuous_scroll_active"):
                        # This condition implies we aborted countdown, but since scroll_start_time is reset above,
                        # we can't check it here easily unless we track it.
                        pass

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in ActionDispatcher: {e}")
