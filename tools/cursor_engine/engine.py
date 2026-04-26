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

        # Disable failsafe to prevent edge-case crashes
        pyautogui.FAILSAFE = False

        self.screen_w, self.screen_h = pyautogui.size()

        # 1 Euro Filter for advanced jitter-free smoothing
        self.filter_x = OneEuroFilter(min_cutoff=0.01, beta=0.8)
        self.filter_y = OneEuroFilter(min_cutoff=0.01, beta=0.8)

        self.last_raw_x = None
        self.last_raw_y = None
        self.deadzone_velocity = self.config.get("DEADZONE_VELOCITY", 0.003)

        # Magnetic target integration
        self.magnetic_pull = (0, 0)

        # Active Zone Multiplier Configuration
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
        # Calculate min and max bounds for the active zone
        min_bound = center - (size / 2)
        max_bound = center + (size / 2)

        # Clamp the value to the active zone bounds
        val_clamped = max(min_bound, min(val, max_bound))

        # Normalize to [0, 1] within the active zone
        normalized = (val_clamped - min_bound) / size
        return normalized

    def _run(self):
        self.was_locked = False

        while self.running:
            try:
                # Use a small timeout so we can periodically check self.running
                payload = self.data_queue.get(timeout=0.1)

                # Pause cursor tracking if dictation is active
                if self.shared_state.get("dictation_active", False):
                    continue

                is_locked = payload.get('is_locked', False)

                # Handle drag and drop via lock state
                if is_locked and not self.was_locked:
                    # Just entered lock state, press mouse down for dragging
                    if self.audio_player:
                        self.audio_player.play('lock_engage')
                    pyautogui.mouseDown()
                    self.was_locked = True
                elif not is_locked and self.was_locked:
                    # Just exited lock state, release mouse
                    if self.audio_player:
                        self.audio_player.play('lock_release')
                    pyautogui.mouseUp()
                    self.was_locked = False

                nose_tip = payload['nose_tip']
                timestamp = payload['timestamp'] / 1000.0 # seconds for the filter

                raw_x = nose_tip['x']
                raw_y = nose_tip['y']

                skip_movement = False

                if self.last_raw_x is not None and self.last_raw_y is not None:
                    dx = raw_x - self.last_raw_x
                    dy = raw_y - self.last_raw_y
                    velocity = (dx**2 + dy**2)**0.5

                    # Micro-deadzone: completely ignore jitter if trying to hold perfectly still
                    if velocity < self.deadzone_velocity:
                        skip_movement = True

                # We use 1 Euro filter which inherently handles slowdowns nicely.
                # But to add an 'ultra-precision' effect while locking, we can dynamically adjust the beta.
                lock_progress = payload.get('lock_progress', 0.0)
                if lock_progress > 0.0 or is_locked:
                     self.filter_x.beta = 0.1
                     self.filter_y.beta = 0.1
                else:
                     self.filter_x.beta = 0.8
                     self.filter_y.beta = 0.8

                if skip_movement:
                    continue

                self.last_raw_x = raw_x
                self.last_raw_y = raw_y

                # Apply Active Zone scaling (invert X because webcam is mirrored)
                scaled_x = self._normalize_to_active_zone(1.0 - raw_x, self.active_zone_x_center, self.active_zone_width)
                scaled_y = self._normalize_to_active_zone(raw_y, self.active_zone_y_center, self.active_zone_height)

                # Map to screen coordinates
                target_x = scaled_x * self.screen_w
                target_y = scaled_y * self.screen_h

                # Add Magnetic Pull (from predictive magnetism thread)
                mx, my = self.magnetic_pull
                target_x += mx
                target_y += my

                # Apply 1 Euro Filter (dynamically handles slow jitter vs fast tracking)
                filtered_x = self.filter_x(target_x, timestamp)
                filtered_y = self.filter_y(target_y, timestamp)

                # Move physical mouse
                try:
                    pyautogui.moveTo(int(filtered_x), int(filtered_y))
                except Exception as e:
                    print(f"Failed to move mouse: {e}")

            except queue.Empty:
                continue
