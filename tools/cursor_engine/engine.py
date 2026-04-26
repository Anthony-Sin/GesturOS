import pyautogui
import queue
import time
import threading
from tools.cursor_engine.one_euro import OneEuroFilter
from tools.interfaces import BaseCursorEngine

class CursorEngine(BaseCursorEngine):
    def __init__(self, data_queue: queue.Queue, config: dict, shared_state: dict, audio_player):
        self.data_queue = data_queue
        self.config = config
        self.shared_state = shared_state
        self.audio_player = audio_player
        self.running = False

        pyautogui.FAILSAFE = False

        self.screen_w, self.screen_h = pyautogui.size()

        self.filter_x = OneEuroFilter(min_cutoff=0.001, beta=0.8)
        self.filter_y = OneEuroFilter(min_cutoff=0.001, beta=0.8)

        self.last_raw_x = None
        self.last_raw_y = None
        self.deadzone_velocity = self.config.get("DEADZONE_VELOCITY", 0.003)

        self.active_zone_x_center = self.config.get("ACTIVE_ZONE_X_CENTER", 0.5)
        self.active_zone_y_center = self.config.get("ACTIVE_ZONE_Y_CENTER", 0.6)
        self.active_zone_width = self.config.get("ACTIVE_ZONE_WIDTH", 0.18)
        self.active_zone_height = self.config.get("ACTIVE_ZONE_HEIGHT", 0.06)

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run)
        thread.start()
        print(f"Cursor Engine started. Screen resolution: {self.screen_w}x{self.screen_h}")
        return thread

    def stop(self):
        self.running = False

    def _normalize_to_active_zone(self, val, center, size):
        min_bound = center - (size / 2)
        max_bound = center + (size / 2)
        val_clamped = max(min_bound, min(val, max_bound))
        normalized = (val_clamped - min_bound) / size
        return normalized

    def _run(self):
        self.was_locked = False
        self.was_looking_away = False

        while self.running:
            try:
                payload = self.data_queue.get(timeout=0.1)

                is_looking_away = payload.get('is_looking_away', False)
                if is_looking_away:
                    if not self.was_looking_away:
                        self.shared_state["currently_doing"] = "TRACKING PAUSED (LOOK AWAY)"
                        self.was_looking_away = True
                    # Skip tracking loop to instantly pause
                    continue
                else:
                    if self.was_looking_away:
                        self.shared_state["currently_doing"] = "AWAITING COMMAND"
                        self.was_looking_away = False

                if self.shared_state.get("dictation_active", False):
                    continue

                if self.shared_state.get("continuous_scroll_active"):
                    continue

                is_locked = payload.get('is_locked', False)

                if is_locked and not self.was_locked:
                    if self.audio_player:
                        self.audio_player.play('lock_engage')
                    self.was_locked = True
                elif not is_locked and self.was_locked:
                    if self.audio_player:
                        self.audio_player.play('lock_release')
                    self.was_locked = False

                nose_tip = payload['nose_tip']
                timestamp = payload['timestamp'] / 1000.0

                raw_x = nose_tip['x']
                raw_y = nose_tip['y']

                skip_movement = False

                if self.last_raw_x is not None and self.last_raw_y is not None:
                    dx = raw_x - self.last_raw_x
                    dy = raw_y - self.last_raw_y
                    velocity = (dx**2 + dy**2)**0.5

                    if velocity < self.deadzone_velocity:
                        skip_movement = True

                lock_progress = payload.get('lock_progress', 0.0)
                if lock_progress > 0.0 or is_locked:
                     self.filter_x.beta = 0.01
                     self.filter_y.beta = 0.01
                else:
                     self.filter_x.beta = 0.8
                     self.filter_y.beta = 0.8

                self.last_raw_x = raw_x
                self.last_raw_y = raw_y

                scaled_x = self._normalize_to_active_zone(1.0 - raw_x, self.active_zone_x_center, self.active_zone_width)
                scaled_y = self._normalize_to_active_zone(raw_y, self.active_zone_y_center, self.active_zone_height)

                target_x = scaled_x * self.screen_w
                target_y = scaled_y * self.screen_h

                # Expose raw mapped target for magnetism logic so it doesn't infinite loop on physical mouse
                self.shared_state["raw_nose_target"] = (target_x, target_y)

                if skip_movement:
                    continue

                # Check for instant snap target from Magnetism
                snap_target = self.shared_state.get("magnet_snap_target")
                if snap_target:
                    # Bypassing filter completely for instant zero-latency snap
                    try:
                        pyautogui.moveTo(int(snap_target[0]), int(snap_target[1]))
                        # Feed the target into the filter so it doesn't jump wildly when releasing
                        self.filter_x(snap_target[0], timestamp)
                        self.filter_y(snap_target[1], timestamp)
                    except Exception:
                        pass
                    continue # Skip normal tracking this frame

                filtered_x = self.filter_x(target_x, timestamp)
                filtered_y = self.filter_y(target_y, timestamp)

                try:
                    pyautogui.moveTo(int(filtered_x), int(filtered_y))
                except Exception as e:
                    pass

            except queue.Empty:
                continue
