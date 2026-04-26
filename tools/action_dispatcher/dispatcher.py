import pyautogui
import queue
import time
import threading
import logging
from tools.interfaces import BaseActionDispatcher

logger = logging.getLogger(__name__)

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
        self.scroll_reset_after_activations = max(
            1, int(self.config.get("SCROLL_RESET_AFTER_ACTIVATIONS", 4))
        )
        self.scroll_reset_cooldown = max(
            0.0, float(self.config.get("SCROLL_RESET_COOLDOWN", 0.9))
        )

        self.scroll_start_time = None
        self.scroll_intent = None # "up" or "down"
        self.scroll_activation_count = 0
        self.scroll_reset_until = 0.0

        # We will need a thread to handle continuous scrolling when active
        self.scroll_thread = None

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run)
        thread.start()

        self.scroll_thread = threading.Thread(target=self._continuous_scroll_loop, daemon=True)
        self.scroll_thread.start()

        logger.info("Action Dispatcher started.")
        return thread

    def stop(self):
        self.running = False

    def _trigger_scroll_reset(self, now: float):
        self.scroll_activation_count = 0
        self.scroll_reset_until = now + self.scroll_reset_cooldown
        self.scroll_start_time = None
        self.scroll_intent = None
        self.shared_state["continuous_scroll_active"] = None
        self.shared_state["currently_doing"] = "BROW RESET (RELAX)"

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
                            logger.info("Action: Left Click triggered via blink!")
                            if self.audio_player:
                                self.audio_player.play('click')
                            pyautogui.click()
                            self.shared_state["clicks_saved"] = self.shared_state.get("clicks_saved", 0) + 1
                            self.last_blink_time = now
                            self.blink_start_time = None
                else:
                    self.blink_start_time = None

                if now < self.scroll_reset_until:
                    self.shared_state["continuous_scroll_active"] = None
                    continue

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
                            if self.shared_state.get("continuous_scroll_active") != current_intent:
                                self.scroll_activation_count += 1
                                if self.scroll_activation_count >= self.scroll_reset_after_activations:
                                    self._trigger_scroll_reset(now)
                                    continue
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
                    elif self.shared_state.get("currently_doing") == "BROW RESET (RELAX)":
                        self.shared_state["currently_doing"] = "AWAITING COMMAND"

                    self.scroll_start_time = None
                    self.scroll_intent = None

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in ActionDispatcher: {e}")
