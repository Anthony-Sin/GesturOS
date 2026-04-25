import pyautogui
import queue
import time
import threading
from config import Config

class CursorEngine:
    def __init__(self, data_queue: queue.Queue):
        self.data_queue = data_queue
        self.running = False

        # Disable failsafe to prevent edge-case crashes
        pyautogui.FAILSAFE = False

        self.screen_w, self.screen_h = pyautogui.size()

        # Exponential Moving Average state
        self.ema_x = None
        self.ema_y = None

        # Dynamic Sensitivity Configuration
        self.base_alpha = Config.BASE_ALPHA
        self.precision_alpha = Config.PRECISION_ALPHA
        self.alpha = self.base_alpha

        # Velocity tracking for dynamic sensitivity
        self.last_raw_x = None
        self.last_raw_y = None
        self.velocity_threshold = Config.VELOCITY_THRESHOLD

        # Active Zone Multiplier Configuration
        self.active_zone_x_center = Config.ACTIVE_ZONE_X_CENTER
        self.active_zone_y_center = Config.ACTIVE_ZONE_Y_CENTER
        self.active_zone_width = Config.ACTIVE_ZONE_WIDTH
        self.active_zone_height = Config.ACTIVE_ZONE_HEIGHT

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

                is_locked = payload.get('is_locked', False)

                # Handle drag and drop via lock state
                if is_locked and not self.was_locked:
                    # Just entered lock state, press mouse down for dragging
                    pyautogui.mouseDown()
                    self.was_locked = True
                elif not is_locked and self.was_locked:
                    # Just exited lock state, release mouse
                    pyautogui.mouseUp()
                    self.was_locked = False

                # We no longer `continue` (skip) on lock. We allow the cursor to move
                # while locked so the user can drag the folder/window around.

                nose_tip = payload['nose_tip']

                raw_x = nose_tip['x']
                raw_y = nose_tip['y']

                # Dynamic Sensitivity: Slow down when head is moving very little
                skip_movement = False
                if self.last_raw_x is not None and self.last_raw_y is not None:
                    dx = raw_x - self.last_raw_x
                    dy = raw_y - self.last_raw_y
                    velocity = (dx**2 + dy**2)**0.5

                    # Micro-deadzone: If movement is practically zero, ignore it completely to prevent jitter when trying to hold perfectly still.
                    if velocity < (self.velocity_threshold / 5.0):
                        skip_movement = True
                    elif velocity < self.velocity_threshold:
                        # Enter precision mode (high smoothing, slow movement)
                        self.alpha = self.precision_alpha
                    else:
                        # Exit precision mode (fast movement)
                        self.alpha = self.base_alpha

                if skip_movement:
                    continue

                self.last_raw_x = raw_x
                self.last_raw_y = raw_y

                # Apply Active Zone scaling
                # Note: Webcam X axis is usually mirrored. Let's assume raw_x needs to be inverted.
                scaled_x = self._normalize_to_active_zone(1.0 - raw_x, self.active_zone_x_center, self.active_zone_width)
                scaled_y = self._normalize_to_active_zone(raw_y, self.active_zone_y_center, self.active_zone_height)

                # Map to screen coordinates
                target_x = scaled_x * self.screen_w
                target_y = scaled_y * self.screen_h

                # Apply EMA
                if self.ema_x is None or self.ema_y is None:
                    self.ema_x = target_x
                    self.ema_y = target_y
                else:
                    self.ema_x = self.alpha * target_x + (1 - self.alpha) * self.ema_x
                    self.ema_y = self.alpha * target_y + (1 - self.alpha) * self.ema_y

                # Move physical mouse
                try:
                    pyautogui.moveTo(int(self.ema_x), int(self.ema_y))
                except Exception as e:
                    print(f"Failed to move mouse: {e}")

            except queue.Empty:
                continue
